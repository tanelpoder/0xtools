-- Base samples data source
-- This fragment provides the core samples data
-- Can be switched between CSV files and materialized tables
SELECT * FROM read_csv_auto('#XTOP_DATADIR#/xcapture_samples_*.csv')