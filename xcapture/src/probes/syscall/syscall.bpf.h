// Common definitions for syscall tracing
#ifndef SYSCALL_BPF_H
#define SYSCALL_BPF_H

#include <vmlinux.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_tracing.h>

#include "maps/xcapture_maps_common.h"

// platform specific syscall stuff
#if defined(__TARGET_ARCH_arm64)
#include "syscall_aarch64.h"
#include "syscall_fd_bitmap_aarch64.h"
#elif defined(__TARGET_ARCH_x86)
#include "syscall_x86_64.h"
#include "syscall_fd_bitmap_x86_64.h"
#endif

#endif /* SYSCALL_BPF_H */
