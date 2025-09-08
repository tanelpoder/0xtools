-- Userspace stack traces fragment with JOIN condition
LEFT OUTER JOIN (
    SELECT DISTINCT
        USTACK_HASH,
        USTACK_SYMS
    FROM read_csv_auto('#XTOP_DATADIR#/xcapture_ustacks_*.csv')
) us ON samples.ustack_hash = us.ustack_hash