-- Userspace stack traces fragment with JOIN condition
LEFT OUTER JOIN (
    SELECT DISTINCT
        STACK_HASH AS USTACK_HASH,
        STACK_SYMS AS USTACK_SYMS
    FROM read_csv_auto('#XTOP_DATADIR#/xcapture_ustacks_*.csv')
) us ON samples.ustack_hash = us.ustack_hash