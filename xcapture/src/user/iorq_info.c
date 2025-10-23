// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024-2038 Tanel Poder [0x.tools]

#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include <unistd.h>
#include <linux/types.h>
#include "blk_types.h"
#include "xcapture.h"
#include "xcapture_user.h"

// Get block I/O operation type and flags as string
const char *get_iorq_op_flags(__u32 cmd_flags)
{
    static char buf[128];
    size_t off = 0;

#define APPEND_LITERAL(lit)                                                      \
    do {                                                                         \
        if (off < sizeof(buf)) {                                                 \
            int written = snprintf(buf + off, sizeof(buf) - off, "%s", (lit));   \
            if (written < 0) {                                                   \
                buf[0] = '\0';                                                   \
                return buf;                                                      \
            }                                                                    \
            if ((size_t)written >= sizeof(buf) - off) {                          \
                off = sizeof(buf);                                               \
            } else {                                                             \
                off += (size_t)written;                                          \
            }                                                                    \
        }                                                                        \
    } while (0)

    buf[0] = '\0';

    if ((cmd_flags & REQ_OP_WRITE) == 0) {
        APPEND_LITERAL("READ");
    } else if (cmd_flags & REQ_OP_WRITE) {
        APPEND_LITERAL("WRITE");
    } else if (cmd_flags & REQ_OP_FLUSH) {
        APPEND_LITERAL("FLUSH");
    } else if (cmd_flags & REQ_OP_DISCARD) {
        APPEND_LITERAL("DISCARD");
    } else if (cmd_flags & REQ_OP_SCSI_IN) {
        APPEND_LITERAL("SCSI_IN");
    } else if (cmd_flags & REQ_OP_SCSI_OUT) {
        APPEND_LITERAL("SCSI_OUT");
    } else if (cmd_flags & REQ_OP_DRV_IN) {
        APPEND_LITERAL("DRV_IN");
    } else if (cmd_flags & REQ_OP_DRV_OUT) {
        APPEND_LITERAL("DRV_OUT");
    }

    if (cmd_flags & REQ_SYNC)
        APPEND_LITERAL("|SYNC");
    if (cmd_flags & REQ_META)
        APPEND_LITERAL("|META");
    if (cmd_flags & REQ_PRIO)
        APPEND_LITERAL("|PRIO");
    if (cmd_flags & REQ_FUA)
        APPEND_LITERAL("|FUA");
    if (cmd_flags & REQ_RAHEAD)
        APPEND_LITERAL("|RA");
    if (cmd_flags & REQ_DRV)
        APPEND_LITERAL("|DRV");
    if (cmd_flags & REQ_SWAP)
        APPEND_LITERAL("|SWAP");

#undef APPEND_LITERAL

    return buf;
}
