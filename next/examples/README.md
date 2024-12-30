### Examples:

This is an experimental query for joining thread samples with any "event completion" records produced
via a separate ringbuf. So far for syscalls only and the query is not complete - it doesn't deal with
long-waiting syscalls that take over 1 second (current hardcoded sampling rate) to complete.

### Usage:

You need to have the "duckdb" binary installed and in your path.
Then just run the following command in the current directory (with the two CSV files)

```
duckdb < duckdb_query.sql
``` 

Depending on your terminal size, you need the .maxwidth setting to see all columns of interest (it's in the script)

### Query Output:

```
$ cd next/examples
$ duckdb < duckdb_query.sql 
┌─────────┬────────────────┬─────────┬────────────────┬───────────────┬───────────────┬─────────────┬────────────────┬──────────────────┬─────────┐
│   EXE   │      comm      │  STATE  │ SYSCALL_ACTIVE │   filename    │ lat_bucket_us │ est_evt_cnt │ est_evt_time_s │ time_seconds_bar │ seconds │
│ varchar │    varchar     │ varchar │    varchar     │    varchar    │     int32     │   double    │     double     │     varchar      │  int64  │
├─────────┼────────────────┼─────────┼────────────────┼───────────────┼───────────────┼─────────────┼────────────────┼──────────────────┼─────────┤
│ auditd  │ auditd         │ DISK    │ read           │ audit.log     │          2048 │       436.0 │          0.892 │ ▍                │       1 │
│ dd      │ dd             │ DISK    │ read           │ sda           │            64 │     11905.0 │          0.762 │ ▍                │       1 │
│ dd      │ dd             │ DISK    │ read           │ sda           │           256 │      3115.0 │          0.798 │ ▍                │       1 │
│ dd      │ dd             │ DISK    │ read           │ sda           │           512 │      4522.0 │          2.315 │ █▏               │       3 │
│ dd      │ dd             │ DISK    │ read           │ sda           │          1024 │     11829.0 │         12.113 │ ████▍            │      11 │
│ dd      │ dd             │ DISK    │ read           │ sda           │          2048 │       521.0 │          1.066 │ ▍                │       1 │
│ dd      │ dd             │ DISK    │ read           │ sda           │          4096 │      2340.0 │          9.583 │ ███▏             │       8 │
│ mysqld  │ connection     │ DISK    │ fdatasync      │ binlog.*      │          2048 │      8322.0 │         17.043 │ ███████▏         │      18 │
│ mysqld  │ connection     │ DISK    │ fdatasync      │ binlog.*      │          4096 │      7101.0 │         29.087 │ ██████████       │      28 │
│ mysqld  │ connection     │ DISK    │ fdatasync      │ binlog.*      │          8192 │      1256.0 │         10.288 │ ████             │      10 │
│ mysqld  │ connection     │ DISK    │ fdatasync      │ binlog.*      │         16384 │      1100.0 │          18.02 │ ██████▊          │      17 │
│ mysqld  │ connection     │ DISK    │ pread64        │ sbtest*.ibd   │           512 │      5820.0 │           2.98 │ █▏               │       3 │
│ mysqld  │ connection     │ DISK    │ pread64        │ sbtest*.ibd   │          1024 │      2395.0 │          2.453 │ ▊                │       2 │
│ mysqld  │ connection     │ DISK    │ pread64        │ sbtest*.ibd   │          2048 │      1651.0 │          3.382 │ █▏               │       3 │
│ mysqld  │ connection     │ DISK    │ pread64        │ sbtest*.ibd   │          4096 │       301.0 │          1.234 │ ▍                │       1 │
│ mysqld  │ ib_log_flush   │ DISK    │ fsync          │ #ib_redo*     │          2048 │     18275.0 │         37.427 │ ██████████       │      38 │
│ mysqld  │ ib_log_flush   │ DISK    │ fsync          │ #ib_redo*     │          4096 │      4937.0 │         20.221 │ ███████▏         │      18 │
│ mysqld  │ ib_log_flush   │ DISK    │ fsync          │ #ib_redo*     │          8192 │      3564.0 │           29.2 │ ██████████       │      28 │
│ mysqld  │ ib_log_flush   │ DISK    │ fsync          │ #ib_redo*     │         16384 │       386.0 │          6.322 │ ██▍              │       6 │
│ mysqld  │ ib_pg_flush_co │ DISK    │ pwrite64       │ #ib_*_*.dblwr │           512 │      3204.0 │           1.64 │ ▊                │       2 │
│ mysqld  │ ib_pg_flush_co │ DISK    │ pwrite64       │ #ib_*_*.dblwr │          1024 │      2603.0 │          2.666 │ █▏               │       3 │
│ mysqld  │ ib_pg_flush_co │ DISK    │ pwrite64       │ #ib_*_*.dblwr │          4096 │      1063.0 │          4.353 │ █▌               │       4 │
│ tar     │ tar            │ DISK    │ getdents64     │ CallChecker   │          2048 │       382.0 │          0.783 │ ▍                │       1 │
│ tar     │ tar            │ DISK    │ getdents64     │ abi           │          4096 │       280.0 │          1.147 │ ▍                │       1 │
│ tar     │ tar            │ DISK    │ getdents64     │ arcnet        │          4096 │       310.0 │           1.27 │ ▍                │       1 │
│ tar     │ tar            │ DISK    │ getdents64     │ chipidea      │          4096 │       272.0 │          1.116 │ ▍                │       1 │
│ tar     │ tar            │ DISK    │ getdents64     │ funeth        │          1024 │      1355.0 │          1.388 │ ▍                │       1 │
│ tar     │ tar            │ DISK    │ getdents64     │ hugetlbfs     │          4096 │       273.0 │          1.116 │ ▍                │       1 │
│ tar     │ tar            │ DISK    │ getdents64     │ imx*-isi      │          2048 │       370.0 │          0.757 │ ▍                │       1 │
│ tar     │ tar            │ DISK    │ getdents64     │ int*          │          4096 │       281.0 │          1.151 │ ▍                │       1 │
│ tar     │ tar            │ DISK    │ getdents64     │ mpls          │          4096 │       308.0 │          1.263 │ ▍                │       1 │
│ tar     │ tar            │ DISK    │ getdents64     │ pvpanic       │           512 │      1406.0 │           0.72 │ ▍                │       1 │
│ tar     │ tar            │ DISK    │ getdents64     │ qualcomm      │          2048 │       365.0 │          0.748 │ ▍                │       1 │
│ tar     │ tar            │ DISK    │ getdents64     │ starfive      │          4096 │       325.0 │          1.332 │ ▍                │       1 │
│ tar     │ tar            │ DISK    │ getdents64     │ xfrm          │          4096 │       329.0 │          1.347 │ ▍                │       1 │
├─────────┴────────────────┴─────────┴────────────────┴───────────────┴───────────────┴─────────────┴────────────────┴──────────────────┴─────────┤
│ 35 rows                                                                                                                              10 columns │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```
