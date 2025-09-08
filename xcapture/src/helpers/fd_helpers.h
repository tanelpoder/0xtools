// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024-2038 Tanel Poder [0x.tools]

#ifndef __FD_HELPERS_H
#define __FD_HELPERS_H

#include <vmlinux.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_tracing.h>

#include "xcapture.h"
#include "../probes/xcapture_config.h"
#include "file_helpers.h"

#if defined(__TARGET_ARCH_arm64)
#include "syscall_aarch64.h"
#include "syscall_fd_bitmap_aarch64.h"
#elif defined(__TARGET_ARCH_x86)
#include "syscall_x86_64.h"
#include "syscall_fd_bitmap_x86_64.h"
#endif

// TCP socket states
#define TCP_LISTEN    10

// Helper function to check if syscall is a READ-type operation
static bool __always_inline is_read_syscall(__s32 syscall_nr)
{
    switch (syscall_nr) {
        // Read operations
        case __NR_read:
        case __NR_readv:
        case __NR_pread64:
        case __NR_preadv:
        case __NR_preadv2:
        case __NR_recvfrom:
        case __NR_recvmsg:
        case __NR_recvmmsg:
        // Poll/select operations
#ifdef __NR_poll
        case __NR_poll:
#endif
#ifdef __NR_select
        case __NR_select:
#endif
        case __NR_pselect6:
        case __NR_ppoll:
#ifdef __NR_epoll_wait
        case __NR_epoll_wait:
#endif
        case __NR_epoll_pwait:
#ifdef __NR_epoll_pwait2
        case __NR_epoll_pwait2:
#endif
        // Connection operations
        case __NR_connect:
        case __NR_accept:
        case __NR_accept4:
            return true;
        default:
            return false;
    }
}

// Helper function to check if syscall is a WRITE-type operation
static bool __always_inline is_write_syscall(__s32 syscall_nr)
{
    switch (syscall_nr) {
        case __NR_write:
        case __NR_writev:
        case __NR_pwrite64:
        case __NR_pwritev:
        case __NR_pwritev2:
        case __NR_sendto:
        case __NR_sendmsg:
        case __NR_sendmmsg:
            return true;
        default:
            return false;
    }
}

// Helper to check socket and get port for a file descriptor
// Returns:
//   0: Not a socket or error
//   1: LISTEN socket (should be filtered as daemon)
//   port_num: Non-LISTEN socket with this port number
static __u16 __always_inline check_fd_port(int fd, struct task_struct *task)
{
    if (fd < 0 || fd >= 1024)
        return 0;

    struct file *file = NULL;
    struct files_struct *files = task->files;

    if (files) {
        struct fdtable *fdt = files->fdt;
        struct file **fd_array = fdt->fd;

        if (fd_array) {
            // Note: We must use bpf_probe_read_kernel for dynamic array access
            bpf_probe_read_kernel(&file, sizeof(file), &fd_array[fd]);
        }
    }

    if (file) {
        struct inode *inode = BPF_CORE_READ(file, f_path.dentry, d_inode);
        if (inode) {
            unsigned short i_mode = BPF_CORE_READ(inode, i_mode);
            // Check if file is of socket type
            if ((i_mode & S_IFMT) == S_IFSOCK) {
                struct socket_info sock_info;
                if (get_socket_info(file, &sock_info)) {
                    // Only check TCP/UDP sockets
                    if (sock_info.protocol == IPPROTO_TCP || sock_info.protocol == IPPROTO_UDP) {
                        // If it's a TCP socket in LISTEN state, return 1 to indicate daemon
                        if (sock_info.protocol == IPPROTO_TCP && sock_info.state == TCP_LISTEN) {
                            return 1;  // Special value indicating LISTEN socket
                        }
                        // Otherwise return the port number
                        return bpf_ntohs(sock_info.sport);
                    }
                }
            }
        }
    }

    return 0;
}

// Helper to get first fd from ppoll and its file info
static int __always_inline get_ppoll_first_fd_info(struct pt_regs *regs, struct task_struct *task,
                                                   int *fd_out, struct file **file_out)
{

    struct pollfd pfd;  // Only read first pollfd
    void *fds_ptr;
    __u64 nfds;

    // Get ppoll arguments (fds pointer and nfds count)
#if defined(__TARGET_ARCH_x86)
    fds_ptr = (void *)regs->di;  // arg1
    nfds = regs->si;              // arg2
#elif defined(__TARGET_ARCH_arm64)
    fds_ptr = (void *)regs->regs[0];
    nfds = regs->regs[1];
#endif

    // Check if we have at least one fd
    if (nfds == 0)
        return -1;

    // Read only first pollfd from userspace - this requires sleepable BPF program
    if (bpf_copy_from_user_task(&pfd, sizeof(struct pollfd), fds_ptr, task, 0) != 0)
        return -1;

    // Get file from fd
    if (pfd.fd < 0 || pfd.fd >= 1024)
        return -1;

    struct file *file = NULL;
    struct files_struct *files = task->files;

    if (files) {
        struct fdtable *fdt = files->fdt;
        struct file **fd_array = fdt->fd;

        if (fd_array) {
            bpf_probe_read_kernel(&file, sizeof(file), &fd_array[pfd.fd]);
        }
    }

    *fd_out = pfd.fd;
    *file_out = file;
    return 0;
}

// Helper to check first fd in ppoll for daemon port
static __u16 __always_inline check_ppoll_daemon_ports(struct pt_regs *regs, struct task_struct *task)
{

    int fd;
    struct file *file;

    if (get_ppoll_first_fd_info(regs, task, &fd, &file) != 0)
        return 0;

    return check_fd_port(fd, task);
}

// Helper to get first fd from pselect6 and its file info
static int __always_inline get_pselect6_first_fd_info(struct pt_regs *regs, struct task_struct *task,
                                                      int *fd_out, struct file **file_out)
{

    __u64 nfds;
    __u64 readfds_ptr;

    // Get pselect6 arguments
#if defined(__TARGET_ARCH_x86)
    nfds = regs->di;                  // arg1: nfds
    readfds_ptr = regs->si;           // arg2: readfds
#elif defined(__TARGET_ARCH_arm64)
    nfds = regs->regs[0];
    readfds_ptr = regs->regs[1];
#endif

    if (nfds == 0 || nfds > 1024 || !readfds_ptr)
        return -1;

    // Read first word of fd_set (covers fds 0-63)
    unsigned long first_word = 0;
    if (bpf_copy_from_user_task(&first_word, sizeof(first_word), (void *)readfds_ptr, task, 0) != 0)
        return -1;

    // Find first fd that is set in the bitmap
    for (int i = 0; i < 64 && i < nfds; i++) {
        if (first_word & (1UL << i)) {
            // Get file from fd
            struct file *file = NULL;
            struct files_struct *files = task->files;

            if (files) {
                struct fdtable *fdt = files->fdt;
                struct file **fd_array = fdt->fd;

                if (fd_array && i >= 0 && i < 1024) {
                    bpf_probe_read_kernel(&file, sizeof(file), &fd_array[i]);
                }
            }

            *fd_out = i;
            *file_out = file;
            return 0;
        }
    }

    return -1;
}

// Helper to check first fd in pselect6 for daemon port
static __u16 __always_inline check_pselect6_daemon_ports(struct pt_regs *regs, struct task_struct *task)
{

    int fd;
    struct file *file;

    if (get_pselect6_first_fd_info(regs, task, &fd, &file) != 0)
        return 0;

    return check_fd_port(fd, task);
}


#endif // __FD_HELPERS_H