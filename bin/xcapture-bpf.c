/*
 *  0x.Tools xcapture-bpf v2.0 beta
 *  Sample Linux task activity using eBPF [0x.tools]
 *
 *  Copyright 2019-2024 Tanel Poder
 *
 *  This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License along
 *  with this program; if not, write to the Free Software Foundation, Inc.,
 *  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 *
 *  SPDX-License-Identifier: GPL-2.0-or-later
 *
 */

#include <uapi/linux/bpf.h>
#include <uapi/linux/ptrace.h>
#include <linux/sched.h>
#include <linux/types.h>
#include <linux/syscalls.h>

#ifdef BCC_SEC
#define __BCC__
#endif

// don't need EIP value for basic stack trace analysis (deduplicate some stackids)
// unfortunately SKIP_FRAMES 1 "skips" both the EIP value and one stack frame...
// #define SKIP_FRAMES (1 & BPF_F_SKIP_FIELD_MASK)
#define SKIP_FRAMES 0

// need to test if using BPF_STACK_TRACE_BUILDID would optimize things
// (apparently need separate stackmaps for ustacks & kstacks then)
#if defined(ONCPU_STACKS) || defined(OFFCPU_U) || defined(OFFCPU_K)
BPF_STACK_TRACE(stackmap, 65536);
#endif

struct thread_state_t {
    u32 state; // scheduler state
    u32 flags; // PF_ flags
    u32 tid;
    u32 pid;
    u32 uid;
    char comm[TASK_COMM_LEN];
    char cmdline[64]; // task->mm->argv0 command executed, unless later changed to something else, like Postgres does

    u16 syscall_id; // unsigned as we switch the value to negative on completion, to see the last syscall
    // unsigned long syscall_args[6]; // IBM s390x port has only 5 syscall args

#ifdef OFFCPU_U
    s32 offcpu_u;   // offcpu ustack
#endif
#ifdef OFFCPU_K
    s32 offcpu_k;   // offcpu kstack
#endif
#ifdef ONCPU_STACKS
    s32 oncpu_u;    // cpu-profile ustack
    s32 oncpu_k;    // cpu-profile kstack
#endif

    s32 syscall_u;

    s32 waker_tid;           // who invoked the waking of the target task
    bool in_sched_migrate;   // migrate to another CPU
    bool in_sched_waking;    // invoke wakeup, potentially on another CPU via inter-processor signalling (IPI)
    bool in_sched_wakeup;    // actual wakeup on target CPU starts
    bool is_running_on_cpu;  // sched_switch (to complete the wakeup/switch) has been invoked

    // s16 waker_syscall;
    // s32 waker_ustack;
    // s32 oracle_wait_event;

    // internal use by python frontend
    bool syscall_set; // 0 means that syscall probe has not fired yet for this task, so don't resolve syscall_id 0
};


// not using BPF_F_NO_PREALLOC here for now, trading some kernel memory for better performance
BPF_HASH(tsa, u32, struct thread_state_t, 16384);


TRACEPOINT_PROBE(raw_syscalls, sys_enter) {
// a rudimentary way for ignoring some syscalls we do not care about (this whole thing will change before GA release)
#if defined(__x86_64__)
    if (args->id ==  __NR_poll || args->id == __NR_getrusage)
#elif defined(__aarch64__)
    if (args->id == __NR_getrusage)
#endif
        return 0;

    struct thread_state_t t_empty = {};

    u32 tid = bpf_get_current_pid_tgid() & 0xffffffff;
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    struct task_struct *curtask = (struct task_struct *) bpf_get_current_task();
    
    struct thread_state_t *t = tsa.lookup_or_try_init(&tid, &t_empty);
    if (!t) return 0;

    if (!t->syscall_set) t->syscall_set  = 1;

    t->syscall_id   = args->id;

    // use a conditional copy(len(args))?
    // t->syscall_arg0 = args->args[0];
    // t->syscall_arg1 = args->args[1];
    // t->syscall_arg2 = args->args[2];
    // t->syscall_arg3 = args->args[3];
    // t->syscall_arg4 = args->args[4];
    // t->syscall_arg5 = args->args[5];
    // t->syscall_u = stackmap.get_stackid(args, BPF_F_USER_STACK | BPF_F_REUSE_STACKID | BPF_F_FAST_STACK_CMP);

    tsa.update(&tid, t);
    return 0;
} // raw_syscalls:sys_enter


TRACEPOINT_PROBE(raw_syscalls, sys_exit) {
    
    u32 tid = bpf_get_current_pid_tgid() & 0xffffffff;
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    struct task_struct *curtask = (struct task_struct *) bpf_get_current_task();

    struct thread_state_t t_empty = {};
    struct thread_state_t *t = tsa.lookup_or_try_init(&tid, &t_empty);
    if (!t) return 0;

    t->syscall_id = t->syscall_id * -1; // switch the syscall_id to its negative value on exit
    t->syscall_u = t->syscall_u * -1; 

    tsa.update(&tid, t);

    return 0;
} // raw_syscalls:sys_exit

// sampling profiling of on-CPU threads (python frontend uses perf event with freq=1)
// update the stack id of threads currently running on (any) CPU

int update_cpu_stack_profile(struct bpf_perf_event_data *ctx) {

    u32 tid = bpf_get_current_pid_tgid() & 0xffffffff;

    // ignore tid 0 - kernel cpuidle
    if (tid) {
        u32 pid = bpf_get_current_pid_tgid() >> 32;
        struct task_struct *curtask = (struct task_struct *) bpf_get_current_task();

        struct thread_state_t t_empty = {};
        struct thread_state_t *t = tsa.lookup_or_try_init(&tid, &t_empty);
        if (!t) return 0;

        t->tid = tid;
        t->pid = pid;
        t->uid = (s32) (bpf_get_current_uid_gid() & 0xFFFFFFFF);
#if LINUX_VERSION_MAJOR >= 5 && LINUX_VERSION_PATCHLEVEL >= 14
        t->state = curtask->__state;
#else
        t->state = curtask->state;
#endif
        bpf_probe_read_str(t->comm, sizeof(t->comm), (struct task_struct *)curtask->comm);

#ifdef CMDLINE
        if (curtask->mm && curtask->mm->arg_start) {
            unsigned long arg_start = curtask->mm->arg_start;
            bpf_probe_read_user_str(t->cmdline, sizeof(t->cmdline), (void *)arg_start);
        }
#endif
#ifdef ONCPU_STACKS
        t->oncpu_u = stackmap.get_stackid(ctx, SKIP_FRAMES | BPF_F_USER_STACK | BPF_F_REUSE_STACKID | BPF_F_FAST_STACK_CMP);
        t->oncpu_k = stackmap.get_stackid(ctx, 0); // BPF_F_REUSE_STACKID | BPF_F_FAST_STACK_CMP);
#endif

        tsa.update(&tid, t);
    }

    return 0;
};

// scheduler (or someone) wants this task to migrate to another CPU
TRACEPOINT_PROBE(sched, sched_migrate_task) {

    struct thread_state_t t_empty = {};
    u32 tid = args->pid;

    struct thread_state_t *t = tsa.lookup_or_try_init(&tid, &t_empty);
    if (!t) return 0;

    t->in_sched_migrate = 1;

    tsa.update(&tid, t);

    return 0;
}

// Context enrichment example (kernel): which waker (curtask->pid) woke a wakee (args->pid) up?
TRACEPOINT_PROBE(sched, sched_waking) {

    struct task_struct *curtask = (struct task_struct *) bpf_get_current_task();
    struct thread_state_t t_empty = {};

    u32 tid_woken = args->pid;
 
    struct thread_state_t *t_being_waked_up = tsa.lookup_or_try_init(&tid_woken, &t_empty);
    if (!t_being_waked_up) return 0;

    t_being_waked_up->in_sched_waking = 1;
    t_being_waked_up->tid = tid_woken;          // this guy is being woken up
    t_being_waked_up->waker_tid = curtask->pid; // this is who wakes that guy up

    tsa.update(&tid_woken, t_being_waked_up);

    return 0;
}

// Context enrichment example (kernel): woken up task waiting in the CPU runqueue
TRACEPOINT_PROBE(sched, sched_wakeup) {

    struct task_struct *curtask = (struct task_struct *) bpf_get_current_task();
    struct thread_state_t t_empty = {};

    u32 tid_woken = args->pid;
 
    struct thread_state_t *t_being_waked_up = tsa.lookup_or_try_init(&tid_woken, &t_empty);
    if (!t_being_waked_up) return 0;

    t_being_waked_up->in_sched_wakeup = 1;
    t_being_waked_up->tid = tid_woken;          // this guy is being woken up
    
    tsa.update(&tid_woken, t_being_waked_up);

    return 0;
}

// newly started task woken up
TRACEPOINT_PROBE(sched, sched_wakeup_new) {

    struct task_struct *curtask = (struct task_struct *) bpf_get_current_task(); // curtask is who does the waking-up!
    struct thread_state_t t_empty = {};

    u32 tid_woken = args->pid;

    struct thread_state_t *t_new = tsa.lookup_or_try_init(&tid_woken, &t_empty);
    if (!t_new) return 0;

    t_new->in_sched_wakeup = 1;
    t_new->tid = tid_woken;          // this guy is being woken up
    t_new->waker_tid = curtask->pid; // this is who wakes that guy up (todo: is this valid here?)

    bpf_probe_read_str(t_new->comm, sizeof(t_new->comm), args->comm);

    // dont read cmdline here, will get cmdline of the task that ran clone()?
    // bpf_probe_read_user_str(t_new->cmdline, sizeof(t_new->cmdline), (struct task_struct *)curtask->mm->arg_start);

    tsa.update(&tid_woken, t_new);

    return 0;
}

// "next" is about to be put on CPU, "prev" goes off-CPU
RAW_TRACEPOINT_PROBE(sched_switch) {

    // from https://github.com/torvalds/linux/blob/master/include/trace/events/sched.h (sched_switch trace event)
    bool *preempt = (bool *)ctx->args[0];
    struct task_struct *prev = (struct task_struct *)ctx->args[1];
    struct task_struct *next = (struct task_struct *)ctx->args[2];
#if LINUX_VERSION_MAJOR >= 5 && LINUX_VERSION_PATCHLEVEL >= 14
    unsigned int prev_state = prev->__state; // ctx->args[3] won't work in older configs due to breaking change in sched_switch tracepoint
#else
    unsigned int prev_state = prev->state; 
#endif
    
    s32 prev_tid = prev->pid;  // task (tid in user tools)
    s32 prev_pid = prev->tgid; // tgid (pid in user tools)
    s32 next_tid = next->pid;  // task
    s32 next_pid = next->tgid; // tgid

    struct thread_state_t t_empty_prev = {0};
    struct thread_state_t t_empty_next = {0};

    // we don't want to capture/report the previous cpuidle "task" during actual task wakeups (tid 0)
    if (prev_tid) {
        struct thread_state_t *t_prev = tsa.lookup_or_try_init(&prev_tid, &t_empty_prev);
        if (!t_prev) return 0;

        t_prev->tid = prev_tid;
        t_prev->pid = prev_pid;
        t_prev->flags = prev->flags;

        // if (!t_prev->comm[0])
        bpf_probe_read_str(t_prev->comm, sizeof(t_prev->comm), prev->comm);

        // switch finished, clear waking/wakeup flags
        t_prev->in_sched_migrate  = 0; // todo: these 3 are probably not needed here
        t_prev->in_sched_waking   = 0;
        t_prev->in_sched_wakeup   = 0;
        t_prev->is_running_on_cpu = 0;
        t_prev->state = prev_state;

        t_prev->uid = prev->cred->euid.val;

#ifdef OFFCPU_U
        if (!(prev->flags & PF_KTHREAD))
            t_prev->offcpu_u = stackmap.get_stackid(ctx, SKIP_FRAMES | BPF_F_USER_STACK | BPF_F_REUSE_STACKID | BPF_F_FAST_STACK_CMP);
#endif
#ifdef OFFCPU_K
        t_prev->offcpu_k = stackmap.get_stackid(ctx, BPF_F_REUSE_STACKID | BPF_F_FAST_STACK_CMP);
#endif
#ifdef CMDLINE
        if (prev->mm && prev->mm->arg_start) {
            unsigned long arg_start = prev->mm->arg_start;
            bpf_probe_read_user_str(t_prev->cmdline, sizeof(t_prev->cmdline), (void *)arg_start);
        }
#endif
        tsa.update(&prev_tid, t_prev);
    }

    // we don't want to capture/report the cpuidle "task" (tid 0) when CPU goes to cpuidle
    if (next_tid) {
        struct thread_state_t *t_next = tsa.lookup_or_try_init(&next_tid, &t_empty_next);
        if (!t_next) return 0;

        t_next->tid = next_tid;
        t_next->pid = next_pid;
        t_next->flags = next->flags;
    
        //if (!t_next->comm[0])
        bpf_probe_read_str(t_next->comm, sizeof(t_next->comm), next->comm);

#if LINUX_VERSION_MAJOR >= 5 && LINUX_VERSION_PATCHLEVEL >= 14
        t_next->state = next->__state;
#else
        t_next->state = next->state;
#endif
        t_next->in_sched_migrate  = 0;
        t_next->in_sched_waking   = 0;
        t_next->in_sched_wakeup   = 0;
        t_next->is_running_on_cpu = 1;

        t_next->uid = next->cred->euid.val;

// previous off-cpu stacks are oncpu stacks when getting back onto cpu (kernel stack slightly different)
#ifdef ONCPU_STACKS
#ifdef OFFCPU_U
        t_next->oncpu_u = t_next->offcpu_u;
#endif
#ifdef OFFCPU_K
        t_next->oncpu_k = t_next->offcpu_k;
#endif
#endif

#ifdef CMDLINE
        if (next->mm && next->mm->arg_start) {
            unsigned long arg_start = next->mm->arg_start;
            bpf_probe_read_user_str(t_next->cmdline, sizeof(t_next->cmdline), (void *)arg_start);
        }
#endif

        tsa.update(&next_tid, t_next);
    }

    return 0;
}


// remove hashmap elements on task exit
static inline int cleanup_tid(u32 tid_exiting) {
    tsa.delete(&tid_exiting);
    return 0;
}

TRACEPOINT_PROBE(sched, sched_process_exit) {
    return cleanup_tid(args->pid);
}

TRACEPOINT_PROBE(sched, sched_process_free) {
    return cleanup_tid(args->pid);
}

TRACEPOINT_PROBE(sched, sched_kthread_stop) {
    return cleanup_tid(args->pid);
}

// vim:syntax=c
