// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
// Copyright 2024-2038 Tanel Poder [0x.tools]

#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "xcapture.h"
#include "maps/xcapture_maps_common.h"
#include "maps/xcapture_maps_iorq_classic.h"
#include "xcapture_config.h"
#include "xcapture_helpers.h"
#include "helpers/file_helpers.h"
#include "helpers/tcp_helpers_simple.h"
#include "helpers/fd_helpers.h"
#include "helpers/io_helpers.h"

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

// Queue-based I/O tracking has been removed - using classic hashtable approach only

// Interesting task filtering for task iterator
static bool __always_inline should_emit_task(__u32 task_state,
                                             __s32 syscall_nr, __u32 aio_inflight_reqs,
                                             __u32 io_uring_sq_pending, __u32 io_uring_cq_pending,
                                             __u16 read_local_port_num)
{
    if (xcap_show_all)
        return true;

    // Filter out TASK_INTERRUPTIBLE state tasks by default unless a task in
    // SLEEP state is waiting for a recently submitted async I/O completion
    if ((syscall_nr == __NR_io_getevents || syscall_nr == __NR_io_pgetevents) && aio_inflight_reqs)
    {
        return true;
    }

    // Show tasks in io_uring_enter syscall with pending I/O
    if (syscall_nr == __NR_io_uring_enter && (io_uring_sq_pending > 0 || io_uring_cq_pending > 0))
    {
        return true;
    }

    if (task_state & TASK_INTERRUPTIBLE) {
        // Check daemon port logic for READ operations on TCP/UDP sockets
        if (read_local_port_num > 0 && is_read_syscall(syscall_nr)) {
            // Special case: if read_local_port_num is 1, it means LISTEN socket
            if (read_local_port_num == 1) {
                // This is a daemon waiting on a LISTEN socket - skip it
                return false;
            }
            if (read_local_port_num <= xcap_daemon_ports) {
                // This is a daemon waiting for work - skip it
                return false;
            }
            // else: local_port > daemon_ports, this is an active client - include it
            return true;
        }
        // Not a READ operation on a socket, filter out sleeping task
        return false;
    }

    return true;
}


SEC("iter.s/task")  // Sleepable iterator for modern kernels
int get_tasks(struct bpf_iter__task *ctx)
{
    // use the same timestamp for each record returned from a task iterator loop
    static __u64 this_iter_loop_start_ktime;

    if (ctx->meta->seq_num == 0) {
        this_iter_loop_start_ktime = bpf_ktime_get_ns();

        // Initialization at start of iteration
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

    // TGID filtering is now done at kernel iterator level when -p option is used

    // Skip xcapture itself (it's always on CPU when sampling)
    if (xcap_xcapture_pid > 0 && task->tgid == xcap_xcapture_pid)
        return 0;

    // Get task storage early to check for interesting tasks
    struct task_storage *storage;
    storage = bpf_task_storage_get(&task_storage, task, NULL, BPF_LOCAL_STORAGE_GET_F_CREATE);
    if (!storage)
        return 0;

    if (!storage->state.pid) storage->state.pid = task->pid;
    if (!storage->state.tgid) storage->state.tgid = task->tgid;

    // Initialize variables used for stack optimization
    __u64 nvcsw = 0;
    __u64 nivcsw = 0;
    __u64 total_ctxsw = 0;
    bool can_use_cached_stack = false;

    // Only read context switch counts if stack traces are enabled
    if (xcap_dump_kernel_stack_traces || xcap_dump_user_stack_traces) {
        // Read context switch counts for stack trace optimization
        nvcsw = task->nvcsw;
        nivcsw = task->nivcsw;
        total_ctxsw = nvcsw + nivcsw;

        // Determine if we can use cached stacks:
        // - If total_ctxsw == storage->state.last_total_ctxsw AND task is not on CPU, use cached stack
        // - If total_ctxsw != storage->state.last_total_ctxsw, task has done work, need fresh stack
        // - If task is on CPU, always need fresh stack regardless of ctxsw count
        can_use_cached_stack = !task->on_cpu && (total_ctxsw == storage->state.last_total_ctxsw);

        // Update context switch tracking
        storage->state.nvcsw = nvcsw;
        storage->state.nivcsw = nivcsw;
    }

    // Check if we are in a syscall (as active syscall probes may be disabled)
    __s32 passive_syscall_nr = -1; // uninitialized (valid syscall numbers start from 0)
    struct pt_regs *passive_regs = NULL;


    // kernel threads don't issue syscalls
    if (!(task_flags & PF_KTHREAD) && task->stack) {
        passive_regs = (struct pt_regs *) bpf_task_pt_regs(task);

        if (passive_regs) {

#if defined(__TARGET_ARCH_x86)
            // Check if orig_ax is -1 (not in syscall) before masking
            // We need to preserve -1 as a special value
            __s64 orig_ax = (__s64) passive_regs->orig_ax;
            if (orig_ax == -1) {
                passive_syscall_nr = -1;
            } else {
                // max val 511 to make verifier on older kernels happy
                passive_syscall_nr = (__s32) (orig_ax & 0x1ffUL);
            }
#elif defined(__TARGET_ARCH_arm64)
            // Check if syscallno is -1 (not in syscall) before masking
            __s64 syscallno = (__s64) passive_regs->syscallno;
            if (syscallno == -1) {
                passive_syscall_nr = -1;
            } else {
                // max val 511 to make verifier on older kernels happy
                passive_syscall_nr = (__s32) (syscallno & 0x1ffUL);
            }
#endif

        }
    }

    // Read socket info early for daemon port filtering
    __u16 read_local_port_num = 0;

    // Special handling for ppoll syscall - check multiple fds
    if (passive_syscall_nr == __NR_ppoll && passive_regs) {
        read_local_port_num = check_ppoll_daemon_ports(passive_regs, task);
    }
    // Special handling for pselect6 syscall - check multiple fds
    else if (passive_syscall_nr == __NR_pselect6 && passive_regs) {
        read_local_port_num = check_pselect6_daemon_ports(passive_regs, task);
    }
    // Special handling for AIO syscalls - calculate inflight requests
    else if ((passive_syscall_nr == __NR_io_getevents || passive_syscall_nr == __NR_io_pgetevents ||
              passive_syscall_nr == __NR_io_submit || passive_syscall_nr == __NR_io_cancel ||
              passive_syscall_nr == __NR_io_destroy) && passive_regs) {
        // Only update aio_inflight_reqs on new kernels where we can read it
        // On old kernels, preserve the value set by syscall tracking (if enabled)
        __u64 ctx_id;
#if defined(__TARGET_ARCH_x86)
        ctx_id = passive_regs->di;
#elif defined(__TARGET_ARCH_arm64)
        ctx_id = passive_regs->regs[0];
#endif
        storage->state.aio_inflight_reqs = get_aio_inflight_count_task(ctx_id, task);
    }
    // Special handling for io_uring_enter syscall - check target fds
    else if (passive_syscall_nr == __NR_io_uring_enter && passive_regs) {
        read_local_port_num = check_io_uring_daemon_ports(passive_regs, task);

        // Also calculate io_uring inflight count early for filtering
        __u64 ring_fd;
#if defined(__TARGET_ARCH_x86)
        ring_fd = passive_regs->di;
#elif defined(__TARGET_ARCH_arm64)
        ring_fd = passive_regs->regs[0];
#endif

        if (ring_fd < 1024) {
            struct file *ring_file = NULL;
            struct files_struct *files = task->files;

            if (files) {
                struct fdtable *fdt = files->fdt;
                struct file **fd_array = fdt->fd;

                if (fd_array && ring_fd >= 0) {
                    bpf_probe_read_kernel(&ring_file, sizeof(ring_file), &fd_array[ring_fd]);
                }
            }

            if (ring_file) {
                get_io_uring_pending_counts(ring_file, task,
                                          &storage->state.io_uring_sq_pending,
                                          &storage->state.io_uring_cq_pending,
                                          NULL, 0, NULL);  // Don't need filename or event in first call
            }
        }
    }
    else if (passive_syscall_nr >= 0 && SYSCALL_HAS_FD_ARG1(passive_syscall_nr) && passive_regs) {
        struct file *file = NULL;
        struct files_struct *files = task->files;

        if (files) {
            struct fdtable *fdt = files->fdt;
            struct file **fd_array = fdt ? fdt->fd : NULL;

            if (fd_array) {
                __u64 fd_arg;
#if defined(__TARGET_ARCH_x86)
                fd_arg = passive_regs->di;
#elif defined(__TARGET_ARCH_arm64)
                fd_arg = passive_regs->regs[0];
#endif
                if (fd_arg >= 0 && fd_arg < 1024) {
                    bpf_probe_read_kernel(&file, sizeof(file), &fd_array[fd_arg]);
                }
            }
        }

        if (file) {
            struct inode *inode = BPF_CORE_READ(file, f_path.dentry, d_inode);
            if (inode) {
                unsigned short i_mode = BPF_CORE_READ(inode, i_mode);
                // Check if file is of socket type (S_IFSOCK == 0140000)
                if ((i_mode & S_IFMT) == S_IFSOCK) {
                    struct socket_info sock_info;
                    if (get_socket_info(file, &sock_info)) {
                        // Only filter on TCP/UDP sockets
                        if (sock_info.protocol == IPPROTO_TCP || sock_info.protocol == IPPROTO_UDP) {
                            // If it's a TCP socket in LISTEN state, set special value 1
                            if (sock_info.protocol == IPPROTO_TCP && sock_info.state == TCP_LISTEN) {
                                read_local_port_num = 1;  // Special value indicating LISTEN socket
                            } else {
                                read_local_port_num = bpf_ntohs(sock_info.sport);
                            }
                        }
                    }
                }
            }
        }
    }

    // Apply user-controlled interesting task filtering
    if (!should_emit_task(task_state, passive_syscall_nr, storage->state.aio_inflight_reqs,
                          storage->state.io_uring_sq_pending, storage->state.io_uring_cq_pending,
                          read_local_port_num))
        return 0;

    // By this point we know the task/state is interesting
    // Sample task, populate sample timestamps first
    storage->state.sample_start_ktime = this_iter_loop_start_ktime;
    storage->state.sample_actual_ktime = bpf_ktime_get_ns();

    // Populate namespace and cgroup IDs
    // PID namespace ID - using direct BTF pointer access
    if (task->nsproxy && task->nsproxy->pid_ns_for_children) {
        storage->state.pid_ns_id = task->nsproxy->pid_ns_for_children->ns.inum;
    } else {
        storage->state.pid_ns_id = 0;  // Fallback if nsproxy is NULL
    }

    // Cgroup v2 ID - walk through task->cgroups->dfl_cgrp->kn->id
    // dfl_cgrp is the default (v2) cgroup hierarchy
    if (task->cgroups && task->cgroups->dfl_cgrp && task->cgroups->dfl_cgrp->kn) {
        storage->state.cgroup_id = task->cgroups->dfl_cgrp->kn->id;
    } else {
        storage->state.cgroup_id = 0;  // Fallback if cgroup structures are NULL
    }

    // Mark any ongoing tracepoint-captured syscall as "sampled" so we get completion events later
    if (passive_syscall_nr >= 0) {

        storage->state.sc_sampled = true;

        // edge: syscall entry time is 0 only for syscalls already ongoing when xcapture started
        // so set it to current sample timestamp, so we'll know the partial duration when sc ends
        if (storage->state.sc_enter_time == 0) {
            storage->state.in_syscall_nr = passive_syscall_nr; // trust passive sample instead of tracepoint
            storage->state.sc_enter_time = storage->state.sample_actual_ktime;
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
    event->in_execve = BPF_CORE_READ_BITFIELD_PROBED(task, in_execve);
    event->in_iowait = BPF_CORE_READ_BITFIELD_PROBED(task, in_iowait);

    // Conditional reads based on kernel version
    if (bpf_core_field_exists(task->sched_remote_wakeup))
        event->sched_remote_wakeup = BPF_CORE_READ_BITFIELD_PROBED(task, sched_remote_wakeup);

    // Reset syscall nr and args due to ringbuffer reuse
    event->syscall_nr = passive_syscall_nr;
    __builtin_memset(event->syscall_args, 0, sizeof(event->syscall_args));
    __u64 sc1_arg = 0;

    // TODO: refactor the task_storage struct to hold a storage.state {} part and storage.cache {}
    // Copy task storage fields to output event using partial memcpy
    // We only copy up to (but not including) the cached stack fields,
    // which are internal to BPF and never used in userspace
    // This copies ~160 bytes instead of ~2040 bytes (avoiding the large stack arrays)
    event->storage = storage->state; // (shallow) copy the entire task_state struct

    // if in syscall, read syscall number and args, otherwise skip
    if (passive_syscall_nr >= 0 && passive_regs) {
        //
#if defined(__TARGET_ARCH_x86)
        // Direct dereference for pt_regs fields
        sc1_arg = passive_regs->di;
        event->syscall_args[0] = passive_regs->di;
        event->syscall_args[1] = passive_regs->si;
        event->syscall_args[2] = passive_regs->dx;
        event->syscall_args[3] = passive_regs->r10;
        event->syscall_args[4] = passive_regs->r8;
        event->syscall_args[5] = passive_regs->r9;
#elif defined(__TARGET_ARCH_arm64)
        event->syscall_args[0] = passive_regs->regs[0];
        event->syscall_args[1] = passive_regs->regs[1];
        event->syscall_args[2] = passive_regs->regs[2];
        event->syscall_args[3] = passive_regs->regs[3];
        event->syscall_args[4] = passive_regs->regs[4];
        event->syscall_args[5] = passive_regs->regs[5];
#endif
        //
    }

    // username, comm and other slower changing metadata
    // (TODO: add more metadata like: namespace id, cgroup name, etc)
    const struct cred *cred = task->cred;
    event->euid = cred->euid.val;
    bpf_probe_read_kernel_str(&event->comm, sizeof(event->comm), task->comm);

    // executable file name for userspace apps (kernel tasks don't set task->mm)
    if (task->mm) {
        get_file_name(task->mm->exe_file, event->exe_file, sizeof(event->exe_file), "[NO_EXE]");
    } else {
        __builtin_memcpy(event->exe_file, "[NO_MM]", 8);
    }

    // first reset the output values due to conditional population below (and ringbuf reuse!)
    event->kstack_hash = 0;  // 0 means no stack
    event->ustack_hash = 0;  // 0 means no stack
    event->filename[0] = '-';
    event->filename[1] = '\0';
    event->has_socket_info = false;
    event->has_tcp_stats = false;
    event->aio_fd = -1; // Initialize to -1 (no fd)
    event->ur_filename[0] = '\0'; // Initialize io_uring CQE filename
    event->aio_filename[0] = '\0'; // Initialize AIO filename
    event->uring_fd = -1; // Initialize to -1 (no fd)
    event->uring_reg_idx = -1; // Initialize to -1 (not registered)
    event->uring_offset = 0;
    event->uring_len = 0;
    event->uring_opcode = 0;
    event->uring_flags = 0;
    event->uring_rw_flags = 0;

    // Read file descriptor information for current syscall
    struct file *file = NULL;

    // Special handling for ppoll/pselect6 - get first fd info
    if (passive_syscall_nr == __NR_ppoll && passive_regs) {
        int fd;
        if (get_ppoll_first_fd_info(passive_regs, task, &fd, &file) == 0) {
            // Update syscall_args[0] to show the actual fd being monitored
            event->syscall_args[0] = fd;
        }
    }
    else if (passive_syscall_nr == __NR_pselect6 && passive_regs) {
        int fd;
        if (get_pselect6_first_fd_info(passive_regs, task, &fd, &file) == 0) {
            // Update syscall_args[0] to show the actual fd being monitored
            event->syscall_args[0] = fd;
        }
    }
    else if (passive_syscall_nr == __NR_io_uring_enter && passive_regs) {
        int fd;
        __u8 opcode;
        if (get_io_uring_sqe_info(passive_regs, task, &fd, &file, &opcode) == 0) {
            // Update syscall_args[0] to show the target fd from SQE
            event->syscall_args[0] = fd;
            // Store opcode in syscall_args[1] for visibility
            event->syscall_args[1] = opcode;
        }
    }
    else if ((passive_syscall_nr == __NR_io_getevents || passive_syscall_nr == __NR_io_pgetevents ||
              passive_syscall_nr == __NR_io_submit) && passive_regs) {
        int fd;
        if (get_aio_first_fd_info(passive_regs, task, &fd, &file) == 0) {
            // Update syscall_args[0] to show the actual fd being accessed via AIO
            event->syscall_args[0] = fd;
            // Store the extracted fd in aio_fd field for debugging
            event->aio_fd = fd;
            // Extract filename from the file pointer if we have it
            if (file) {
                get_file_name(file, event->aio_filename, sizeof(event->aio_filename), "-");
            }
        }
    }
    else if (passive_syscall_nr >= 0 && SYSCALL_HAS_FD_ARG1(passive_syscall_nr)) {
        // Regular single-fd syscalls
        struct files_struct *files = task->files;

        if (files) {
            struct fdtable *fdt = files->fdt;
            struct file **fd_array = fdt ? fdt->fd : NULL;

            if (fd_array) {
                if (event->syscall_args[0] >= 0 && event->syscall_args[0] < 1024) {
                    bpf_probe_read_kernel(&file, sizeof(file), &fd_array[event->syscall_args[0]]);
                }
            }
        }
    }

    // Common file handling for all syscalls with file info
    if (file) {
        get_file_name(file, event->filename, sizeof(event->filename), "-");

        // Try to get socket information
        struct inode *inode = BPF_CORE_READ(file, f_path.dentry, d_inode);
        if (inode) {
            unsigned short i_mode = BPF_CORE_READ(inode, i_mode);
            // Check if file is of socket type (S_IFSOCK == 0140000)
            if ((i_mode & S_IFMT) == S_IFSOCK) {
                event->has_socket_info = get_socket_info(file, &event->sock_info);

                // If we got socket info and it's a TCP socket, get TCP stats
                if (event->has_socket_info && should_collect_tcp_stats(&event->sock_info)) {
                    struct socket *sock = BPF_CORE_READ(file, private_data);
                    if (sock) {
                        struct sock *sk = BPF_CORE_READ(sock, sk);
                        if (sk) {
                            event->has_tcp_stats = get_tcp_stats(sk, &event->tcp_stats);
                        }
                    }
                }
            }
        }
    }

    // If we're in io_uring_enter syscall and have pending CQEs, populate ur_filename with last submitted fd
    if (passive_syscall_nr == __NR_io_uring_enter && storage->state.io_uring_cq_pending > 0 && passive_regs) {
        __u64 ring_fd;
#if defined(__TARGET_ARCH_x86)
        ring_fd = passive_regs->di;
#elif defined(__TARGET_ARCH_arm64)
        ring_fd = passive_regs->regs[0];
#endif

        if (ring_fd < 1024) {
            struct file *ring_file = NULL;
            struct files_struct *files = task->files;

            if (files) {
                struct fdtable *fdt = files->fdt;
                struct file **fd_array = fdt->fd;

                if (fd_array && ring_fd >= 0) {
                    bpf_probe_read_kernel(&ring_file, sizeof(ring_file), &fd_array[ring_fd]);
                }
            }

            if (ring_file) {
                // Call the function again to get SQE filename
                __u32 sq_pending_dummy, cq_pending_dummy;
                get_io_uring_pending_counts(ring_file, task,
                                          &sq_pending_dummy,
                                          &cq_pending_dummy,
                                          event->ur_filename,
                                          sizeof(event->ur_filename),
                                          event);
            }
        }
    }

    // Track iorq info if relevant: iorq struct addresses get quickly reused in kernel
    // by any task in the system. iorq pointers are not unique over time so need
    // to compare kernel-provided iorq insert/issue time with our tracked state.
    // this is because we don't clear the storage->state.last_iorq_rq in iorq completion tracepoint
    if (storage->state.last_iorq_rq) {
        storage->state.last_iorq_sampled = storage->state.last_iorq_rq;
        storage->state.last_iorq_dev_sampled = storage->state.last_iorq_dev;
        storage->state.last_iorq_sector_sampled = storage->state.last_iorq_sector;
        storage->state.last_iorq_sequence_num = storage->state.iorq_sequence_num;
        // storage->state.last_iorq_sampled_insert_ns = storage->last_iorq_insert_ns;
        // storage->state.last_iorq_sampled_issue_ns = storage->last_iorq_issue_ns;

        // Mark tracked iorq as sampled in the hashtable
        struct iorq_info *iorq_info = bpf_map_lookup_elem(&iorq_tracking, &storage->state.last_iorq_sampled);
        if (iorq_info && iorq_info->insert_pid == task->pid &&
            iorq_info->iorq_sequence_num == storage->state.iorq_sequence_num) {
            iorq_info->iorq_sampled = true;
        }
    }

    // Collect kernel stack trace if requested
    if (xcap_dump_kernel_stack_traces) {
        // Only read fresh stack if task was scheduled or is on CPU
        if (!can_use_cached_stack || storage->cache.cached_kstack_len == 0) {
            // Read fresh stack trace
            int stack_len = bpf_get_task_stack(task, storage->cache.cached_kstack,
                                             sizeof(storage->cache.cached_kstack), 0);
            if (stack_len > 0) {
                storage->cache.cached_kstack_len = stack_len / sizeof(__u64);
                if (storage->cache.cached_kstack_len > MAX_STACK_LEN) {
                    storage->cache.cached_kstack_len = MAX_STACK_LEN;
                }
            } else {
                storage->cache.cached_kstack_len = 0;
            }
        }

        // Compute hash of the kernel stack and store in event
        if (storage->cache.cached_kstack_len > 0) {
            event->kstack_hash = get_stack_hash(storage->cache.cached_kstack, storage->cache.cached_kstack_len);

            // Copy hash to stack for old kernel verifier compatibility
            __u64 kstack_hash = event->kstack_hash;

            // Check if this stack has already been emitted
            __u8 *emitted = bpf_map_lookup_elem(&emitted_stacks, &kstack_hash);
            if (!emitted || *emitted != 1) {
                // New stack, send it through stack_traces ring buffer
                struct stack_trace_event *stack_event;
                stack_event = bpf_ringbuf_reserve(&stack_traces, sizeof(*stack_event), 0);
                if (stack_event) {
                    stack_event->type = EVENT_STACK_TRACE;
                    stack_event->stack_hash = event->kstack_hash;
                    stack_event->is_kernel = true;
                    stack_event->stack_len = storage->cache.cached_kstack_len;
                    stack_event->pid = task->pid;

                    // Copy stack addresses
                    for (int i = 0; i < MAX_STACK_LEN; i++) {
                        if (i < storage->cache.cached_kstack_len) {
                            stack_event->stack[i] = storage->cache.cached_kstack[i];
                        } else {
                            stack_event->stack[i] = 0;
                        }
                    }

                    bpf_ringbuf_submit(stack_event, 0);

                    // Mark as emitted
                    __u8 one = 1;
                    bpf_map_update_elem(&emitted_stacks, &kstack_hash, &one, BPF_ANY);
                }
            }
        }
    }

    // Collect userspace stack trace if requested
    #ifndef OLD_KERNEL_SUPPORT
    if (xcap_dump_user_stack_traces && !(event->flags & PF_KTHREAD)) {
        // Only read fresh stack if task was scheduled or is on CPU
        if (!can_use_cached_stack || storage->cache.cached_ustack_len == 0) {
            // Reset cached stack length
            storage->cache.cached_ustack_len = 0;

            // Get the current stack pointer from task's pt_regs
            struct pt_regs *regs = (struct pt_regs *)bpf_task_pt_regs(task);
            if (regs) {
                // Architecture-specific frame pointer unwinding
                #if defined(__TARGET_ARCH_x86)
                    // x86_64 stack frame layout:
                    // struct stack_frame {
                    //     void *rbp;  // next frame pointer
                    //     void *rip;  // return address
                    // };
                    __u64 fp = regs->bp;  // Frame pointer (RBP)
                    __u64 sp = regs->sp;  // Stack pointer (RSP)

                    // Unwind up to MAX_STACK_LEN frames
                    for (int i = 0; i < MAX_STACK_LEN && i < 20; i++) {
                        if (!fp || fp < sp || fp > sp + 0x100000) {
                            // Basic sanity check: fp should be above sp and within reasonable range
                            break;
                        }

                        // Read the stack frame
                        __u64 next_fp, ret_addr;
                        if (bpf_copy_from_user_task(&next_fp, sizeof(next_fp),
                                                    (void *)fp, task, 0) < 0) {
                            break;
                        }
                        if (bpf_copy_from_user_task(&ret_addr, sizeof(ret_addr),
                                                    (void *)(fp + 8), task, 0) < 0) {
                            break;
                        }

                        // Store the return address
                        storage->cache.cached_ustack[i] = ret_addr;
                        storage->cache.cached_ustack_len++;

                        // Move to next frame
                        fp = next_fp;
                    }
                #elif defined(__TARGET_ARCH_arm64)
                    // ARM64 frame pointer unwinding
                    // struct stack_frame {
                    //     void *fp;  // x29 - next frame pointer
                    //     void *lr;  // x30 - return address
                    // };
                    __u64 fp = regs->regs[29];  // Frame pointer (x29)
                    __u64 sp = regs->sp;        // Stack pointer

                    for (int i = 0; i < MAX_STACK_LEN && i < 20; i++) {
                        if (!fp || fp < sp || fp > sp + 0x100000) {
                            break;
                        }

                        // Read the stack frame
                        __u64 next_fp, ret_addr;
                        if (bpf_copy_from_user_task(&next_fp, sizeof(next_fp),
                                                    (void *)fp, task, 0) < 0) {
                            break;
                        }
                        if (bpf_copy_from_user_task(&ret_addr, sizeof(ret_addr),
                                                    (void *)(fp + 8), task, 0) < 0) {
                            break;
                        }

                        // Store the return address
                        storage->cache.cached_ustack[i] = ret_addr;
                        storage->cache.cached_ustack_len++;

                        // Move to next frame
                        fp = next_fp;
                    }
                #endif // target arch
            }
        }

        // Compute hash of the userspace stack and store in event
        if (storage->cache.cached_ustack_len > 0) {
            event->ustack_hash = get_stack_hash(storage->cache.cached_ustack, storage->cache.cached_ustack_len);

            // Copy hash to stack for old kernel verifier compatibility
            __u64 ustack_hash = event->ustack_hash;

            // Check if this stack has already been emitted
            __u8 *emitted = bpf_map_lookup_elem(&emitted_stacks, &ustack_hash);
            if (!emitted || *emitted != 1) {
                // New stack, send it through stack_traces ring buffer
                struct stack_trace_event *stack_event;
                stack_event = bpf_ringbuf_reserve(&stack_traces, sizeof(*stack_event), 0);
                if (stack_event) {
                    stack_event->type = EVENT_STACK_TRACE;
                    stack_event->stack_hash = event->ustack_hash;
                    stack_event->is_kernel = false;
                    stack_event->stack_len = storage->cache.cached_ustack_len;
                    stack_event->pid = task->pid;

                    // Copy stack addresses
                    for (int i = 0; i < MAX_STACK_LEN; i++) {
                        if (i < storage->cache.cached_ustack_len) {
                            stack_event->stack[i] = storage->cache.cached_ustack[i];
                        } else {
                            stack_event->stack[i] = 0;
                        }
                    }

                    bpf_ringbuf_submit(stack_event, 0);

                    // Mark as emitted
                    __u8 one = 1;
                    bpf_map_update_elem(&emitted_stacks, &ustack_hash, &one, BPF_ANY);
                }
            }
        }
    }
    #endif // !OLD_KERNEL_SUPPORT

    // Update last_total_ctxsw for next iteration (only if stack traces are enabled)
    if (xcap_dump_kernel_stack_traces || xcap_dump_user_stack_traces) {
        storage->state.last_total_ctxsw = total_ctxsw;
    }

    bpf_ringbuf_submit(event, 0);

    return 0;
}
