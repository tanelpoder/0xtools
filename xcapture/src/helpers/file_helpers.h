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


// get inet socket info from file object
static __always_inline bool get_socket_info(struct file *file, struct socket_info *si)
{
    struct socket *sock;
    struct sock *sk;
    struct inet_sock *inet;

    if (!file)
        return false;

    sock = BPF_CORE_READ(file, private_data);
    if (!sock)
        return false;

    sk = BPF_CORE_READ(sock, sk);
    if (!sk)
        return false;

    si->family = BPF_CORE_READ(sk, __sk_common.skc_family);
    if (si->family != AF_INET && si->family != AF_INET6)
        return false;

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

    // Read ports
    si->sport = BPF_CORE_READ(inet, inet_sport);
    si->dport = BPF_CORE_READ(sk, __sk_common.skc_dport);

    // Read socket state (for TCP sockets)
    if (si->protocol == IPPROTO_TCP) {
        si->state = BPF_CORE_READ(sk, __sk_common.skc_state);
    } else {
        si->state = 0;  // UDP doesn't have states
    }

    return true;
}

#endif /* __FILE_HELPERS_H */
