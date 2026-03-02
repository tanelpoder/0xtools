// SPDX-License-Identifier: GPL-2.0
// Copyright (c) 2020 Wenbo Zhang
// Modified for PERCPU_HASH usage and timestamp selection
//
// 02-Apr-2025   Tanel Poder   Changes below:
//   Rely on built-in [io_]start_time_ns fields in Linux kernel
//   Remove IO insert/issue TPs and starts map
//   Mark "hists" map as per-CPU map

#include <vmlinux.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_tracing.h>

#include "biolatency.h"
#include "bits.bpf.h"
#include "core_fixes.bpf.h"

#define MAX_ENTRIES 10240

extern int LINUX_KERNEL_VERSION __kconfig;

const volatile bool filter_cg = false;
const volatile bool targ_per_disk = false;
const volatile bool targ_per_flag = false;
const volatile bool targ_queued = false;
const volatile bool targ_ms = false;
const volatile bool filter_dev = false;
const volatile __u32 targ_dev = 0;
const volatile bool targ_single = true;

struct {
    __uint(type, BPF_MAP_TYPE_CGROUP_ARRAY);
    __type(key, u32);
    __type(value, u32);
    __uint(max_entries, 1);
} cgroup_map SEC(".maps");

static struct hist initial_hist;

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_HASH);
    __uint(max_entries, MAX_ENTRIES);
    __type(key, struct hist_key);
    __type(value, struct hist);
} hists SEC(".maps");

static int handle_block_rq_complete(struct request *rq, int error, unsigned int nr_bytes)
{
    struct hist_key hkey = {};
    struct hist *histp;
    u64 slot, delta, start_ns;
    u64 ts;
    int ret;

    if (filter_cg && !bpf_current_task_under_cgroup(&cgroup_map, 0)) {
         return 0;
    }

    ts = bpf_ktime_get_ns();

    if (targ_queued)
        start_ns = BPF_CORE_READ(rq, start_time_ns);
    else
        start_ns = BPF_CORE_READ(rq, io_start_time_ns);

    delta = (s64)(ts - start_ns);

    if (delta < 0) {
        return 0;
    }

    hkey.dev = 0; // Initialize
    if (targ_per_disk) {
        struct gendisk *disk = NULL;
        struct request_queue *q = BPF_CORE_READ(rq, q);
        if (q)
             disk = BPF_CORE_READ(q, disk);

        if (disk) {
             u32 major = BPF_CORE_READ(disk, major);
             u32 minor = BPF_CORE_READ(disk, first_minor);
             hkey.dev = MKDEV(major, minor);
        } else {
        }
    }

    if (filter_dev && hkey.dev != targ_dev) {
         return 0;
    }

    hkey.cmd_flags = 0;
    if (targ_per_flag)
        hkey.cmd_flags = BPF_CORE_READ(rq, cmd_flags);

    histp = bpf_map_lookup_elem(&hists, &hkey);
    if (!histp) {
        ret = bpf_map_update_elem(&hists, &hkey, &initial_hist, BPF_ANY);
        if (ret < 0) {
            return 0; // Exit if update failed
        }
        histp = bpf_map_lookup_elem(&hists, &hkey);
        if (!histp) {
             return 0;
        }
    } else {
    }

    // Calculate log2 histogram slot
    if (targ_ms)
        delta /= 1000000U;
    else
        delta /= 1000U;

    slot = log2l(delta);
    if (slot >= MAX_SLOTS)
        slot = MAX_SLOTS - 1;

    histp->slots[slot]++;

    return 0;
}

SEC("tp_btf/block_rq_complete")
int BPF_PROG(block_rq_complete_btf, struct request *rq, int error, unsigned int nr_bytes)
{
    return handle_block_rq_complete(rq, error, nr_bytes);
}

char LICENSE[] SEC("license") = "GPL";
