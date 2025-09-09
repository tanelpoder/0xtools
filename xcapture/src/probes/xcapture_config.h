// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024-2038 Tanel Poder [0x.tools]

#ifndef __XCAPTURE_CONFIG_H
#define __XCAPTURE_CONFIG_H

// Global configuration variables (set from userspace via skeleton)
// These are const volatile to be placed in .rodata section
// The const volatile pattern allows userspace to set values before BPF program load
// but prevents modification after load (values are in read-only section)

// Show all tasks including sleeping ones (equivalent to -a flag)
const volatile bool xcap_show_all = false;

// Port threshold for daemon detection heuristic (equivalent to -d flag)
const volatile __u32 xcap_daemon_ports = 10000;

// Filter by TGID - 0 means no filter (equivalent to -p flag)
const volatile pid_t xcap_filter_tgid = 0;

// Enable kernel stack trace collection (equivalent to -k flag)
const volatile bool xcap_dump_kernel_stack_traces = false;

// Enable userspace stack trace collection (equivalent to -u flag)
const volatile bool xcap_dump_user_stack_traces = false;

// PID of xcapture itself to filter out from results
const volatile pid_t xcap_xcapture_pid = 0;

#endif /* __XCAPTURE_CONFIG_H */