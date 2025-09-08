-- Generic histogram bucket calculation
-- Replace #DURATION_COLUMN# with the actual duration column name (e.g., duration_ns)
-- This fragment calculates power-of-2 buckets for latency histograms

CASE 
    WHEN #DURATION_COLUMN# IS NULL OR #DURATION_COLUMN# <= 0 THEN NULL
    ELSE POWER(2, CEIL(LOG2(CEIL(#DURATION_COLUMN# / 1000))))::bigint
END AS lat_bkt_us