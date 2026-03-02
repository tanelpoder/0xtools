-- Generic histogram aggregation query template
-- Placeholders:
--   #GROUP_COLUMNS# - comma-separated list of GROUP BY columns
--   #BUCKET_COLUMN# - the bucket column name (e.g., sc_lat_bkt_us)
--   #DURATION_COLUMN# - the duration column name (e.g., sc_duration_ns)

SELECT
    #GROUP_COLUMNS#,
    #BUCKET_COLUMN#,
    COUNT(*) as cnt,
    SUM(CASE 
        WHEN #DURATION_COLUMN# > 0 
        THEN (1000000000.0 / #DURATION_COLUMN#) * #BUCKET_COLUMN# / 1000000.0
        ELSE 0 
    END) as est_time_s
FROM base_samples
WHERE #DURATION_COLUMN# > 0
GROUP BY #GROUP_COLUMNS#, #BUCKET_COLUMN#