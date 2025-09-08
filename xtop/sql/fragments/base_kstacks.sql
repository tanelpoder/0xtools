-- Base kernel stack traces data source
-- Provides deduplicated kernel stack traces with MD5 hashes
SELECT 
    KSTACK_HASH,
    KSTACK_SYMS
FROM read_csv_auto('#XTOP_DATADIR#/xcapture_kstacks_*.csv')