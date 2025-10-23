// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024-2038 Tanel Poder [0x.tools]

#ifndef __FILE_HELPERS_H
#define __FILE_HELPERS_H

#include <vmlinux.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>

#include "xcapture.h"

#define MAX_PATH_DEPTH 16
// socket file type
#ifndef AF_UNIX
#define AF_UNIX 1
#endif
#define AF_INET   2
#define AF_INET6  10
#define S_IFMT    0170000
#define S_IFSOCK  0140000

// get file dentry name only
static void __always_inline get_file_name(struct file *file, char *dest, size_t size, const char *fallback) {
    if (file) {
        struct dentry *dentry = BPF_CORE_READ(file, f_path.dentry);

        if (dentry) {
            struct qstr d_name = BPF_CORE_READ(dentry, d_name);
            bpf_probe_read_kernel_str(dest, size, d_name.name);
            return;
        }
    }

    // Handle error/fallback message case
    __builtin_memcpy(dest, fallback, __builtin_strlen(fallback) + 1);
}


// get inet/unix socket info from file object
static __always_inline bool get_socket_info(struct file *file,
                                            struct socket_info *si)
{
    struct socket *sock;
    struct sock *sk;
    struct inet_sock *inet;

    if (!file)
        return false;

    __builtin_memset(si, 0, sizeof(*si));

    sock = BPF_CORE_READ(file, private_data);
    if (!sock)
        return false;

    si->socket_type = BPF_CORE_READ(sock, type);

    sk = BPF_CORE_READ(sock, sk);
    if (!sk)
        return false;

    si->family = BPF_CORE_READ(sk, __sk_common.skc_family);
    if (si->family == AF_INET || si->family == AF_INET6) {
        si->protocol = BPF_CORE_READ(sk, sk_protocol);
        if (si->protocol != IPPROTO_TCP && si->protocol != IPPROTO_UDP)
            return false;

        inet = (struct inet_sock *)sk;

        if (si->family == AF_INET) {
            si->saddr_v4 = BPF_CORE_READ(sk, __sk_common.skc_rcv_saddr);
            si->daddr_v4 = BPF_CORE_READ(sk, __sk_common.skc_daddr);
        } else {
            unsigned __int128 saddr, daddr;
            BPF_CORE_READ_INTO(&saddr, sk, __sk_common.skc_v6_rcv_saddr.in6_u.u6_addr32);
            BPF_CORE_READ_INTO(&daddr, sk, __sk_common.skc_v6_daddr.in6_u.u6_addr32);
            __builtin_memcpy(si->saddr_v6, &saddr, sizeof(si->saddr_v6));
            __builtin_memcpy(si->daddr_v6, &daddr, sizeof(si->daddr_v6));
        }

        si->sport = BPF_CORE_READ(inet, inet_sport);
        si->dport = BPF_CORE_READ(sk, __sk_common.skc_dport);

        if (si->protocol == IPPROTO_TCP) {
            si->state = BPF_CORE_READ(sk, __sk_common.skc_state);
        }

        return true;
    }

    if (si->family == AF_UNIX) {
        struct dentry *dentry = BPF_CORE_READ(file, f_path.dentry);
        struct inode *inode = dentry ? BPF_CORE_READ(dentry, d_inode) : NULL;
        if (inode) {
            si->unix_inode = BPF_CORE_READ(inode, i_ino);
            si->unix_owner_uid = BPF_CORE_READ(inode, i_uid.val);
        }

        struct unix_sock *usk = (struct unix_sock *)sk;
        struct unix_address *addr = NULL;
        addr = BPF_CORE_READ(usk, addr);
        if (addr) {
            __u32 len = BPF_CORE_READ(addr, len);
            if (len > 2) {
                __u32 path_len = len - 2;
                int name_off = bpf_core_field_offset(struct unix_address, name);
                if (name_off >= 0) {
                    unsigned long path_base = (unsigned long)addr + name_off + 2;
                    __u8 first_byte = 0;
                    bpf_probe_read_kernel(&first_byte, sizeof(first_byte), (const void *)path_base);

                    if (first_byte == '\0') {
                        si->unix_is_abstract = 1;
                        if (path_len > 1) {
                            __u32 copy_len = path_len - 1;
                            if (copy_len >= XCAPTURE_UNIX_PATH_MAX)
                                copy_len = XCAPTURE_UNIX_PATH_MAX - 1;
                            bpf_probe_read_kernel(si->unix_path, copy_len, (const void *)(path_base + 1));
                            si->unix_path[copy_len] = '\0';
                            si->unix_path_len = copy_len;
                        }
                    } else {
                        __u32 copy_len = path_len;
                        if (copy_len >= XCAPTURE_UNIX_PATH_MAX)
                            copy_len = XCAPTURE_UNIX_PATH_MAX - 1;
                        bpf_probe_read_kernel(si->unix_path, copy_len, (const void *)path_base);
                        si->unix_path[copy_len] = '\0';
                        si->unix_path_len = copy_len;
                    }
                }
            }
        }

        struct pid *peer_pid = BPF_CORE_READ(sk, sk_peer_pid);
        if (peer_pid) {
            si->unix_peer_pid = BPF_CORE_READ(peer_pid, numbers[0].nr);
        }

        struct sock *peer_sk = BPF_CORE_READ(usk, peer);
        if (peer_sk) {
            struct socket *peer_socket = BPF_CORE_READ(peer_sk, sk_socket);
            if (peer_socket) {
                struct file *peer_file = BPF_CORE_READ(peer_socket, file);
                if (peer_file) {
                    struct dentry *peer_dentry = BPF_CORE_READ(peer_file, f_path.dentry);
                    struct inode *peer_inode = peer_dentry ? BPF_CORE_READ(peer_dentry, d_inode) : NULL;
                    if (peer_inode)
                        si->unix_peer_inode = BPF_CORE_READ(peer_inode, i_ino);
                }
            }
        }

        return true;
    }

    return false;
}

#endif /* __FILE_HELPERS_H */
