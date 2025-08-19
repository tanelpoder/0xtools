-- Base syscall completion data source
-- Provides system call completion events with duration measurements
SELECT * FROM read_csv_auto('#XTOP_DATADIR#/xcapture_syscend_*.csv')