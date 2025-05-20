-- SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
-- Copyright 2024-2038 Tanel Poder [0x.tools]

--
--  This is a demo of an overengineered SQL query, simply so I could display histogram latency 
--  buckets using SQL (and fill any empty buckets) all using just SQL. Normally the histogram
--  rendering will be done in the frontend UI code, but I couldn't help it and wanted to fit
--  it all in DuckDB to avoid an additional Python or JS dependency.
--
--  The queries in the xcapture v3 beta and production release will be much simpler (and faster)!
--
--  Depending on your terminal size, you need the .maxwidth setting to see all columns of interest

.nullvalue ''
.width connection2=50
.width connectionsum=50
.width connectionsum2=50
.maxwidth 300
.maxrows 1000

SET enable_progress_bar = false;
-- SET memory_limit = '1GB';
-- SET enable_profiling = 'json'; -- query_tree, query_tree_optimizer, json
-- SET profiling_mode = 'standard'; -- standard, detailed
-- SET profiling_output = 'duckdb.prof';

WITH part AS ( -- block device id to name mapping
    SELECT
        LIST_EXTRACT(field_list, 1)::int  AS DEV_MAJ,
        LIST_EXTRACT(field_list, 2)::int  AS DEV_MIN,
        TRIM(LIST_EXTRACT(field_list, 4)) AS DEVNAME
    FROM (
        SELECT
            REGEXP_EXTRACT_ALL(column0, ' +(\w+)') field_list
        FROM
            read_csv('#XTOP_DATADIR#/partitions', skip=1, header=false)
        WHERE
            field_list IS NOT NULL
    )
),
base_samples AS (
    SELECT
        t.timestamp AS SAMPLE_TIMESTAMP
      , t.exe
      , t.username
      , CASE
          WHEN t.comm LIKE 'ora_p%' -- for oracle process naming that also use letters in addition to digits
          THEN regexp_replace(t.comm, '(?:p[0-9a-z]+_)', 'p*_', 'g')
          ELSE regexp_replace(t.comm, '[0-9]+', '*', 'g')
        END as COMM
      , t.state
      , t.syscall
      , t.syscall_active
      , t.sysc_arg1
      , t.sysc_arg2
      , t.sysc_arg3
      , t.sysc_arg4
      , t.sysc_arg5
      , t.sysc_arg6
      , t.filename
      , COALESCE(REGEXP_REPLACE(t.filename, '[0-9]+', '*', 'g'), '-') AS FILENAMESUM
      , CASE
          WHEN t.filename IS NULL THEN '-'
          WHEN REGEXP_MATCHES(t.filename, '\.([^\.]+)$') THEN REGEXP_EXTRACT(t.filename, '(\.[^\.]+)$', 1)
          ELSE '-'
        END AS FEXT
      , connection
      , connection2:    COALESCE(REGEXP_REPLACE(connection, '::ffff:', '', 'g'), '-')
      , connectionsum:  COALESCE(REGEXP_REPLACE(connection2, '(->.*:)[0-9]+', '\1[*]'), '-')
      , connectionsum2: COALESCE(REGEXP_REPLACE(connection2, '(:)[0-9]+', '\1[*]', 'g'), '-')
      , t.tid
      , t.tgid
      , t.sysc_seq_num
      , sc.duration_ns                  AS SYSC_DURATION_NS
      , COALESCE(io.iorq_seq_num , 0)   AS IORQ_SEQ_NUM
      , COALESCE(io.duration_ns  , 0)   AS IORQ_DURATION_NS
      , COALESCE(io.service_ns   , 0)   AS IORQ_SERVICE_NS
      , COALESCE(io.queued_ns    , 0)   AS IORQ_QUEUED_NS
      , COALESCE(io.bytes        , 0)   AS IORQ_BYTES
      , COALESCE(io.iorq_flags , '-')   AS IORQ_FLAGS
      , COALESCE(io.dev_maj, 0)         AS DEV_MAJ
      , COALESCE(io.dev_min, 0)         AS DEV_MIN
      , CASE
            WHEN io.dev_maj IS NULL OR io.dev_maj IS NULL THEN '-'
            ELSE io.dev_maj||':'||io.dev_min
        END AS DEV
      , COALESCE(part.devname, '-') AS DEVNAME
    FROM
        read_csv_auto('#XTOP_DATADIR#/xcapture_samples_*.csv') AS t
    LEFT OUTER JOIN
        read_csv_auto('#XTOP_DATADIR#/xcapture_syscend_*.csv') AS sc
         ON t.tid = sc.tid
        AND t.sysc_seq_num = sc.sysc_seq_num
    LEFT OUTER JOIN read_csv_auto('#XTOP_DATADIR#/xcapture_iorqend_*.csv') AS io
         ON t.tid = io.insert_tid
        AND t.iorq_seq_num = io.iorq_seq_num
    LEFT OUTER JOIN part
         ON io.dev_maj = part.dev_maj
        AND io.dev_min = part.dev_min
    WHERE
        (#XTOP_WHERE#) -- the parenthesis are important here if there are OR statements in filter clause
    AND timestamp >= TIMESTAMP '#XTOP_LOW_TIME#'
    AND timestamp  < TIMESTAMP '#XTOP_HIGH_TIME#'
),
grouped_lat_buckets AS (
    SELECT
        seconds: COUNT(*)
      , SUM(seconds) OVER (PARTITION BY #XTOP_GROUP_COLS#) total_group_seconds
      , LEAST(
            POWER(2, CEIL(LOG2(CASE WHEN sysc_duration_ns <= 0 THEN NULL ELSE CEIL(sysc_duration_ns / 1000) END)))::bigint
          , POWER(2, 25)::bigint
        ) AS SC_LAT_BKT_US
      , #XTOP_GROUP_COLS#
      , ROUND(SUM(1000000000 / sysc_duration_ns)) AS EST_SC_CNT
      , ROUND(SUM(1000000000 / iorq_duration_ns)) AS EST_IORQ_CNT
      , MIN(sysc_duration_ns)                     AS MIN_SCLAT_NS
      , MAX(sysc_duration_ns)                     AS MAX_SCLAT_NS
      , MIN(sample_timestamp)                     AS FIRST_SEEN_TS
      , MAX(sample_timestamp)                     AS LAST_SEEN_TS
    FROM
        base_samples
    GROUP BY
        #XTOP_GROUP_COLS#
      , LEAST(
            POWER(2, CEIL(LOG2(CASE WHEN sysc_duration_ns <= 0 THEN NULL ELSE CEIL(sysc_duration_ns / 1000) END)))::bigint
          , POWER(2, 25)::bigint
        )
),
max_group_seconds AS (
    SELECT MAX(total_group_seconds) AS max_seconds FROM grouped_lat_buckets
),
max_lat_bkt_seconds AS (
    SELECT MAX(sum_seconds) AS max_seconds FROM (
        SELECT SUM(seconds) AS sum_seconds FROM grouped_lat_buckets
        WHERE syscall != '-'
        GROUP BY
            #XTOP_GROUP_COLS#
          , sc_lat_bkt_us
    )
),
-- generate all bucket numbers to also list buckets with no rows in histogram
-- the following pattern is a hack to abuse SQL for generating the entire histogram in SQL
-- in the final xtop (and web UI) this SQL hack is not needed as histograms are rendered in
-- frontend application code
gen_all_lat_buckets AS (
    SELECT nr, POWER(2,nr)::bigint AS sc_lat_bkt_us
    FROM (SELECT * FROM generate_series(0, 25) AS buckets(nr))
),
distinct_dimensions AS (
    SELECT DISTINCT #XTOP_GROUP_COLS#
    FROM grouped_lat_buckets
),
all_dims_buckets AS (
    SELECT distinct_dimensions.*, gen_all_lat_buckets.sc_lat_bkt_us
    FROM distinct_dimensions CROSS JOIN gen_all_lat_buckets
),
full_data AS (
    SELECT
        ab.*
      , COALESCE(g.seconds, 0)         AS SECONDS
      , COALESCE(g.est_sc_cnt, NULL)   AS EST_SC_CNT
      , COALESCE(g.min_sclat_ns, NULL) AS MIN_SCLAT_NS
      , COALESCE(g.max_sclat_ns, NULL) AS MAX_SCLAT_NS
      , g.first_seen_ts
      , g.last_seen_ts
    FROM
        all_dims_buckets ab LEFT OUTER JOIN grouped_lat_buckets g USING (#XTOP_GROUP_COLS#,sc_lat_bkt_us)
)
SELECT
    SUM(seconds) AS SECONDS
  , ROUND(SUM(seconds) / EPOCH (TIMESTAMP '#XTOP_HIGH_TIME#' - TIMESTAMP '#XTOP_LOW_TIME#'), 1) AVG_THR
  , BAR(SUM(seconds), 0, (SELECT max_seconds FROM max_group_seconds), 10) AS TIME_BAR
  , #XTOP_GROUP_COLS#
  , CASE WHEN syscall != '-' OR syscall IS NULL THEN
        -- the LPAD below isn't really needed anymore as we generate all latency buckets
        LPAD('', COALESCE(MIN(CEIL(LOG2(sc_lat_bkt_us)))::int, 0), ' ') || STRING_AGG(
            CASE -- for debugging
                WHEN seconds IS NULL THEN 'n' -- if you see this, something funky going on
            ELSE
                CASE(CEIL(8 * seconds / (SELECT max_seconds FROM max_lat_bkt_seconds)))::int
                    WHEN 0 THEN ' '
                    WHEN 1 THEN '▁'
                    WHEN 2 THEN '▂'
                    WHEN 3 THEN '▃'
                    WHEN 4 THEN '▄'
                    WHEN 5 THEN '▅'
                    WHEN 6 THEN '▆'
                    WHEN 7 THEN '▇'
                    WHEN 8 THEN '█'
                ELSE
                    '?' -- bar overflow (would be a bug)
                END
            END,
            '' ORDER BY sc_lat_bkt_us ASC
            )
    ELSE '' END AS "<1us__32us_1ms__32ms_1s_8+" -- latency_distribution
  , LPAD(FORMAT('{:,}', CASE WHEN syscall != '-' THEN MIN(min_sclat_ns) END), 15, ' ') AS  MIN_SC_LAT_NS
  , LPAD(FORMAT('{:,}', CASE WHEN syscall != '-' THEN MAX(max_sclat_ns) END), 18, ' ') AS  MAX_SC_LAT_NS
  , LPAD(FORMAT('{:,}', CASE WHEN syscall != '-' THEN SUM(est_sc_cnt)::bigint END), 13, ' ') AS EST_SC_CNT
--  , MIN(first_seen_ts) AS FIRST_SEEN
--  , MAX(last_seen_ts)  AS LAST_SEEN
FROM
    full_data
GROUP BY
    #XTOP_GROUP_COLS#
HAVING
    SUM(seconds) > 0 -- filter out empty buckets post-aggregation and histogram rendering
ORDER BY
    seconds DESC
  , #XTOP_GROUP_COLS#
LIMIT 30
;
