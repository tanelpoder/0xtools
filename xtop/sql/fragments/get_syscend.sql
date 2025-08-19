-- System call completion data fragment with JOIN condition
LEFT OUTER JOIN (
    SELECT * FROM read_csv_auto('#XTOP_DATADIR#/xcapture_syscend_*.csv')
) sc ON samples.tid = sc.tid AND samples.sysc_seq_num = sc.sysc_seq_num