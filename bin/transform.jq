(["SAMPLE_TIME", "TID", "PID", "COMM", "TASK_STATE", "SYSCALL_ID", 
  "SYSCALL_ARG0", "SYSCALL_ARG1", "SYSCALL_ARG2", 
  "SYSCALL_ARG3", "SYSCALL_ARG4", "SYSCALL_ARG5", 
  "CMDLINE", "PROFILE_USTACK", "PROFILE_KSTACK",
  "SYSCALL_USTACK", "OFFCPU_USTACK", "OFFCPU_KSTACK",
  "SCHED_WAKEUP", "ORACLE_WAIT_EVENT"],
(.samples[] | 
    .SAMPLE_TIME       as $time                  |
    .comm              as $comm_map              |
    .task_state        as $task_state_map        |
    .syscall_id        as $syscall_id_map        |
    .syscall_args      as $syscall_args_map      |
    .cmdline           as $cmdline_map           |
    .profile_ustack    as $profile_ustack_map    |
    .profile_kstack    as $profile_kstack_map    |
    .syscall_ustack    as $syscall_ustack_map    |
    .offcpu_ustack     as $offcpu_ustack_map     |
    .offcpu_kstack     as $offcpu_kstack_map     |
    .sched_wakeup      as $sched_wakeup_map      |
    .oracle_wait_event as $oracle_wait_event_map |
    .pid | to_entries[] | .key as $key | 
    [$time, $key, .value,
        ($comm_map              [$key]    ),  # // "-"
        ($task_state_map        [$key]    ),
        ($syscall_id_map        [$key]    ),
        ($syscall_args_map      [$key][0] ),
        ($syscall_args_map      [$key][1] ),
        ($syscall_args_map      [$key][2] ),
        ($syscall_args_map      [$key][3] ),
        ($syscall_args_map      [$key][4] ),
        ($syscall_args_map      [$key][5] ),
        ($cmdline_map           [$key]    ),
        ($profile_ustack_map    [$key]    ),
        ($profile_kstack_map    [$key]    ),
        ($syscall_ustack_map    [$key]    ),
        ($offcpu_ustack_map     [$key]    ),
        ($offcpu_kstack_map     [$key]    ),
        ($sched_wakeup_map      [$key]    ),
        ($oracle_wait_event_map [$key]    )
    ]
)) | @csv

# vi:syntax=zsh

