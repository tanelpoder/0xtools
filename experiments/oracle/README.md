This is an example of using xcapture to read `kskthwtb` arg2 to report Oracle wait event name.

This is just a proof-of-concept experiment, so you need to change the `KSLEDT_SYM_ADDRESS` value in `xcapture-bpf.c` to the location of `ksledt_` symbol in your Oracle binary.

You can get the value with:

```
nm $ORACLE_HOME/bin/oracle | grep ksledt
```

Example command (executed in the experiments/oracle directory):

```
sudo ./xcapture-bpf --xtop -G oracle_wait_event
```

Output:


```
=== Active Threads ============================================================================================

seconds | avg_thr | visual_pct | st | username | comm           | syscall         | oracle_wait_event          
---------------------------------------------------------------------------------------------------------------
   2.60 |    0.52 | ████▊      | R  | oracle   | oracle_*_li    | -               | -                          
   2.07 |    0.41 | ███▊       | D  | oracle   | oracle_*_li    | pread64         | db file scattered read     
   0.13 |    0.03 | ▎          | R  | oracle   | oracle_*_li    | mmap            | -                          
   0.13 |    0.03 | ▎          | R  | oracle   | ora_vkrm_lin*m | -               |                            
   0.13 |    0.03 | ▎          | R  | oracle   | ora_m*_lin*c   | semtimedop      |                            
   0.07 |    0.01 | ▏          | R  | oracle   | oracle_*_li    | pread64         | db file scattered read     
   0.07 |    0.01 | ▏          | R  | oracle   | ora_vktm_lin*m | clock_nanosleep |                            
   0.07 |    0.01 | ▏          | R  | oracle   | ora_p*_lin*c   | semtimedop      |                            
   0.07 |    0.01 | ▏          | R  | tanel    | python*        | -               |                            
   0.07 |    0.01 | ▏          | R  | oracle   | ora_vkrm_lin*m | clock_nanosleep |                            
   0.07 |    0.01 | ▏          | S  | oracle   | ora_ckpt_lin*m | io_getevents    | control file parallel write
   0.07 |    0.01 | ▏          | R  | oracle   | oracle_*_li    | pread64         | -                          
   0.07 |    0.01 | ▏          | R  | oracle   | oracle_*_li    | io_submit       | -                          


sampled: 75 times, avg_thr: 1.12
start: 2024-10-12 20:57:27, duration: 5s



=== Active Threads ==================================================================================

seconds | avg_thr | visual_pct | st | username | comm           | syscall         | oracle_wait_event
-----------------------------------------------------------------------------------------------------
   0.68 |    0.14 | ██▊        | R  | oracle   | oracle_*_li    | -               | -                
   0.41 |    0.08 | █▋         | S  | oracle   | oracle_*_li    | io_getevents    | direct path read 
   0.27 |    0.05 | █▏         | R  | oracle   | ora_vkrm_lin*m | -               |                  
   0.14 |    0.03 | ▋          | R  | oracle   | ora_dia*_lin*c | semtimedop      | -                
   0.14 |    0.03 | ▋          | R  | oracle   | ora_mmnl_lin*m | -               | -                
   0.07 |    0.01 | ▍          | R  | oracle   | ora_m*_lin*m   | -               |                  
   0.07 |    0.01 | ▍          | R  | oracle   | ora_p*_lin*c   | semtimedop      |                  
   0.07 |    0.01 | ▍          | R  | oracle   | ora_vktm_lin*m | clock_nanosleep |                  
   0.07 |    0.01 | ▍          | R  | oracle   | ora_p*p_lin*c  | semtimedop      |                  
   0.07 |    0.01 | ▍          | R  | root     | pmdaxfs        | openat          |                  
   0.07 |    0.01 | ▍          | R  | root     | pmdalinux      | read            |                  
   0.07 |    0.01 | ▍          | R  | root     | pmdaproc       | getdents64      |                  
   0.07 |    0.01 | ▍          | R  | pcp      | pmdaproc       | openat          |                  
   0.07 |    0.01 | ▍          | R  | pcp      | pmdaproc       | read            |                  
   0.07 |    0.01 | ▍          | R  | pcp      | pmlogger       | -               |                  
   0.07 |    0.01 | ▍          | R  | oracle   | ora_p*q_lin*c  | semtimedop      |                  
   0.07 |    0.01 | ▍          | R  | oracle   | ora_mmnl_lin*m | semtimedop      | -                
   0.07 |    0.01 | ▍          | R  | oracle   | ora_dbrm_lin*m | -               | -                


sampled: 74 times, avg_thr: 0.5
start: 2024-10-12 20:57:32, duration: 5s
```


