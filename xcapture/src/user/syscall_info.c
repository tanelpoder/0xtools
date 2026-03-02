// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024-2038 Tanel Poder [0x.tools]

#include <stdio.h>
#include <stdbool.h>
#include <unistd.h>
#include <linux/types.h>
#include "xcapture.h"
#include "xcapture_user.h"

// platform specific syscall NR<->name mapping
#if defined(__TARGET_ARCH_arm64)
#include "syscall_aarch64.h"
#include "syscall_names_aarch64.h"
#elif defined(__TARGET_ARCH_x86)
#include "syscall_x86_64.h"
#include "syscall_names_x86_64.h"
#endif

const char *safe_syscall_name(__s32 syscall_nr)
{
    static char unknown_str[32];

    if (syscall_nr < 0)
        return "-";

    if ((unsigned long)syscall_nr < NR_SYSCALLS && sysent0[syscall_nr].name != NULL) {
        return sysent0[syscall_nr].name;
    }

    snprintf(unknown_str, sizeof(unknown_str), "%d", syscall_nr);
    return unknown_str;
}

const char *get_syscall_info_desc(__u32 syscall_nr)
{
    switch (syscall_nr) {
        case __NR_io_submit:     return "inflight_rqs";
        case __NR_io_cancel:     return "inflight_rqs";
        case __NR_io_destroy:    return "inflight_rqs";
        case __NR_io_getevents:  return "inflight_rqs";
        case __NR_io_pgetevents: return "inflight_rqs";
    default:
        return "-";
    }
}
