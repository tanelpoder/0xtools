-- I/O request completion data fragment with JOIN condition
LEFT OUTER JOIN (
    SELECT * FROM read_csv_auto('#XTOP_DATADIR#/xcapture_iorqend_*.csv')
) io ON samples.tid = io.insert_tid AND samples.iorq_seq_num = io.iorq_seq_num