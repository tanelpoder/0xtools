// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
// Copyright 2024-2038 Tanel Poder [0x.tools]

#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "xcapture.h"
#include "xcapture_maps.h"
#include "xcapture_helpers.h"
#include "helpers/file_helpers.h"

#if defined(__TARGET_ARCH_arm64)
#include "syscall_aarch64.h"
#include "syscall_fd_bitmap_aarch64.h"
#elif defined(__TARGET_ARCH_x86)
#include "syscall_x86_64.h"
#include "syscall_fd_bitmap_x86_64.h"
#endif


char LICENSE[] SEC("license") = "Dual BSD/GPL";
char VERSION[] = "3.0.0";
extern int LINUX_KERNEL_VERSION __kconfig;

#define PAGE_SIZE 4096
#define EAGAIN    11

// Version-adaptive task state field retrieval
static __u32 __always_inline get_task_state(void *arg)
{
    if (bpf_core_field_exists(struct task_struct___pre514, state)) {
        struct task_struct___pre514 *task = arg;
        return task->state;
    } else {
        struct task_struct___post514 *task = arg;
        return task->__state;
    }
}

// Interesting task filtering for task iterator
static bool __always_inline should_emit_task(__u32 task_state, struct filter_config *cfg,
                                             __s32 syscall_nr, __u32 aio_inflight_reqs)
{
    if (!cfg)
        return true;  // If we can't find config, show everything

    if (cfg->show_all)
        return true;

    // Filter out TASK_INTERRUPTIBLE state tasks by default unless a task in
    // SLEEP state is waiting for a recently submitted async I/O completion
    if ((syscall_nr == __NR_io_getevents || syscall_nr == __NR_io_pgetevents) && aio_inflight_reqs)
    {
        return true;
    }

    if (task_state & TASK_INTERRUPTIBLE) {
        return false;
    }

    return true;
}


SEC("iter/task")
int get_tasks(struct bpf_iter__task *ctx)
{
    // we can replace this map with libbpf program arguments
    struct filter_config *cfg;
    const __u32 key = 0;
    cfg = bpf_map_lookup_elem(&filter_config_map, &key);

    // use the same timestamp for each record returned from a task iterator loop
    static __u64 this_iter_loop_start_ktime;

    if (ctx->meta->seq_num == 0) {
        this_iter_loop_start_ktime = bpf_ktime_get_ns();
    }

    struct task_struct *task = ctx->task;
    if (!task)
        return 0;

    // Early filtering of uninteresting tasks
    __u32 task_state = get_task_state(task);
    __u32 task_flags = task->flags;

    // exclude idle kernel threads
    if ((task_flags & PF_KTHREAD) && (task_state & TASK_IDLE))
        return 0;

    // Get task storage early to check for interesting tasks
    struct task_storage *storage;
    storage = bpf_task_storage_get(&task_storage, task, NULL, BPF_LOCAL_STORAGE_GET_F_CREATE);
    if (!storage)
        return 0;

    if (!storage->pid) storage->pid = task->pid;
    if (!storage->tgid) storage->tgid = task->tgid;

    // Check if we are in a syscall (as active syscall probes may be disabled)
    __s32 passive_syscall_nr = -1; // uninitialized (valid syscall numbers start from 0)
    struct pt_regs *passive_regs = NULL;

    // kernel threads don't issue syscalls
    if (!(task_flags & PF_KTHREAD) && task->stack) {
        passive_regs = (struct pt_regs *) bpf_task_pt_regs(task);

        if (passive_regs) {

#if defined(__TARGET_ARCH_x86)
            // max val 511 to make verifier on older kernels happy
            // this issue showed up probably due to refactoring to separate x86/arm .h files
            // so that some macros are behind ifdefs now - or it's just an older kernel issue (TODO)
            passive_syscall_nr = (__s32) passive_regs->orig_ax & 0x1ffUL;
#elif defined(__TARGET_ARCH_arm64)
            passive_syscall_nr = (__s32) passive_regs->syscallno & 0x1ffUL;
#endif

        }
    }

    // Apply user-controlled interesting task filtering
    if (!should_emit_task(task_state, cfg, passive_syscall_nr, storage->aio_inflight_reqs))
        return 0;

    // By this point we know the task/state is interesting
    // Sample task, populate sample timestamps first
    storage->sample_start_ktime = this_iter_loop_start_ktime;
    storage->sample_actual_ktime = bpf_ktime_get_ns();

    // Mark any ongoing tracepoint-captured syscall as "sampled" so we get completion events later
    if (passive_syscall_nr >= 0) {
        storage->in_syscall_nr = passive_syscall_nr;
        storage->sc_sampled = true;

        // syscall entry time is 0 only for syscalls already ongoing when xcapture started
        // so set it to current sample timestamp, so we'll know the partial duration when sc ends
        if (!storage->sc_enter_time) {
            storage->sc_enter_time = storage->sample_actual_ktime;
        }
    }

    // Reserve space in output ring buffer and start populating it
    // Important: We are reusing existing ringbuf space, so pages are not zero-filled
    struct task_output_event *event;
    event = bpf_ringbuf_reserve(&task_samples, sizeof(*event), 0);
    if (!event) {
        return 0;
    }

    // Basic task information
    event->type = EVENT_TASK_INFO;
    event->pid = task->pid;   // to avoid confusion, use TID and TGID in userspace output
    event->tgid = task->tgid; // kernel pid == TID (thread ID) in userspace for threads
                              // kernel tgid == TGID (thread group ID) for processes

    // Scheduler state info (volatile fast changing values)
    event->flags = task_flags;
    event->state = task_state;
    event->on_cpu = task->on_cpu;
    event->on_rq = task->on_rq;
    event->migration_pending = task->migration_pending;
    event->in_execve = BPF_CORE_READ_BITFIELD(task, in_execve);
    event->in_iowait = BPF_CORE_READ_BITFIELD(task, in_iowait);

    // Conditional reads based on kernel version
    if (bpf_core_field_exists(task->sched_remote_wakeup))
        event->sched_remote_wakeup = BPF_CORE_READ_BITFIELD(task, sched_remote_wakeup);

    // Reset syscall nr and args due to ringbuffer reuse
    event->syscall_nr = passive_syscall_nr;
    __builtin_memset(event->syscall_args, 0, sizeof(event->syscall_args));
    __u64 sc1_arg = 0;

    // if in syscall, read syscall number and args, otherwise skip
    if (passive_syscall_nr >= 0 && passive_regs) {
        //
#if defined(__TARGET_ARCH_x86)
        // TODO both sections below can be optimized (yay!)
        bpf_probe_read_kernel(&sc1_arg, sizeof(sc1_arg), &passive_regs->di);
        bpf_probe_read_kernel(&event->syscall_args[0], sizeof(event->syscall_args[0]), &passive_regs->di);
        bpf_probe_read_kernel(&event->syscall_args[1], sizeof(event->syscall_args[1]), &passive_regs->si);
        bpf_probe_read_kernel(&event->syscall_args[2], sizeof(event->syscall_args[2]), &passive_regs->dx);
        bpf_probe_read_kernel(&event->syscall_args[3], sizeof(event->syscall_args[3]), &passive_regs->r10);
        bpf_probe_read_kernel(&event->syscall_args[4], sizeof(event->syscall_args[4]), &passive_regs->r8);
        bpf_probe_read_kernel(&event->syscall_args[5], sizeof(event->syscall_args[5]), &passive_regs->r9);
#elif defined(__TARGET_ARCH_arm64)
        bpf_probe_read_kernel(&event->syscall_args[0], sizeof(event->syscall_args[0]), &passive_regs->regs[1]);
        bpf_probe_read_kernel(&event->syscall_args[1], sizeof(event->syscall_args[1]), &passive_regs->regs[2]);
        bpf_probe_read_kernel(&event->syscall_args[2], sizeof(event->syscall_args[2]), &passive_regs->regs[3]);
        bpf_probe_read_kernel(&event->syscall_args[3], sizeof(event->syscall_args[3]), &passive_regs->regs[4]);
        bpf_probe_read_kernel(&event->syscall_args[4], sizeof(event->syscall_args[4]), &passive_regs->regs[5]);
        bpf_probe_read_kernel(&event->syscall_args[5], sizeof(event->syscall_args[5]), &passive_regs->regs[6]);
#endif
        //
    }

    // username, comm and other slower changing metadata
    // (TODO: add more metadata like: namespace id, cgroup name, etc)
    event->euid = task->cred->euid.val;
    BPF_CORE_READ_STR_INTO(&event->comm, task, comm);

    // executable file name for userspace apps (kernel tasks don't set task->mm)
    if (task->mm) {
        get_file_name(task->mm->exe_file, event->exe_file, sizeof(event->exe_file), "[NO_EXE]");
    } else {
        __builtin_memcpy(event->exe_file, "[NO_MM]", 8);
    }

    // first reset the output values due to conditional population below (and ringbuf reuse!)
    event->kstack_len = 0;
    event->filename[0] = '-';
    event->filename[1] = '\0';
    event->has_socket_info = false;

    // Read file descriptor information for current syscall
    if  (passive_syscall_nr >=0 && SYSCALL_HAS_FD_ARG1(passive_syscall_nr)) {
        struct file *file = NULL;
        struct files_struct *files = BPF_CORE_READ(task, files);

        if (files) {
            struct fdtable *fdt = BPF_CORE_READ(files, fdt);
            struct file **fd_array = BPF_CORE_READ(fdt, fd);

            if (fd_array) {
                if (event->syscall_args[0] >= 0 && event->syscall_args[0] < 1024) { // TODO remove this
                    bpf_probe_read_kernel(&file, sizeof(file), &fd_array[event->syscall_args[0]]);
                }
            }
        }

        if (file) {
            get_file_name(file, event->filename, sizeof(event->filename), "-");
        }

        // Try to get socket information
        if (file) {
            struct inode *inode = BPF_CORE_READ(file, f_path.dentry, d_inode);
            if (inode) {
                // unsigned short i_mode = BPF_CORE_READ(inode, i_mode);
                unsigned short i_mode = BPF_CORE_READ(inode, i_mode);
                // Check if file is of socket type (S_IFSOCK == 0140000)
                if ((i_mode & S_IFMT) == S_IFSOCK) {
                    event->has_socket_info = get_socket_info(file, &event->sock_info);
                }
            }
        }
    }

    // Track iorq info if relevant: iorq struct addresses get quickly reused in kernel
    // by any task in the system. iorq pointers are not unique over time so need
    // to compare kernel-provided iorq insert/issue time with our tracked state.
    // this is because we don't clear the storage->last_iorq_rq in iorq completion tracepoint
    if (storage->last_iorq_rq) {
        storage->last_iorq_sampled = storage->last_iorq_rq;
        // storage->last_iorq_sampled_insert_ns = storage->last_iorq_insert_ns;
        // storage->last_iorq_sampled_issue_ns = storage->last_iorq_issue_ns;

        struct iorq_info *iorq_info = bpf_map_lookup_elem(&iorq_tracking, &storage->last_iorq_sampled);

        // First make sure that the iorq struct in this memory address is caused by *this* task's
        // last iorq (and not reused by another request). Not using iorq_sequence num here as iorq
        // addr + pid + high precision timestamps should be ok for differentiating (for now).
        // If the iorq addr + pid + insert or issue ts are the same in the iorq map and task
        // storage, then this is indeed our I/O at this iorq memory address (populated by
        // the independently running tracepoints), so it's ok to mark the iorq sampled.

        if (iorq_info && iorq_info->insert_pid == task->pid &&
            iorq_info->iorq_sequence_num == storage->iorq_sequence_num) {
                iorq_info->iorq_sampled = true;
        }
    }
    // if (iorq_info->insert_time == storage->last_iorq_sampled_insert_ns) {

    __builtin_memcpy(&event->storage, storage, sizeof(event->storage));
    bpf_ringbuf_submit(event, 0);

    return 0;
}
