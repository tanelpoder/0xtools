-- Kernel stack traces fragment with JOIN condition
LEFT OUTER JOIN (
    SELECT DISTINCT
        KSTACK_HASH,
        KSTACK_SYMS
    FROM read_csv_auto('#XTOP_DATADIR#/xcapture_kstacks_*.csv')
) ks ON samples.kstack_hash = ks.kstack_hash