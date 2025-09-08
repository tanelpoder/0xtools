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

#if defined(__TARGET_ARCH_arm64)
#include "syscall_aarch64.h"
#elif defined(__TARGET_ARCH_x86)
#include "syscall_x86_64.h"
#endif

// io_uring fixed file flag
#define IOSQE_FIXED_FILE 0x01

// Helper to get filename from file descriptor
static void __always_inline get_fd_filename(struct task_struct *task, int fd, char *filename, size_t size)
{
    if (fd < 0 || fd >= 1024) {
        filename[0] = '\0';
        return;
    }

    struct files_struct *files = task->files;
    if (!files) {
        filename[0] = '\0';
        return;
    }

    struct fdtable *fdt = files->fdt;
    struct file **fd_array = fdt->fd;

    if (!fd_array) {
        filename[0] = '\0';
        return;
    }

    struct file *file = NULL;
    bpf_probe_read_kernel(&file, sizeof(file), &fd_array[fd]);

    if (file) {
        get_file_name(file, filename, size, "-");
    } else {
        filename[0] = '\0';
    }
}

// Helper to calculate io_uring SQ and CQ pending counts and get last submitted fd info
static void __always_inline get_io_uring_pending_counts(struct file *ring_file, struct task_struct *task,
                                                        __u32 *sq_pending_out, __u32 *cq_pending_out,
                                                        char *sqe_filename, size_t filename_size,
                                                        struct task_output_event *event)
{
    *sq_pending_out = 0;
    *cq_pending_out = 0;

    if (!ring_file || !task) {
        return;
    }

    // Get io_ring_ctx from file->private_data
    struct io_ring_ctx *ctx = BPF_CORE_READ(ring_file, private_data);
    if (!ctx) {
        return;
    }

    // Get the rings pointer from io_ring_ctx
    struct io_rings *rings = BPF_CORE_READ(ctx, rings);
    if (!rings) {
        return;
    }

    // Read SQ head
    // Note: The rings structure is shared between kernel and userspace
    // The head is updated by consumer (kernel for SQ), tail by producer (userspace for SQ)
    __u32 sq_head = BPF_CORE_READ(rings, sq.head);

    // Read SQ tail
    // For SQ: tail is written by userspace, head by kernel
    __u32 sq_tail = BPF_CORE_READ(rings, sq.tail);

    // Read SQ mask
    __u32 sq_mask = BPF_CORE_READ(rings, sq_ring_mask);

    // Read CQ head
    __u32 cq_head = BPF_CORE_READ(rings, cq.head);

    // Read CQ tail
    __u32 cq_tail = BPF_CORE_READ(rings, cq.tail);

    // Read CQ mask
    __u32 cq_mask = BPF_CORE_READ(rings, cq_ring_mask);

    // Calculate pending in submission queue (wrapping handled by masking)
    if (sq_tail >= sq_head) {
        *sq_pending_out = sq_tail - sq_head;
    } else {
        // Handle wrap around
        *sq_pending_out = (sq_mask + 1) - sq_head + sq_tail;
    }

    // Calculate completed but not reaped in completion queue
    __u32 cq_pending_calc = 0;
    if (cq_tail >= cq_head) {
        cq_pending_calc = cq_tail - cq_head;
    } else {
        // Handle wrap around
        cq_pending_calc = (cq_mask + 1) - cq_head + cq_tail;
    }
    *cq_pending_out = cq_pending_calc;


    // Calculations complete

    // Try to get the fd from the most recently submitted SQE
    if (sqe_filename && filename_size > 0) {
        // Initialize filename to empty
        sqe_filename[0] = '\0';

        // Get SQ array pointer from context
        __u32 *sq_array = BPF_CORE_READ(ctx, sq_array);
        if (!sq_array) {
            goto skip_sqe_read;
        }

        // Get SQE array pointer from context
        struct io_uring_sqe *sqes = BPF_CORE_READ(ctx, sq_sqes);
        if (!sqes) {
            goto skip_sqe_read;
        }

        // If there are any submissions (even if they've been consumed),
        // look at the most recent one. For pending CQs, check the submission
        // that led to them
        if (sq_tail > 0 || cq_pending_calc > 0) {
            // Get the index of the most recently submitted entry
            __u32 last_sq_idx = 0;
            if (sq_tail > 0) {
                last_sq_idx = (sq_tail - 1) & sq_mask;
            } else {
                // If sq_tail is 0 but we have completions, try index 0
                last_sq_idx = 0;
            }

            // Read the SQE index from the SQ array
            // Note: We must use bpf_probe_read_kernel here for dynamic array access
            __u32 sqe_idx = 0;
            int ret = bpf_probe_read_kernel(&sqe_idx, sizeof(sqe_idx), &sq_array[last_sq_idx]);
            if (ret < 0) {
                goto skip_sqe_read;
            }

            // Read the SQE at this index
            // Note: We must use bpf_probe_read_kernel here for dynamic array access
            struct io_uring_sqe sqe;
            ret = bpf_probe_read_kernel(&sqe, sizeof(sqe), &sqes[sqe_idx]);
            if (ret < 0) {
                goto skip_sqe_read;
            }

            // Check if this is a registered file (IOSQE_FIXED_FILE = 0x01)
            bool is_fixed_file = (sqe.flags & IOSQE_FIXED_FILE) != 0;
            __s32 fd = sqe.fd;

            if (is_fixed_file) {
                // For registered files, sqe.fd is an index into the registered files array
                // Try to access registered files through io_ring_ctx
                struct file *reg_file = NULL;

                // Check if we can access file_data field
                if (fd >= 0 && fd < 64) {
                    // The registered files structure has changed across kernel versions
                    // Try different approaches based on what's available

                    // Approach 1: Try ctx->file_table if it exists (not a pointer)
                    if (bpf_core_field_exists(ctx->file_table)) {
                        // file_table is embedded, not a pointer
                        if (bpf_core_field_exists(ctx->file_table.files)) {
                            // files is an array of io_fixed_file structures
                            struct io_fixed_file *fixed_files = BPF_CORE_READ(ctx, file_table.files);
                            if (fixed_files) {
                                // io_fixed_file contains a file pointer as file_ptr (unsigned long)
                                struct io_fixed_file fixed_file;
                                if (bpf_probe_read_kernel(&fixed_file, sizeof(fixed_file), &fixed_files[fd]) == 0) {
                                    // Read the file_ptr field which is unsigned long containing the file pointer
                                    unsigned long file_ptr = BPF_CORE_READ(&fixed_file, file_ptr);
                                    if (file_ptr) {
                                        // Convert the unsigned long to a file pointer
                                        reg_file = (struct file *)file_ptr;
                                    }
                                }
                            }
                        }
                    }
                    // Approach 2: Try ctx->file_data if previous didn't work
                    else if (!reg_file && bpf_core_field_exists(ctx->file_data)) {
                        struct io_rsrc_data *file_data = BPF_CORE_READ(ctx, file_data);
                        if (file_data) {
                            // io_rsrc_data might have a different structure
                            // Try to find a way to access the files
                            // This is kernel version dependent
                        }
                    }
                }

                // Try to get filename if we found the file
                if (reg_file && sqe_filename && filename_size > 0) {
                    get_file_name(reg_file, sqe_filename, filename_size, "-");
                } else if (sqe_filename && filename_size > 0) {
                    // Fallback: Mark as registered file
                    // we can't resolve the filename for registered files
                    // on all kernel versions, so we just show [reg]
                    if (filename_size > 5) {
                        sqe_filename[0] = '[';
                        sqe_filename[1] = 'r';
                        sqe_filename[2] = 'e';
                        sqe_filename[3] = 'g';
                        sqe_filename[4] = ']';
                        sqe_filename[5] = '\0';
                    }
                }

                // For registered files, we indicate it's not a regular fd
                if (event) {
                    event->uring_fd = -1;  // Indicate it's not a regular fd
                    event->uring_reg_idx = -1;  // Not using reg_idx anymore

                    // Also ensure we have a filename for registered files
                    if (sqe_filename && sqe_filename[0] == '\0' && filename_size > 5) {
                        // Set a simple marker
                        sqe_filename[0] = '[';
                        sqe_filename[1] = 'r';
                        sqe_filename[2] = 'e';
                        sqe_filename[3] = 'g';
                        sqe_filename[4] = ']';
                        sqe_filename[5] = '\0';
                    }
                }
            } else {
                // Regular file descriptor
                if (fd >= 0 && fd < 1024) {
                    get_fd_filename(task, fd, sqe_filename, filename_size);
                }
                if (event) {
                    event->uring_fd = fd;  // Store the actual fd from SQE
                    event->uring_reg_idx = -1;  // Not a registered file
                }
            }

            // Store io_uring operation details in event
            if (event) {
                event->uring_opcode = sqe.opcode;
                event->uring_flags = sqe.flags;
                event->uring_offset = sqe.off;
                event->uring_len = sqe.len;
                event->uring_rw_flags = sqe.rw_flags;
            }
        }
    }

skip_sqe_read:
    ;  // Empty statement to avoid C23 warning
}

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

    if (files) {
        struct fdtable *fdt = files->fdt;
        struct file **fd_array = fdt->fd;

        if (fd_array && ring_fd >= 0 && ring_fd < 1024) {
            bpf_probe_read_kernel(&ring_file, sizeof(ring_file), &fd_array[ring_fd]);
        }
    }

    if (!ring_file)
        return -1;

    // Try to access io_uring context through file->private_data
    *fd_out = (int)ring_fd;
    *file_out = ring_file;
    *opcode_out = 0; // TODO read the actual opcode

    return 0;
}

// Helper to get first fd from AIO syscalls (io_getevents/io_pgetevents/io_submit)
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
            if (bpf_copy_from_user_task(&iocb_ptr, sizeof(iocb_ptr), (void *)iocbpp_ptr, task, 0) == 0) {
                if (iocb_ptr) {
                    struct iocb {
                        __u64 aio_data;
                        __u32 aio_key;
                        __u32 aio_rw_flags;
                        __u16 aio_lio_opcode;
                        __s16 aio_reqprio;
                        __u32 aio_fildes;
                    } iocb;

                    if (bpf_copy_from_user_task(&iocb, sizeof(iocb), (void *)iocb_ptr, task, 0) == 0) {
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

    if (bpf_copy_from_user_task(&ring, sizeof(ring), (void *)ctx_id, task, 0) != 0)
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

        if (bpf_copy_from_user_task(&ring_event, sizeof(ring_event),
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

                if (bpf_copy_from_user_task(&iocb, sizeof(iocb), (void *)ring_event.obj, task, 0) == 0) {
                    int fd = iocb.aio_fildes;
                    // Debug: Let's check what we're actually reading
                    // Store the opcode in fd_out temporarily to debug
                    if (fd == 0 && iocb.aio_lio_opcode > 0) {
                        // If fd is 0 but we have a valid opcode, the structure might be misaligned
                        // Try reading just the fd field at the expected offset
                        __u32 fd_only;
                        if (bpf_copy_from_user_task(&fd_only, sizeof(fd_only),
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
        if (bpf_copy_from_user_task(&event, sizeof(event), (void *)events_ptr, task, 0) == 0) {
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

                if (bpf_copy_from_user_task(&iocb, sizeof(iocb), (void *)event.obj, task, 0) == 0) {
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

// Helper function to calculate number of inflight AIO requests in a ring
// For use in task iterator context with bpf_copy_from_user_task()
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
    if (bpf_copy_from_user_task(&ring, sizeof(ring), (void *)ctx_id, task, 0) != 0)
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