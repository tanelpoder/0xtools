// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024-2038 Tanel Poder [0x.tools]

#include "syscall/syscall.bpf.h"
#include "xcapture.h"
#include "xcapture_config.h"
#include "xcapture_helpers.h"
#include "maps/xcapture_maps_common.h"

char LICENSE[] SEC("license") = "Dual BSD/GPL";

#define TRACE_COPY_LEN TRACE_PAYLOAD_LEN

struct rw_capture_state {
    void *buf;
    __u64 len;
    __s32 fd;
    __u8  is_write;
};

static bool __always_inline get_rw_capture_state(long syscall_nr, struct pt_regs *regs,
                                                 struct rw_capture_state *out)
{
    __u64 len = 0;
    void *buf = NULL;
    __s32 fd = -1;
    __u8 is_write = 0;

    switch (syscall_nr) {
    case __NR_read:
#ifdef __NR_pread64
    case __NR_pread64:
#endif
        fd = (__s32) PT_REGS_PARM1_CORE_SYSCALL(regs);
        buf = (void *) PT_REGS_PARM2_CORE_SYSCALL(regs);
        len = PT_REGS_PARM3_CORE_SYSCALL(regs);
        break;
    case __NR_recvfrom:
        fd = (__s32) PT_REGS_PARM1_CORE_SYSCALL(regs);
        buf = (void *) PT_REGS_PARM2_CORE_SYSCALL(regs);
        len = PT_REGS_PARM3_CORE_SYSCALL(regs);
        break;
#ifdef __NR_recv
    case __NR_recv:
        fd = (__s32) PT_REGS_PARM1_CORE_SYSCALL(regs);
        buf = (void *) PT_REGS_PARM2_CORE_SYSCALL(regs);
        len = PT_REGS_PARM3_CORE_SYSCALL(regs);
        break;
#endif
    case __NR_write:
#ifdef __NR_pwrite64
    case __NR_pwrite64:
#endif
        fd = (__s32) PT_REGS_PARM1_CORE_SYSCALL(regs);
        buf = (void *) PT_REGS_PARM2_CORE_SYSCALL(regs);
        len = PT_REGS_PARM3_CORE_SYSCALL(regs);
        is_write = 1;
        break;
    case __NR_sendto:
        fd = (__s32) PT_REGS_PARM1_CORE_SYSCALL(regs);
        buf = (void *) PT_REGS_PARM2_CORE_SYSCALL(regs);
        len = PT_REGS_PARM3_CORE_SYSCALL(regs);
        is_write = 1;
        break;
#ifdef __NR_send
    case __NR_send:
        fd = (__s32) PT_REGS_PARM1_CORE_SYSCALL(regs);
        buf = (void *) PT_REGS_PARM2_CORE_SYSCALL(regs);
        len = PT_REGS_PARM3_CORE_SYSCALL(regs);
        is_write = 1;
        break;
#endif
    default:
        return false;
    }

    if (!buf || len == 0 || fd < 0)
        return false;

    out->buf = buf;
    out->len = len;
    out->fd = fd;
    out->is_write = is_write;
    return true;
}

// If a userspace task is entering io_*getevents, check if there are any
// I/Os inflight in that ring or it's just an "idle" wait for work to show up
// NOTE: this won't work in the task_iterator program context (yet) as it needs
// to read userspace memory of other processes. TODO: 5.18 has xcap_copy_from_user_task()
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
int BPF_PROG(xcap_sys_enter, struct pt_regs *regs, long syscall_nr)
{
    struct task_storage *storage;
    struct task_struct *task = bpf_get_current_task_btf();
    if (!task)
        return 0;

    storage = bpf_task_storage_get(&task_storage, task, NULL, BPF_LOCAL_STORAGE_GET_F_CREATE);
    if (!storage)
        return 0;

    storage->state.sc_enter_time = bpf_ktime_get_ns();
    storage->state.in_syscall_nr = syscall_nr;
    storage->state.sc_sequence_num++;

    if (syscall_nr == __NR_io_getevents || syscall_nr == __NR_io_pgetevents) {
        __u64 ctx_id = PT_REGS_PARM1_CORE_SYSCALL(regs); // aio ctx_id (process-wide mem addr)
        storage->state.aio_inflight_reqs = get_num_inflight_aios_ring(ctx_id);
    }

    if (xcap_capture_rw_payloads) {
        struct rw_capture_state state = {};

        storage->cache.pending_trace_buf = 0;
        storage->cache.pending_trace_len = 0;
        storage->cache.pending_trace_syscall = -1;
        storage->cache.pending_trace_fd = -1;
        storage->cache.pending_trace_is_write = 0;

        if (get_rw_capture_state(syscall_nr, regs, &state)) {
            __u32 copy_len = state.len > TRACE_COPY_LEN ? TRACE_COPY_LEN : (__u32) state.len;
            storage->cache.pending_trace_buf = (__u64) state.buf;
            storage->cache.pending_trace_len = copy_len;
            storage->cache.pending_trace_syscall = syscall_nr;
            storage->cache.pending_trace_fd = state.fd;
            storage->cache.pending_trace_is_write = state.is_write;
        }
    }

    return 0;
}

SEC("tp_btf/sys_exit")
int BPF_PROG(xcap_sys_exit, struct pt_regs *regs, long ret)
{
    struct task_storage *storage;
    struct task_struct *task = bpf_get_current_task_btf();
    storage = bpf_task_storage_get(&task_storage, task, NULL,
                                  BPF_LOCAL_STORAGE_GET_F_CREATE);
    if (!storage)
        return 0;

    if (xcap_capture_rw_payloads) {
        __u64 buf_addr = storage->cache.pending_trace_buf;
        __s32 pending_nr = storage->cache.pending_trace_syscall;
        __u32 requested_len = storage->cache.pending_trace_len;
        __s32 pending_fd = storage->cache.pending_trace_fd;
        storage->cache.pending_trace_buf = 0;
        storage->cache.pending_trace_len = 0;
        storage->cache.pending_trace_syscall = -1;
        storage->cache.pending_trace_fd = -1;
        storage->cache.pending_trace_is_write = 0;

        storage->state.trace_payload_len = 0;

        if (!buf_addr || requested_len == 0 || pending_nr != storage->state.in_syscall_nr)
            goto skip_payload_copy;

        if (ret <= 0)
            goto skip_payload_copy;

        if (pending_fd < 0)
            goto skip_payload_copy;

        __u32 copy_len = requested_len;
        if ((__u64) ret < copy_len)
            copy_len = (__u32) ret;
        if (copy_len > TRACE_COPY_LEN)
            copy_len = TRACE_COPY_LEN;
        if (copy_len == 0)
            goto skip_payload_copy;

        storage->state.trace_payload_len = copy_len;
        int err = bpf_probe_read_user(storage->state.trace_payload, copy_len, (void *) buf_addr);
        if (err != 0) {
            storage->state.trace_payload_len = 0;
            storage->state.trace_payload_syscall = -1;
            storage->state.trace_payload_seq_num = (unsigned long long)(-err);
        } else {
            storage->state.trace_payload_syscall = pending_nr;
            storage->state.trace_payload_seq_num = storage->state.sc_sequence_num;
        }

skip_payload_copy:
        ;
    } else {
        storage->state.trace_payload_len = 0;
        storage->state.trace_payload_syscall = -1;
        storage->state.trace_payload_seq_num = 0;
    }

    if (!storage->state.sc_sampled) { // only emit syscalls caught by task sampler
        return 0;
    } else {
        struct sc_completion_event *scevent;
        scevent = bpf_ringbuf_reserve(&completion_events, sizeof(*scevent), 0);

        if (scevent) {
            __builtin_memset(scevent, 0, sizeof(*scevent));

            __u64 exit_time = bpf_ktime_get_ns();
            __u32 payload_len = storage->state.trace_payload_len;
            __s32 payload_syscall = storage->state.trace_payload_syscall;
            __u64 payload_seq = storage->state.trace_payload_seq_num;

            if (payload_len > TRACE_PAYLOAD_LEN)
                payload_len = TRACE_PAYLOAD_LEN;

            scevent->type = EVENT_SYSCALL_COMPLETION;  // Set scevent type

            // if storage->state.sc_sampled above is true, then storage->state.pid/tgid
            // have been put in place by task sampler already too
            scevent->pid = storage->state.pid;
            scevent->tgid = storage->state.tgid;
            scevent->completed_syscall_nr = storage->state.in_syscall_nr;
            scevent->completed_sc_sequence_num = storage->state.sc_sequence_num;
            scevent->completed_sc_enter_time = storage->state.sc_enter_time;
            scevent->completed_sc_exit_time = exit_time;
            scevent->completed_sc_ret_val = ret;

            scevent->trace_payload_len = payload_len;
            scevent->trace_payload_syscall = payload_syscall;
            scevent->trace_payload_seq_num = payload_seq;

            if (payload_len > 0) {
                if (bpf_probe_read_kernel(scevent->trace_payload,
                                          payload_len,
                                          storage->state.trace_payload) != 0) {
                    scevent->trace_payload_len = 0;
                    scevent->trace_payload_syscall = -1;
                    scevent->trace_payload_seq_num = 0;
                }
            }

            bpf_ringbuf_submit(scevent, 0);
        }
    }

    // clear sampled status as the syscall exits
    storage->state.sc_sampled = false;
    storage->state.in_syscall_nr = -1;
    // storage->state.sc_enter_time = 0;
    return 0;
}
