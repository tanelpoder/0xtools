#include "io/iorq.bpf.h"
#include "xcapture.h"
#include "xcapture_helpers.h"

char LICENSE[] SEC("license") = "Dual BSD/GPL";

// In the "simple" IO request tracking mode, trying avoid and delay work
// as much as possible to the request completion tracepoint, as we only
// need to process completion if an in-flight request happened to be sampled
// while in-flight

// Block I/O request insertion handler (does not fire if it's bypassed for direct dispatch)
SEC("tp_btf/block_rq_insert")
int BPF_PROG(block_rq_insert, struct request *rq)
{
    struct task_struct *task = bpf_get_current_task_btf();
    struct task_storage *storage;
    storage = bpf_task_storage_get(&task_storage, task, NULL, BPF_LOCAL_STORAGE_GET_F_CREATE);
    // if can't get task storage object, something is broken, no point in accounting iorqs
    if (!storage)
        return 0;

    // ensure zero fill of reused memory as we don't populate all members here
    // this also sets iorq_info.iorq_sampled = false
    struct iorq_info iorq_info = {0};

    storage->last_iorq_rq = rq;

    // every task has its private sequence counting, incremented only here or iorq issue tp
    iorq_info.iorq_sequence_num = ++storage->iorq_sequence_num;
    iorq_info.insert_pid = task->pid;
    iorq_info.insert_tgid = task->tgid;

    bpf_map_update_elem(&iorq_tracking, &rq, &iorq_info, BPF_ANY);

    return 0;
}

// Block I/O request *issue* handler (may run under a different task than request inserter)
SEC("tp_btf/block_rq_issue")
int BPF_PROG(block_rq_issue, struct request *rq)
{
    struct task_struct *task = bpf_get_current_task_btf();
    struct task_storage *storage;
    storage = bpf_task_storage_get(&task_storage, task, NULL, BPF_LOCAL_STORAGE_GET_F_CREATE);
    if (!storage)
        return 0;

    // iorq INSERT tracepoint may not always get hit, some I/Os can go directly to ISSUE stage
    // check if request is already inserted into the OS I/O queue previously
    struct iorq_info *iorq_info = bpf_map_lookup_elem(&iorq_tracking, &rq);

    if (iorq_info) {
        // iorq_info->issue_time = rq->io_start_time_ns; // issue to device driver
        iorq_info->issue_pid = task->pid;
        iorq_info->issue_tgid = task->tgid;
    }
    // request issued/dispatched directly without inserting to a queue first
    // so set the iorq map entry up from scratch (insert_pid same as issue_pid)
    else {
        struct iorq_info new_iorq_info = {0}; // deliberate zero fill

        storage->last_iorq_rq = rq;

        // as we skipped insert, increment the task-private iorq sequence counter here
        new_iorq_info.iorq_sequence_num = ++storage->iorq_sequence_num;
        new_iorq_info.insert_pid = task->pid;
        new_iorq_info.insert_tgid = task->tgid;
        new_iorq_info.issue_pid = task->pid;
        new_iorq_info.issue_tgid = task->tgid;

        bpf_map_update_elem(&iorq_tracking, &rq, &new_iorq_info, BPF_ANY);
    }

    return 0;
}

// block IORQ completion tracepoint that emits a completion record to ringbuf only
// if the task sampler has marked the currently completing I/O as "sampled"
SEC("tp_btf/block_rq_complete")
int BPF_PROG(block_rq_complete, struct request *rq, int error, unsigned int nr_bytes)
{
    // process completion event only after all bios under this IO request are completed
    if (nr_bytes < rq->__data_len)
        return 0;

    // check if this I/O was sampled
    struct iorq_info *iorq_info = bpf_map_lookup_elem(&iorq_tracking, &rq);
    // no tracked IO found, nothing to do
    if (!iorq_info)
        return 0;

    // if this I/O request wasn't sampled by task iterator while in-flight, then do not emit
    if (!iorq_info->iorq_sampled)
        goto cleanup;

    // allocate ringbuf memory for emitting event
    struct iorq_completion_event *event;
    event = bpf_ringbuf_reserve(&completion_events, sizeof(*event), 0);
    if (!event)
        goto cleanup;

    // populate all output struct fields to avoid stale garbage values in ringbuf
    // need CORE for rq for RHEL9 / kernel 5.14 verifier
    event->type = EVENT_IORQ_COMPLETION;
    event->insert_pid = iorq_info->insert_pid;
    event->insert_tgid = iorq_info->insert_tgid;
    event->issue_pid = iorq_info->issue_pid;
    event->issue_tgid = iorq_info->issue_tgid;
    event->iorq_sequence_num = iorq_info->iorq_sequence_num;
    event->iorq_complete_time = bpf_ktime_get_ns(); // current time for completion
    event->iorq_sector = BPF_CORE_READ(rq, __sector);
    event->iorq_bytes = BPF_CORE_READ(rq, __data_len);
    event->iorq_cmd_flags = BPF_CORE_READ(rq, cmd_flags);
    event->iorq_insert_time = BPF_CORE_READ(rq, start_time_ns);
    event->iorq_issue_time = BPF_CORE_READ(rq, io_start_time_ns);
    event->iorq_error = error; // tracepoint argument
    // if rq->q->disk is found, convert it to device maj/min numbers
    event->iorq_dev = 0;
    struct gendisk *disk = BPF_CORE_READ(rq, q, disk);
    if (disk)
        event->iorq_dev = MKDEV(BPF_CORE_READ(disk, major), BPF_CORE_READ(disk, first_minor));

    bpf_ringbuf_submit(event, 0);

cleanup:
    // delete the iorq tracking map element regardless of its sampling status
    bpf_map_delete_elem(&iorq_tracking, &rq);
    return 0;
}



/*
   This is the original completion tracepoint I was using until RHEL 9.5 tests showed its
   verifier didn't like it (function calls "spilling" the *rq argument from registers to
   stack/memory and it lost its BTF type info afterwards. I'll make this switch dynamic
   as a special case for RHEL 5.14.x kernels (or just RHEL's kernel if needed).

   You can comment out the tracepoint above and uncomment the tracepoint below if you want
   to play with.
*/

/*
SEC("tp_btf/block_rq_complete")
int BPF_PROG(block_rq_complete, struct request *rq, int error, unsigned int nr_bytes)
{
    // process completion event only after all bios under this IO request are completed
    if (nr_bytes < rq->__data_len)
        return 0;

    struct iorq_info *iorq_info = bpf_map_lookup_elem(&iorq_tracking, &rq);
    // no tracked IO found, nothing to do
    if (!iorq_info)
        return 0;

    // if this I/O request wasn't sampled by task iterator while in-flight, then do not emit
    if (!iorq_info->iorq_sampled)
        goto cleanup;

    // allocate ringbuf memory for emitting event
    struct iorq_completion_event *event;
    event = bpf_ringbuf_reserve(&completion_events, sizeof(*event), 0);
    if (!event)
        goto cleanup;

    event->type = EVENT_IORQ_COMPLETION;

    event->insert_pid = iorq_info->insert_pid;
    event->insert_tgid = iorq_info->insert_tgid;
    event->issue_pid = iorq_info->issue_pid;
    event->issue_tgid = iorq_info->issue_tgid;
    event->iorq_sequence_num = iorq_info->iorq_sequence_num;
    event->iorq_insert_time = rq->start_time_ns;
    event->iorq_issue_time = rq->io_start_time_ns;
    event->iorq_complete_time = bpf_ktime_get_ns(); // current time for completion

    // if rq->q->disk is found, convert it to device maj/min numbers
    struct gendisk *disk = rq->q->disk;
    if (disk)
        event->iorq_dev = MKDEV(disk->major, disk->first_minor);

    event->iorq_sector = rq->__sector;
    event->iorq_bytes = rq->__data_len;
    event->iorq_cmd_flags = rq->cmd_flags;
    event->iorq_error = error; // tracepoint argument

    bpf_ringbuf_submit(event, 0);

cleanup:
    // delete the iorq tracking map element regardless of its sampling status
    bpf_map_delete_elem(&iorq_tracking, &rq);
    return 0;
}
*/
