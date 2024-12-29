-- SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
-- Copyright 2024 Tanel Poder [0x.tools]

-- Experimental query for joining thread samples with any "event completion" records produced
-- via a separate ringbuf. So far for syscalls only and it's not complete. It doesn't deal with
-- long-waiting syscalls so far that take over 1 second (current hardcoded sampling rate) to complete.

-- Usage:
--   You need to have the "duckdb" binary installed and in your path.
--   Then just run the following command in the current directory (with the two CSV files)
-- 
--     duckdb < duckdb_query.sql 
--
--  Depending on your terminal size, you need the .maxwidth setting to see all columns of interest


.maxwidth 200

WITH base_samples AS (
    SELECT
        t.exe
      , CASE 
          WHEN t.comm LIKE 'ora_p%' -- for oracle process naming that also use letters in addition to digits
          THEN regexp_replace(t.comm, '(?:p[0-9a-z]+_)', 'p*_', 'g')
          ELSE regexp_replace(t.comm, '[0-9]+', '*', 'g')
        END as comm
      , t.state
      , t.syscall_active
      , regexp_replace(t.filename, '[0-9]+', '*', 'g') filename
      , t.tid
      , t.sc_seq_num
      , COALESCE(c.duration_us, t.sc_us_so_far::int) as event_duration_us
    FROM read_csv_auto('xcapture_samples.csv') AS t
    LEFT OUTER JOIN read_csv_auto('xcapture_sc_completion.csv') AS c ON 
        t.tid = c.tid AND 
        t.sc_seq_num = c.sc_seq_num
    WHERE 1=1
    AND t.exe NOT IN ('[NO_MM]')
    AND t.state IN ('DISK')
)
SELECT 
    exe
  , comm
  , state
  , syscall_active
  , filename
  , POWER(2, ROUND(LOG2(CASE WHEN event_duration_us <= 0 THEN 1 ELSE event_duration_us END)))::int lat_bucket_us
  , ROUND(SUM(1000000 / event_duration_us)) est_evt_cnt
  , ROUND(SUM(1000000 / event_duration_us) * POWER(2, ROUND(LOG2(CASE WHEN event_duration_us <= 0 THEN 1 ELSE event_duration_us END)))/1000000,3) est_evt_time_s
  , bar(COUNT(*), 0, 25, 10) time_seconds_bar
  , COUNT(*) as seconds
FROM base_samples
GROUP BY
    exe
  , comm
  , state
  , syscall_active
  , filename
  , POWER(2, ROUND(LOG2(CASE WHEN event_duration_us <= 0 THEN 1 ELSE event_duration_us END)))
ORDER BY
    exe
  , comm
  , state
  , syscall_active
  , filename
  , lat_bucket_us ASC
LIMIT 40;

