-- Enriched samples CTE that includes all computed columns
-- This provides a consistent base for all queries
-- Usage: WITH enriched_samples AS (#ENRICHED_SAMPLES_CTE#)

SELECT
    samples.*,
    -- Include all computed columns
    #COMPUTED_COLUMNS#
FROM (#BASE_SAMPLES#) AS samples