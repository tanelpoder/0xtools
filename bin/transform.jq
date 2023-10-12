(["SAMPLE_TIME", "TID", "PID", "COMM", "TASK_STATE", "SYSCALL_ID", 
  "SYSCALL_ARG0", "SYSCALL_ARG1", "SYSCALL_ARG2", 
  "SYSCALL_ARG3", "SYSCALL_ARG4", "SYSCALL_ARG5", 
  "PROBE_NAME", "PROFILE_USTACK", "PROFILE_KSTACK"],
(.samples[] | 
    .SAMPLE_TIME       as $time               |
    .comm              as $comm_map           |
    .task_state        as $task_state_map     |
    .syscall_id        as $syscall_id_map     |
    .syscall_args      as $syscall_args_map   |
    .probe_name        as $probe_name_map     |
    .profile_ustack    as $profile_ustack_map |
    .profile_kstack    as $profile_kstack_map |
    .pid | to_entries[] | .key as $key | 
    [$time, $key, .value,
        ($comm_map           [$key]    ),  # // "-"
        ($task_state_map     [$key]    ),
        ($syscall_id_map     [$key]    ),
        ($syscall_args_map   [$key][0] ),
        ($syscall_args_map   [$key][1] ),
        ($syscall_args_map   [$key][2] ),
        ($syscall_args_map   [$key][3] ),
        ($syscall_args_map   [$key][4] ),
        ($syscall_args_map   [$key][5] ),
        ($probe_name_map     [$key]    ),
        ($profile_ustack_map [$key]    ),
        ($profile_kstack_map [$key]    )
    ]
)) | @csv

# vi:syntax=zsh

