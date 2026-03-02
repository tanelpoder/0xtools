-- Base I/O request completion data source
-- Provides block I/O request completions with timing and device info
SELECT * FROM read_csv_auto('#XTOP_DATADIR#/xcapture_iorqend_*.csv')