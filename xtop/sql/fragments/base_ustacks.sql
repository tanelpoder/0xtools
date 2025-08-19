-- Base userspace stack traces data source  
-- Provides deduplicated userspace stack traces with MD5 hashes
SELECT 
    STACK_HASH AS USTACK_HASH,
    STACK_SYMS AS USTACK_SYMS
FROM read_csv_auto('#XTOP_DATADIR#/xcapture_ustacks_*.csv')