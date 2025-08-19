-- Base query fragment for xcapture_samples data
-- This is always the starting point for any query
SELECT * FROM read_csv_auto('#XTOP_DATADIR#/xcapture_samples_*.csv')