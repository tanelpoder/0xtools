// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024-2038 Tanel Poder [0x.tools]

#ifndef __IO_HELPERS_H
#define __IO_HELPERS_H

#include <vmlinux.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_tracing.h>

#include "xcapture.h"
#include "../probes/xcapture_config.h"
#include "file_helpers.h"
#include "../utils/xcapture_helpers.h"

#if defined(__TARGET_ARCH_arm64)
#include "syscall_aarch64.h"
#elif defined(__TARGET_ARCH_x86)
#include "syscall_x86_64.h"
#endif

// io_uring fixed file flag
#define IOSQE_FIXED_FILE 0x01

// Helper to get filename from file descriptor
static __always_inline struct file *get_file_from_fd(struct files_struct *files, int fd)
{
    if (!files || fd < 0)
        return NULL;

    struct fdtable *fdt = files->fdt;
    if (!fdt)
        return NULL;

    unsigned int max_fds = BPF_CORE_READ(fdt, max_fds);
    if (max_fds && (unsigned int)fd >= max_fds)
        return NULL;

    struct file **fd_array = fdt->fd;
    if (!fd_array)
        return NULL;

    struct file *file = NULL;
    bpf_probe_read_kernel(&file, sizeof(file), &fd_array[fd]);
    return file;
}

static void __always_inline get_fd_filename(struct task_struct *task, int fd, char *filename, size_t size)
{
    struct file *file = get_file_from_fd(task->files, fd);

    if (file) {
        get_file_name(file, filename, size, "-");
    } else {
        filename[0] = '\0';
    }
}

#ifdef OLD_KERNEL_SUPPORT
static __always_inline struct file *resolve_io_uring_fixed_file(struct io_ring_ctx *ctx, __s32 idx)
{
    return NULL;
}
#else
static __always_inline struct file *resolve_io_uring_fixed_file(struct io_ring_ctx *ctx, __s32 idx)
{
    if (!ctx || idx < 0)
        return NULL;
    void *table_ptr = (void *)&ctx->file_table;
    int bitmap_off = bpf_core_field_offset(struct io_file_table, bitmap);
    if (bitmap_off < 0)
        return NULL;

    if (bitmap_off == (int)sizeof(void *)) {
        /* Legacy layout: file_table.files points to io_fixed_file entries */
        struct io_fixed_file *files = NULL;
        if (bpf_probe_read_kernel(&files, sizeof(files), table_ptr) != 0 || !files)
            return NULL;

        struct io_fixed_file fixed_entry = {};
        if (bpf_probe_read_kernel(&fixed_entry, sizeof(fixed_entry), &files[idx]) != 0)
            return NULL;

        if (!fixed_entry.file_ptr)
            return NULL;

        return (struct file *)fixed_entry.file_ptr;
    }

    if (bitmap_off < (int)(2 * sizeof(void *)))
        return NULL;

    /* Modern layout: first field embeds io_rsrc_data { nr, nodes } */
    unsigned int nr = 0;
    if (bpf_probe_read_kernel(&nr, sizeof(nr), table_ptr) != 0)
        return NULL;
    if ((unsigned int)idx >= nr)
        return NULL;

    struct io_rsrc_node **nodes = NULL;
    int nodes_off = bitmap_off - (int)sizeof(void *);
    if (bpf_probe_read_kernel(&nodes, sizeof(nodes), (__u8 *)table_ptr + nodes_off) != 0 || !nodes)
        return NULL;

    struct io_rsrc_node *node = NULL;
    if (bpf_probe_read_kernel(&node, sizeof(node), &nodes[idx]) != 0 || !node)
        return NULL;

    /* io_rsrc_node layout stores file_ptr 16 bytes from base (after type, refs, tag) */
    unsigned long file_ptr = 0;
    const int file_ptr_off = 16;
    if (bpf_probe_read_kernel(&file_ptr, sizeof(file_ptr), (__u8 *)node + file_ptr_off) != 0)
        return NULL;

    if (!file_ptr)
        return NULL;

    return (struct file *)file_ptr;
}
#endif

static void __always_inline uring_track_request(struct task_storage *storage,
                                                __u64 user_data,
                                                __s32 fd,
                                                __s32 reg_idx,
                                                __u64 file_ptr)
{
    if (!storage)
        return;

    storage->cache.uring_last_user_data = user_data;
    storage->cache.uring_last_fd = fd;
    storage->cache.uring_last_reg_idx = reg_idx;
    storage->cache.uring_last_file_ptr = file_ptr;
}

static __u64 __always_inline uring_lookup_tracked_file(const struct task_storage *storage,
                                                       __u64 user_data)
{
    if (!storage)
        return 0;

    if (storage->cache.uring_last_user_data != user_data)
        return 0;

    return storage->cache.uring_last_file_ptr;
}

// Helper to calculate io_uring SQ and CQ pending counts and get sample filenames for both queues
#ifdef OLD_KERNEL_SUPPORT
static void __always_inline get_io_uring_pending_counts(struct file *ring_file, struct task_struct *task,
                                                        __u32 *sq_pending_out, __u32 *cq_pending_out,
                                                        char *sqe_filename, size_t sq_filename_size,
                                                        char *cqe_filename, size_t cq_filename_size,
                                                        struct task_storage *storage,
                                                        struct task_output_event *event)
{
    if (sq_pending_out)
        *sq_pending_out = 0;
    if (cq_pending_out)
        *cq_pending_out = 0;

    if (sqe_filename && sq_filename_size > 0)
        sqe_filename[0] = '\0';
    if (cqe_filename && cq_filename_size > 0)
        cqe_filename[0] = '\0';

    if (storage) {
        storage->cache.uring_last_user_data = 0;
        storage->cache.uring_last_fd = -1;
        storage->cache.uring_last_reg_idx = -1;
        storage->cache.uring_last_file_ptr = 0;
    }

    if (event) {
        event->uring_dbg_sq_idx = -9;
        event->uring_dbg_sq_fixed = 0;
        event->uring_dbg_sq_user_data = 0;
        event->uring_dbg_sq_file_ptr = 0;
        event->uring_dbg_cq_scanned = 0;
        event->uring_dbg_cq_matched = 0;
        event->uring_dbg_cq_file_ptr = 0;
    }
}
#else
static void __always_inline get_io_uring_pending_counts(struct file *ring_file, struct task_struct *task,
                                                        __u32 *sq_pending_out, __u32 *cq_pending_out,
                                                        char *sqe_filename, size_t sq_filename_size,
                                                        char *cqe_filename, size_t cq_filename_size,
                                                        struct task_storage *storage,
                                                        struct task_output_event *event)
{
    if (sq_pending_out)
        *sq_pending_out = 0;
    if (cq_pending_out)
        *cq_pending_out = 0;

    if (sqe_filename && sq_filename_size > 0)
        sqe_filename[0] = '\0';
    if (cqe_filename && cq_filename_size > 0)
        cqe_filename[0] = '\0';

    if (!ring_file || !task)
        return;

    struct io_ring_ctx *ctx = BPF_CORE_READ(ring_file, private_data);
    if (!ctx)
        return;

    struct io_rings *rings = BPF_CORE_READ(ctx, rings);
    if (!rings)
        return;

    __u32 sq_head = BPF_CORE_READ(rings, sq.head);
    __u32 sq_tail = BPF_CORE_READ(rings, sq.tail);
    __u32 sq_mask = BPF_CORE_READ(rings, sq_ring_mask);

    __u32 cq_head = BPF_CORE_READ(rings, cq.head);
    __u32 cq_tail = BPF_CORE_READ(rings, cq.tail);
    __u32 cq_mask = BPF_CORE_READ(rings, cq_ring_mask);

    __u32 sq_pending = 0;
    if (sq_tail >= sq_head)
        sq_pending = sq_tail - sq_head;
    else
        sq_pending = (sq_mask + 1) - sq_head + sq_tail;

    if (event) {
        event->uring_dbg_cq_scanned = 0;
        event->uring_dbg_cq_matched = 0;
        event->uring_dbg_cq_file_ptr = 0;
    }

    if (sq_pending_out)
        *sq_pending_out = sq_pending;
    if (storage && sq_pending == 0) {
        storage->cache.uring_last_user_data = 0;
        storage->cache.uring_last_file_ptr = 0;
        storage->cache.uring_last_fd = -1;
        storage->cache.uring_last_reg_idx = -1;
    }

    __u32 cq_pending_calc = 0;
    if (cq_tail >= cq_head)
        cq_pending_calc = cq_tail - cq_head;
    else
        cq_pending_calc = (cq_mask + 1) - cq_head + cq_tail;

    if (cq_pending_out)
        *cq_pending_out = cq_pending_calc;

    if (sqe_filename && sq_filename_size > 0) {
        __u32 *sq_array = BPF_CORE_READ(ctx, sq_array);
        struct io_uring_sqe *sqes = BPF_CORE_READ(ctx, sq_sqes);

        bool has_sq_array = sq_array != NULL;
        bool has_sqes = sqes != NULL;

        if (!has_sqes) {
            if (event)
                event->uring_dbg_sq_idx = -7;
        } else if (sq_tail > 0 || cq_pending_calc > 0) {
            __u32 last_sq_idx = (sq_tail > 0) ? ((sq_tail - 1) & sq_mask) : 0;
            __u32 sqe_idx = 0;
            bool sqe_valid = true;

            if (!has_sq_array) {
                sqe_idx = last_sq_idx;
            } else {
                bool sqe_idx_loaded = false;
                bool tried_task_copy = false;

                if (task) {
                    tried_task_copy = true;
                    if (xcap_copy_from_user_task(&sqe_idx, sizeof(sqe_idx),
                                                &sq_array[last_sq_idx], task, 0) == 0)
                        sqe_idx_loaded = true;
                }

                if (!sqe_idx_loaded) {
                    if (bpf_probe_read_user(&sqe_idx, sizeof(sqe_idx), &sq_array[last_sq_idx]) == 0 ||
                        bpf_probe_read_kernel(&sqe_idx, sizeof(sqe_idx), &sq_array[last_sq_idx]) == 0)
                        sqe_idx_loaded = true;
                }

                if (!sqe_idx_loaded) {
                    sqe_valid = false;
                    if (event)
                        event->uring_dbg_sq_idx = tried_task_copy ? -3 : -2;
                }
            }

            struct io_uring_sqe sqe = {};
            if (sqe_valid) {
                bool sqe_loaded = false;
                bool tried_task_copy_sqe = false;

                if (task) {
                    tried_task_copy_sqe = true;
                    if (xcap_copy_from_user_task(&sqe, sizeof(sqe), &sqes[sqe_idx], task, 0) == 0)
                        sqe_loaded = true;
                }

                if (!sqe_loaded) {
                    if (bpf_probe_read_user(&sqe, sizeof(sqe), &sqes[sqe_idx]) == 0 ||
                        bpf_probe_read_kernel(&sqe, sizeof(sqe), &sqes[sqe_idx]) == 0)
                        sqe_loaded = true;
                }

                if (!sqe_loaded) {
                    sqe_valid = false;
                    if (event)
                        event->uring_dbg_sq_idx = tried_task_copy_sqe ? -3 : -2;
                }
            }

            if (!sqe_valid) {
                if (event)
                event->uring_dbg_sq_idx = (event->uring_dbg_sq_idx < 0)
                                              ? event->uring_dbg_sq_idx
                                              : -2;
            } else {
                bool is_fixed_file = (sqe.flags & IOSQE_FIXED_FILE) != 0;
                __s32 fd = sqe.fd;
                __s32 reg_idx = -1;
                struct file *file = NULL;

                if (event) {
                    event->uring_dbg_sq_idx = sqe_idx;
                    event->uring_dbg_sq_fixed = is_fixed_file ? 1 : 0;
                    event->uring_dbg_sq_user_data = sqe.user_data;
                }

                if (is_fixed_file) {
                    reg_idx = fd;
                    file = resolve_io_uring_fixed_file(ctx, reg_idx);

                    if (file)
                        get_file_name(file, sqe_filename, sq_filename_size, "-");
                    else if (sq_filename_size > 5) {
                        sqe_filename[0] = '[';
                        sqe_filename[1] = 'r';
                        sqe_filename[2] = 'e';
                        sqe_filename[3] = 'g';
                        sqe_filename[4] = ']';
                        sqe_filename[5] = '\0';
                    }

                    if (event) {
                        event->uring_fd = -1;
                        event->uring_reg_idx = reg_idx;
                    }

                    uring_track_request(storage, sqe.user_data, -1, reg_idx, (__u64)file);
                } else {
                    if (fd >= 0)
                        file = get_file_from_fd(task->files, fd);

                    if (file)
                        get_file_name(file, sqe_filename, sq_filename_size, "-");
                    else if (sq_filename_size > 0)
                        sqe_filename[0] = '\0';

                    if (event) {
                        event->uring_fd = fd;
                        event->uring_reg_idx = -1;
                    }

                    uring_track_request(storage, sqe.user_data, fd, -1, (__u64)file);
                }

                if (event) {
                    event->uring_opcode = sqe.opcode;
                    event->uring_flags = sqe.flags;
                    event->uring_offset = sqe.off;
                    event->uring_len = sqe.len;
                    event->uring_rw_flags = sqe.rw_flags;
                    event->uring_dbg_sq_file_ptr = (__u64)file;
                }
            }
        } else if (event) {
            event->uring_dbg_sq_idx = -5;
        }
    }

    if (cqe_filename && cq_filename_size > 0 && cq_pending_calc > 0 && storage) {
        const __u32 max_scan = 8;
        __u32 to_scan = cq_pending_calc;
        if (to_scan > max_scan)
            to_scan = max_scan;

        struct io_uring_cqe *cqes = BPF_CORE_READ(rings, cqes);
        if (cqes) {
            for (int i = 0; i < max_scan; i++) {
            if (i >= to_scan)
                break;

            __u32 idx = (cq_head + i) & cq_mask;

            struct io_uring_cqe cqe;
            if (bpf_probe_read_user(&cqe, sizeof(cqe), &cqes[idx]) != 0 &&
                bpf_probe_read_kernel(&cqe, sizeof(cqe), &cqes[idx]) != 0)
                continue;

            if (event) {
                event->uring_dbg_cq_scanned = i + 1;
            }

            __u64 file_ptr = uring_lookup_tracked_file(storage, cqe.user_data);

            if ((!file_ptr) && storage && storage->cache.uring_last_user_data == cqe.user_data) {
                if (storage->cache.uring_last_reg_idx >= 0) {
                    struct file *reg_file = resolve_io_uring_fixed_file(ctx, storage->cache.uring_last_reg_idx);
                    if (reg_file) {
                        file_ptr = (__u64)reg_file;
                        storage->cache.uring_last_file_ptr = file_ptr;
                    }
                } else if (storage->cache.uring_last_fd >= 0) {
                    struct file *file_retry = get_file_from_fd(task->files,
                                                               storage->cache.uring_last_fd);
                    if (file_retry) {
                        file_ptr = (__u64)file_retry;
                        storage->cache.uring_last_file_ptr = file_ptr;
                    }
                }
            }

            if (!file_ptr)
                continue;

            struct file *file = (struct file *)file_ptr;
            get_file_name(file, cqe_filename, cq_filename_size, "-");

            if (event) {
                event->uring_dbg_cq_matched = 1;
                event->uring_dbg_cq_file_ptr = (__u64)file;
            }

            break;
            }
        } else if (event) {
            event->uring_dbg_cq_scanned = -1;
        }
    }
}
#endif

// Helper to check io_uring fd for daemon port
static __u16 __always_inline check_io_uring_daemon_ports(struct pt_regs *regs, struct task_struct *task);

// Helper to get io_uring sqe info
static int __always_inline get_io_uring_sqe_info(struct pt_regs *regs, struct task_struct *task,
                                                  int *fd_out, struct file **file_out, __u8 *opcode_out)
{

    __u64 ring_fd;
    __u32 to_submit;

    // Get io_uring_enter arguments
#if defined(__TARGET_ARCH_x86)
    ring_fd = regs->di;       // arg1: fd
    to_submit = regs->si;     // arg2: to_submit
#elif defined(__TARGET_ARCH_arm64)
    ring_fd = regs->regs[0];
    to_submit = regs->regs[1];
#endif

    // Validate ring_fd and to_submit
    if (ring_fd >= 1024 || to_submit == 0)
        return -1;

    // Get the io_uring file from the file descriptor
    struct file *ring_file = NULL;
    struct files_struct *files = task->files;

    if (files)
        ring_file = get_file_from_fd(files, ring_fd);

    if (!ring_file)
        return -1;

    // Try to access io_uring context through file->private_data
    *fd_out = (int)ring_fd;
    *file_out = ring_file;
    *opcode_out = 0; // TODO read the actual opcode

    return 0;
}

// Helper to get first fd from AIO syscalls (io_getevents/io_pgetevents/io_submit)
#ifdef OLD_KERNEL_SUPPORT
static int __always_inline get_aio_first_fd_info(struct pt_regs *regs, struct task_struct *task,
                                                  int *fd_out, struct file **file_out)
{
    return -1;
}
#else
static int __always_inline get_aio_first_fd_info(struct pt_regs *regs, struct task_struct *task,
                                                  int *fd_out, struct file **file_out)
{

    __u64 ctx_id;
    __s64 nr;
    __u64 iocbpp_ptr = 0;  // For io_submit
    __u64 events_ptr = 0;  // For io_getevents

    // Get syscall number to determine which arguments to read
    __s32 syscall_nr;
#if defined(__TARGET_ARCH_x86)
    syscall_nr = regs->orig_ax;
#elif defined(__TARGET_ARCH_arm64)
    syscall_nr = regs->syscallno;
#endif

    // Handle io_submit differently
    if (syscall_nr == __NR_io_submit) {
        // io_submit(ctx_id, nr, iocbpp)
#if defined(__TARGET_ARCH_x86)
        ctx_id = regs->di;          // arg1: aio context
        nr = regs->si;              // arg2: nr
        iocbpp_ptr = regs->dx;      // arg3: array of iocb pointers
#elif defined(__TARGET_ARCH_arm64)
        ctx_id = regs->regs[0];
        nr = regs->regs[1];
        iocbpp_ptr = regs->regs[2];
#endif

        // For io_submit, read the first iocb pointer from the array
        if (iocbpp_ptr && nr > 0) {
            struct iocb *iocb_ptr;
            // Read first pointer from the array
            if (xcap_copy_from_user_task(&iocb_ptr, sizeof(iocb_ptr), (void *)iocbpp_ptr, task, 0) == 0) {
                if (iocb_ptr) {
                    struct iocb {
                        __u64 aio_data;
                        __u32 aio_key;
                        __u32 aio_rw_flags;
                        __u16 aio_lio_opcode;
                        __s16 aio_reqprio;
                        __u32 aio_fildes;
                    } iocb;

                    if (xcap_copy_from_user_task(&iocb, sizeof(iocb), (void *)iocb_ptr, task, 0) == 0) {
                        int fd = iocb.aio_fildes;
                        if (fd > 0 && fd < 1024) {
                            // Get file from fd
                            struct file *file = NULL;
                            struct files_struct *files = task->files;

                            if (files) {
                                struct fdtable *fdt = files->fdt;
                                struct file **fd_array = fdt ? fdt->fd : NULL;

                                if (fd_array) {
                                    bpf_probe_read_kernel(&file, sizeof(file), &fd_array[fd]);
                                }
                            }

                            *fd_out = fd;
                            *file_out = file;
                            return 0;
                        }
                    }
                }
            }
        }
        return -1;
    }

    // Handle io_getevents/io_pgetevents
    __s64 min_nr;
#if defined(__TARGET_ARCH_x86)
    ctx_id = regs->di;        // arg1: aio context
    min_nr = regs->si;        // arg2: min_nr
    nr = regs->dx;            // arg3: nr
    events_ptr = regs->cx;    // arg4: events (rcx for syscalls)
#elif defined(__TARGET_ARCH_arm64)
    ctx_id = regs->regs[0];
    min_nr = regs->regs[1];
    nr = regs->regs[2];
    events_ptr = regs->regs[3];
#endif

    if (!ctx_id)
        return -1;

    // First, try to read directly from the AIO ring to find any pending iocb
    // The AIO ring contains completed events. Let's walk through the ring
    // to find ANY iocb, not just the ones being returned by this call
    struct aio_ring {
        unsigned id;
        unsigned nr;        // Total size of the ring (number of io_events)
        unsigned head;      // Head index (userspace writes here)
        unsigned tail;      // Tail index (kernel writes here)
        // We don't need the rest of the structure
    } ring;

    if (xcap_copy_from_user_task(&ring, sizeof(ring), (void *)ctx_id, task, 0) != 0)
        return -1;

    // The io_events array starts right after the aio_ring header
    __u64 event_offset = sizeof(struct aio_ring);


    // Try to find ANY io_event in the ring (bounded loop for verifier)
    for (int i = 0; i < 16; i++) {  // Check up to 16 entries
        if (i >= ring.nr)  // Don't go beyond ring size
            break;

        unsigned idx = (ring.tail + i) % ring.nr;  // Start from tail (oldest entries)

        struct io_event {
            __u64 data;
            __u64 obj;    // Pointer to original iocb
            __s64 res;
            __s64 res2;
        } ring_event;

        // Calculate offset for this entry
        __u64 entry_offset = event_offset + (idx * sizeof(struct io_event));

        if (xcap_copy_from_user_task(&ring_event, sizeof(ring_event),
                                    (void *)(ctx_id + entry_offset), task, 0) == 0) {
            if (ring_event.obj) {
                struct iocb {
                    __u64 aio_data;
                    __u32 aio_key;
                    __u32 aio_rw_flags;
                    __u16 aio_lio_opcode;
                    __s16 aio_reqprio;
                    __u32 aio_fildes;  // This is the file descriptor
                } iocb;

                if (xcap_copy_from_user_task(&iocb, sizeof(iocb), (void *)ring_event.obj, task, 0) == 0) {
                    int fd = iocb.aio_fildes;
                    // Debug: Let's check what we're actually reading
                    // Store the opcode in fd_out temporarily to debug
                    if (fd == 0 && iocb.aio_lio_opcode > 0) {
                        // If fd is 0 but we have a valid opcode, the structure might be misaligned
                        // Try reading just the fd field at the expected offset
                        __u32 fd_only;
                        if (xcap_copy_from_user_task(&fd_only, sizeof(fd_only),
                                                    (void *)((char *)ring_event.obj + 20), task, 0) == 0) {
                            fd = fd_only;
                        }
                    }

                    if (fd >= 0 && fd < 1024) {
                        // Get file from fd
                        struct file *file = NULL;
                        struct files_struct *files = task->files;

                        if (files) {
                            struct fdtable *fdt = BPF_CORE_READ(files, fdt);
                            struct file **fd_array = BPF_CORE_READ(fdt, fd);

                            if (fd_array) {
                                bpf_probe_read_kernel(&file, sizeof(file), &fd_array[fd]);
                            }
                        }

                        *fd_out = fd;
                        *file_out = file;
                        return 0;
                    }
                }
            }
        }
    }

    // If we still couldn't find anything, try the events array if it was provided
    if (events_ptr && nr > 0) {
        struct io_event {
            __u64 data;
            __u64 obj;    // Pointer to original iocb
            __s64 res;
            __s64 res2;
        } event;

        // Read first io_event from userspace
        if (xcap_copy_from_user_task(&event, sizeof(event), (void *)events_ptr, task, 0) == 0) {
            // Now read the iocb structure that event.obj points to
            if (event.obj) {
                struct iocb {
                    __u64 aio_data;
                    __u32 aio_key;
                    __u32 aio_rw_flags;
                    __u16 aio_lio_opcode;
                    __s16 aio_reqprio;
                    __u32 aio_fildes;  // This is the file descriptor
                } iocb;

                if (xcap_copy_from_user_task(&iocb, sizeof(iocb), (void *)event.obj, task, 0) == 0) {
                    int fd = iocb.aio_fildes;
                    if (fd >= 0 && fd < 1024) {
                        // Get file from fd
                        struct file *file = NULL;
                        struct files_struct *files = task->files;

                        if (files) {
                            struct fdtable *fdt = BPF_CORE_READ(files, fdt);
                            struct file **fd_array = BPF_CORE_READ(fdt, fd);

                            if (fd_array) {
                                bpf_probe_read_kernel(&file, sizeof(file), &fd_array[fd]);
                            }
                        }

                        *fd_out = fd;
                        *file_out = file;
                        return 0;
                    }
                }
            }
        }
    }

    return -1;
}
#endif

// Helper function to calculate number of inflight AIO requests in a ring
// For use in task iterator context with xcap_copy_from_user_task()
#ifdef OLD_KERNEL_SUPPORT
static __u32 __always_inline get_aio_inflight_count_task(__u64 ctx_id, struct task_struct *task)
{
    return 0;
}
#else
static __u32 __always_inline get_aio_inflight_count_task(__u64 ctx_id, struct task_struct *task)
{
    if (!ctx_id || !task) return 0;

    struct aio_ring {
        unsigned id;
        unsigned nr;
        unsigned head;
        unsigned tail;
    } ring;

    // Read the aio_ring structure from userspace
    if (xcap_copy_from_user_task(&ring, sizeof(ring), (void *)ctx_id, task, 0) != 0)
        return 0;

    // Calculate inflight requests
    // Note: Due to race conditions in passive sampling, we might read inconsistent
    // head/tail values, which can result in negative values being shown
    if (ring.tail >= ring.head) {
        return ring.tail - ring.head;
    } else {
        // Handle wrap-around case
        return (UINT32_MAX - ring.head) + ring.tail + 1;
    }
}
#endif

// Include fd_helpers.h for check_fd_port function
#include "fd_helpers.h"

// Implementation of check_io_uring_daemon_ports (needs check_fd_port from fd_helpers.h)
static __u16 __always_inline check_io_uring_daemon_ports(struct pt_regs *regs, struct task_struct *task)
{

    int fd;
    struct file *file;
    __u8 opcode;

    if (get_io_uring_sqe_info(regs, task, &fd, &file, &opcode) != 0)
        return 0;

    return check_fd_port(fd, task);
}

#endif // __IO_HELPERS_H
