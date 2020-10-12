# Linux Process Snapper

Linux Process Snapper (pSnapper, psn) is a Linux `/proc` profiler that works by sampling Linux task states and other metrics from `/proc/PID/task/TID` pseudofiles. pSnapper is a _passive sampling profiler_, it does not attach to your program to slow it down, nor alter your program execution path or signal handling (like `strace` may inadvertently do).

As pSnapper is just a python script reading /proc files, it does not require software installation, nor install any kernel modules. pSnapper does not even require root access in many cases. The exception is if you want to sample some “private” /proc files (like syscall, and kernel stack) of processes running under other users.

More info at https://tanelpoder.com/psnapper

### Example 1

MySQL XFS fsync() metadata syncing bottleneck & inode contention:

```
$ sudo psn -p "mysqld|kwork" -G syscall,wchan

Linux Process Snapper v0.14 by Tanel Poder [https://tanelpoder.com/psnapper]
Sampling /proc/syscall, stat, wchan for 5 seconds... finished.


=== Active Threads ========================================================================================

 samples | avg_threads | comm          | state                  | syscall   | wchan                        
-----------------------------------------------------------------------------------------------------------
      25 |        3.12 | (mysqld)      | Disk (Uninterruptible) | fsync     | _xfs_log_force_lsn
      16 |        2.00 | (mysqld)      | Running (ON CPU)       | [running] | 0                            
      14 |        1.75 | (mysqld)      | Disk (Uninterruptible) | pwrite64  | call_rwsem_down_write_failed
       8 |        1.00 | (mysqld)      | Disk (Uninterruptible) | fsync     | submit_bio_wait              
       4 |        0.50 | (mysqld)      | Disk (Uninterruptible) | pread64   | io_schedule                  
       4 |        0.50 | (mysqld)      | Disk (Uninterruptible) | pwrite64  | io_schedule                  
       3 |        0.38 | (mysqld)      | Disk (Uninterruptible) | pread64   | 0                            
       3 |        0.38 | (mysqld)      | Running (ON CPU)       | [running] | io_schedule                  
       3 |        0.38 | (mysqld)      | Running (ON CPU)       | pread64   | 0                            
       2 |        0.25 | (mysqld)      | Disk (Uninterruptible) | [running] | 0                            
       1 |        0.12 | (kworker/*:*) | Running (ON CPU)       | read      | worker_thread                
       1 |        0.12 | (mysqld)      | Disk (Uninterruptible) | fsync     | io_schedule                  
       1 |        0.12 | (mysqld)      | Disk (Uninterruptible) | futex     | call_rwsem_down_write_failed 
       1 |        0.12 | (mysqld)      | Disk (Uninterruptible) | poll      | 0                            
       1 |        0.12 | (mysqld)      | Disk (Uninterruptible) | pwrite64  | _xfs_log_force_lsn           
       1 |        0.12 | (mysqld)      | Running (ON CPU)       | fsync     | submit_bio_wait              
       1 |        0.12 | (mysqld)      | Running (ON CPU)       | futex     | futex_wait_queue_me      
```

### Example 2

Linux software RAID syncing causing an I/O hang:

```
$ sudo psn -G syscall,wchan -r -p "sync|kworker"

Linux Process Snapper v0.11 by Tanel Poder [https://tanelpoder.com/psnapper]
Sampling /proc/stat, syscall, wchan for 5 seconds... finished.


=== Active Threads =====================================================================================

 samples | avg_threads | comm            | state                  | syscall    | wchan                  
--------------------------------------------------------------------------------------------------------
     100 |        1.00 | (sync)          | Disk (Uninterruptible) | sync       | wb_wait_for_completion
      98 |        0.98 | (kworker/u66:0) | Disk (Uninterruptible) | read       | wait_barrier           
      82 |        0.82 | (md10_resync)   | Disk (Uninterruptible) | read       | raise_barrier          
      15 |        0.15 | (md10_resync)   | Disk (Uninterruptible) | read       | md_do_sync             
       3 |        0.03 | (kworker/29:2)  | Disk (Uninterruptible) | read       | rpm_resume             
       3 |        0.03 | (md10_resync)   | Disk (Uninterruptible) | read       | raid10_sync_request    
       2 |        0.02 | (kworker/1:0)   | Disk (Uninterruptible) | read       | hub_event              
       2 |        0.02 | (kworker/29:2)  | Disk (Uninterruptible) | read       | msleep                 
       1 |        0.01 | (kworker/20:1H) | Running (ON CPU)       | read       | worker_thread          
       1 |        0.01 | (kworker/30:0)  | Running (ON CPU)       | [userland] | 0                      
       1 |        0.01 | (kworker/6:0)   | Running (ON CPU)       | [userland] | 0                      
       1 |        0.01 | (kworker/u66:0) | Running (ON CPU)       | [userland] | 0                      
       1 |        0.01 | (kworker/u66:0) | Running (ON CPU)       | read       | wait_barrier      
```

More info at https://tanelpoder.com/psnapper

