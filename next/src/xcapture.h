// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024 Tanel Poder [0x.tools]

#define TASK_COMM_LEN 16
#define MAX_STACK_LEN 127
#define MAX_FILENAME_LEN 256
#define MAX_CMDLINE_LEN 64

// kernel task states here so we don't have to include kernel headers
#define TASK_RUNNING 0x00000000
#define TASK_INTERRUPTIBLE 0x00000001
#define TASK_UNINTERRUPTIBLE 0x00000002
#define TASK_STOPPED 0x00000004
#define TASK_TRACED 0x00000008
/* Used in tsk->exit_state: */
#define EXIT_DEAD 0x00000010
#define EXIT_ZOMBIE 0x00000020
#define EXIT_TRACE (EXIT_ZOMBIE | EXIT_DEAD)
/* Used in tsk->state again: */
#define TASK_PARKED 0x00000040
#define TASK_DEAD 0x00000080
#define TASK_WAKEKILL 0x00000100
#define TASK_WAKING 0x00000200
#define TASK_NOLOAD 0x00000400
#define TASK_NEW 0x00000800
#define TASK_RTLOCK_WAIT 0x00001000
#define TASK_FREEZABLE 0x00002000
#define TASK_FREEZABLE_UNSAFE       0x00004000
#define TASK_FROZEN 0x00008000
#define TASK_STATE_MAX 0x00010000

// task flags from linux/sched/h
#define PF_KSWAPD   0x00020000  /* I am kswapd */
#define PF_KTHREAD    0x00200000  /* I am a kernel thread */


// use kernel nomenclature in kernel side eBPF code (pid,tgid)
struct task_info {
	pid_t pid;   // task id (tid in userspace)
	pid_t tgid;  // thread group id (pid in userspace)
	__u32 state;
  __u32 flags;

	uid_t euid;  // effective uid
	char comm[TASK_COMM_LEN];

	void * kstack_ptr;
	struct pt_regs * regs_ptr;
	__u32 thread_size;

	int kstack_len;
	__u64 kstack[MAX_STACK_LEN];
	__u32 syscall_nr;
	__u64 syscall_args[6];

	char filename[MAX_FILENAME_LEN];
	char full_path[MAX_FILENAME_LEN];
	char cmdline[MAX_CMDLINE_LEN]; // userspace mem: maybe not possible to read reliably using the passive task_iter probe
	char exe_file[MAX_FILENAME_LEN];

	int debug_err;
	__u64 debug_addr;
};
