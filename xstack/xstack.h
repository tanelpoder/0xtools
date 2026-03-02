// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
#ifndef __XSTACK_H
#define __XSTACK_H

#define TASK_COMM_LEN 16
#define MAX_STACK_DEPTH 127

// kernel task states here so we don't have to include kernel headers
#define TASK_RUNNING          0x00000000
#define TASK_INTERRUPTIBLE    0x00000001
#define TASK_UNINTERRUPTIBLE  0x00000002
#define TASK_STOPPED          0x00000004
#define TASK_TRACED           0x00000008
/* Used in tsk->exit_state: */
#define EXIT_DEAD             0x00000010
#define EXIT_ZOMBIE           0x00000020
#define EXIT_TRACE (EXIT_ZOMBIE | EXIT_DEAD)
/* Used in tsk->state again: */
#define TASK_PARKED           0x00000040
#define TASK_DEAD             0x00000080
#define TASK_WAKEKILL         0x00000100
#define TASK_WAKING           0x00000200
#define TASK_NOLOAD           0x00000400
#define TASK_NEW              0x00000800
#define TASK_RTLOCK_WAIT      0x00001000
#define TASK_FREEZABLE        0x00002000
#define TASK_FREEZABLE_UNSAFE 0x00004000
#define TASK_FROZEN           0x00008000
#define TASK_STATE_MAX        0x00010000

#define TASK_IDLE (TASK_UNINTERRUPTIBLE | TASK_NOLOAD)

// task flags from linux/sched.h
#define PF_KSWAPD             0x00020000  /* I am kswapd */
#define PF_KTHREAD            0x00200000  /* I am a kernel thread */


// Filter configuration
struct filter_config {
    __u32 filter_mode;  // 0=all, 1=by_tgid, 2=by_pid
    __u32 target_tgid;
    __u32 target_pid;
};

// Event sent from kernel to userspace
struct stack_event {
    __u32 pid;
    __u32 tgid;
    __u32 state;
    char comm[TASK_COMM_LEN];
    __s32 kstack_sz;
    __s32 ustack_sz;
    __u64 kstack[MAX_STACK_DEPTH];
    __u64 ustack[MAX_STACK_DEPTH];
};

#endif /* __XSTACK_H */
