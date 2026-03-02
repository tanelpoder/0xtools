// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause

#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>

#include "xcapture.h"
#include "xcapture_config.h"
#include "maps/xcapture_maps_common.h"
#include "maps/xcapture_maps_iorq_classic.h"
#include "xcapture_helpers.h"

char LICENSE[] SEC("license") = "Dual BSD/GPL";

// Classic hashtable-based I/O request tracking

SEC("tp_btf/block_rq_insert")
int BPF_PROG(xcap_iorq_insert, struct request *rq)
{
    struct task_struct *task = bpf_get_current_task_btf();
    struct task_storage *storage = bpf_task_storage_get(&task_storage, task, NULL, BPF_LOCAL_STORAGE_GET_F_CREATE);
    if (!storage)
        return 0;

    struct iorq_info info = {0};
    storage->state.last_iorq_rq = rq;
    info.iorq_sequence_num = ++storage->state.iorq_sequence_num;
    info.insert_pid = task->pid;
    info.insert_tgid = task->tgid;
    bpf_map_update_elem(&iorq_tracking, &rq, &info, BPF_ANY);
    return 0;
}

SEC("tp_btf/block_rq_issue")
int BPF_PROG(xcap_iorq_issue, struct request *rq)
{
    struct task_struct *task = bpf_get_current_task_btf();
    struct task_storage *storage = bpf_task_storage_get(&task_storage, task, NULL, BPF_LOCAL_STORAGE_GET_F_CREATE);
    if (!storage)
        return 0;

    struct iorq_info *info = bpf_map_lookup_elem(&iorq_tracking, &rq);
    if (info) {
        info->issue_pid = task->pid;
        info->issue_tgid = task->tgid;
    } else {
        struct iorq_info ni = {0};
        storage->state.last_iorq_rq = rq;
        ni.iorq_sequence_num = ++storage->state.iorq_sequence_num;
        ni.insert_pid = task->pid;
        ni.insert_tgid = task->tgid;
        ni.issue_pid = task->pid;
        ni.issue_tgid = task->tgid;
        bpf_map_update_elem(&iorq_tracking, &rq, &ni, BPF_ANY);
    }
    return 0;
}

SEC("tp_btf/block_rq_complete")
int BPF_PROG(xcap_iorq_complete, struct request *rq, int error, unsigned int nr_bytes)
{
    if (nr_bytes < rq->__data_len)
        return 0;

    struct iorq_info *iorq_info = bpf_map_lookup_elem(&iorq_tracking, &rq);
    if (!iorq_info)
        return 0;
    if (!iorq_info->iorq_sampled)
        goto cleanup;

    struct iorq_completion_event *event = bpf_ringbuf_reserve(&completion_events, sizeof(*event), 0);
    if (!event)
        goto cleanup;

    event->type = EVENT_IORQ_COMPLETION;
    event->rq = rq;
    event->insert_pid = iorq_info->insert_pid;
    event->insert_tgid = iorq_info->insert_tgid;
    event->issue_pid = iorq_info->issue_pid;
    event->issue_tgid = iorq_info->issue_tgid;
    event->iorq_sequence_num = iorq_info->iorq_sequence_num;
    event->iorq_complete_time = bpf_ktime_get_ns();
    event->iorq_sector =      BPF_CORE_READ(rq, __sector);          //  rq->__sector;
    event->iorq_bytes =       BPF_CORE_READ(rq, __data_len);        //  rq->__data_len;
    event->iorq_cmd_flags =   BPF_CORE_READ(rq, cmd_flags);         //  rq->cmd_flags;
    event->iorq_insert_time = BPF_CORE_READ(rq, start_time_ns);     //  rq->start_time_ns;
    event->iorq_issue_time =  BPF_CORE_READ(rq, io_start_time_ns);  //  rq->io_start_time_ns;
    event->iorq_error = error;
    event->iorq_dev = 0;
    struct gendisk *disk = BPF_CORE_READ(rq, q) ? BPF_CORE_READ(rq, q, disk) : NULL;
    if (disk)
        event->iorq_dev = MKDEV(BPF_CORE_READ(disk, major), BPF_CORE_READ(disk, first_minor));

    bpf_ringbuf_submit(event, 0);

cleanup:
    bpf_map_delete_elem(&iorq_tracking, &rq);
    return 0;
}
