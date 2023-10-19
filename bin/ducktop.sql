SELECT
    COUNT(*) num_samples
  , ROUND(COUNT(*) / 300, 1) avg_threads -- querying 5 minutes (300 sec) of wall-clock time
  , REGEXP_REPLACE(cmdline, '.*/', '') cmdline2
--  , cmdline
  , REGEXP_REPLACE(comm, '[0-9]+','*') comm2
  , task_state
  , oracle_wait_event
  , syscall_name
--  , syscall_arg0
--  , profile_ustack
--  , profile_kstack
--  , REGEXP_REPLACE(REGEXP_REPLACE(offcpu_kstack, '^->0x[0-9a-f]+', ''), '\+[0-9]+','','g') offcpu_kstack
  , REGEXP_REPLACE(REGEXP_REPLACE(offcpu_ustack, '^->0x[0-9a-f]+', ''), '\+[0-9]+','','g') offcpu_ustack
--  , REGEXP_REPLACE(REGEXP_REPLACE(syscall_ustack, '^->0x[0-9a-f]+', ''), '\+[0-9]+','','g') syscall_ustack
--  , REGEXP_REPLACE(REGEXP_REPLACE(syscall_ustack, '^->0x[0-9a-f]+', ''), '\+[0-9]+','','g') syscall_ustack
FROM
    READ_CSV('xcapture_20231019_05.csv', auto_detect=true) samples
RIGHT OUTER JOIN
    READ_CSV('syscalls.csv', auto_detect=true) syscalls
ON (samples.syscall_id = syscalls.syscall_id)
WHERE
    sample_time BETWEEN TIMESTAMP'2023-10-19 05:00:00' AND TIMESTAMP'2023-10-19 05:05:00'
AND task_state IN ('R','D')
--AND cmdline LIKE 'postgres%'
AND comm != 'bpftrace' -- bpftrace is shown always active when taking a sample
GROUP BY 
    cmdline2
  , cmdline
  , comm2
  , task_state
  , oracle_wait_event
  , syscall_name
--  , syscall_arg0
--  , profile_ustack
--  , profile_kstack
--  , syscall_ustack
  , offcpu_ustack
--  , offcpu_kstack
ORDER BY 
     num_samples DESC
LIMIT 20
;
