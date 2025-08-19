-- Generic histogram bucket calculation
-- Replace #DURATION_COLUMN# with the actual duration column name (e.g., duration_ns)
-- This fragment calculates power-of-2 buckets for latency histograms

POWER(2, CEIL(LOG2(CASE WHEN #DURATION_COLUMN# <= 0 THEN NULL ELSE CEIL(#DURATION_COLUMN# / 1000) END)))::bigint AS lat_bkt_us