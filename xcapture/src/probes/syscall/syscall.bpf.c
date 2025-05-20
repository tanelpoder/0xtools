// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024-2038 Tanel Poder [0x.tools]

#include "syscall/syscall.bpf.h"
#include "xcapture.h"
#include "xcapture_helpers.h"

char LICENSE[] SEC("license") = "Dual BSD/GPL";

// If a userspace task is entering io_*getevents, check if there are any
// I/Os inflight in that ring or it's just an "idle" wait for work to show up
// NOTE: this won't work in the task_iterator program context (yet) as it needs
// to read userspace memory of other processes. TODO: 5.18 has bpf_copy_from_user_task()
static __u32 __always_inline get_num_inflight_aios_ring(__u64 ctx_id)
{
    if (!ctx_id) return 0;
    struct aio_ring *ring = (void *)ctx_id;
    __u32 head = 0, tail = 0;

    // Read ring head and tail (and bail on error)
    if (BPF_CORE_READ_USER_INTO(&head, ring, head)) return -1;
    if (BPF_CORE_READ_USER_INTO(&tail, ring, tail)) return -2;

    if (tail >= head) {
            return tail - head;
    } else {
        // When when tail has wrapped but head hasn't yet
        return (UINT32_MAX - head) + tail + 1;
    }
}


// syscall entry & exit handlers for active tracking mode
SEC("tp_btf/sys_enter")
int BPF_PROG(handle_sys_enter, struct pt_regs *regs, long syscall_nr)
{
    struct task_storage *storage;
    struct task_struct *task = bpf_get_current_task_btf();
    if (!task)
        return 0;

    storage = bpf_task_storage_get(&task_storage, task, NULL, BPF_LOCAL_STORAGE_GET_F_CREATE);
    if (!storage)
        return 0;

    storage->sc_enter_time = bpf_ktime_get_ns();
    storage->in_syscall_nr = syscall_nr;
    storage->sc_sequence_num++;

    if (syscall_nr == __NR_io_getevents || syscall_nr == __NR_io_pgetevents) {
        __u64 ctx_id = PT_REGS_PARM1_CORE_SYSCALL(regs); // aio ctx_id (process-wide mem addr)
        storage->aio_inflight_reqs = get_num_inflight_aios_ring(ctx_id);
    }

    return 0;
}

SEC("tp_btf/sys_exit")
int BPF_PROG(handle_sys_exit, struct pt_regs *regs, long ret)
{
    struct task_storage *storage;
    struct task_struct *task = bpf_get_current_task_btf();
    storage = bpf_task_storage_get(&task_storage, task, NULL,
                                  BPF_LOCAL_STORAGE_GET_F_CREATE);
    if (!storage)
        return 0;

    if (!storage->sc_sampled) { // only emit syscalls caught by task sampler
        return 0;
    } else {
        struct sc_completion_event *scevent;
        scevent = bpf_ringbuf_reserve(&completion_events, sizeof(*scevent), 0);

        if (scevent) {
            scevent->type = EVENT_SYSCALL_COMPLETION;  // Set scevent type

            // if storage->sc_sampled above is true, then storage->pid/tgid
            // have been put in place by task sampler already too
            scevent->pid = storage->pid;
            scevent->tgid = storage->tgid;
            scevent->completed_syscall_nr = storage->in_syscall_nr;
            scevent->completed_sc_sequence_num = storage->sc_sequence_num;
            scevent->completed_sc_enter_time = storage->sc_enter_time;
            scevent->completed_sc_exit_time = bpf_ktime_get_ns();
            scevent->completed_sc_ret_val = ret;

            bpf_ringbuf_submit(scevent, 0);
        }
    }

    // clear sampled status as the syscall exits
    storage->sc_sampled = false;
    storage->in_syscall_nr = -1;
    storage->sc_enter_time = 0;
    return 0;
}
