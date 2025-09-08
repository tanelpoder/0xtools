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
    buf[0] = '\0';

    if ((cmd_flags & REQ_OP_WRITE) == 0)
        strcat(buf, "READ");
    else if (cmd_flags & REQ_OP_WRITE)
        strcat(buf, "WRITE");
    else if (cmd_flags & REQ_OP_FLUSH)
        strcat(buf, "FLUSH");
    else if (cmd_flags & REQ_OP_DISCARD)
        strcat(buf, "DISCARD");
    // TODO add the rest
    else if (cmd_flags & REQ_OP_SCSI_IN)
        strcat(buf, "SCSI_IN");
    else if (cmd_flags & REQ_OP_SCSI_OUT)
        strcat(buf, "SCSI_OUT");
    else if (cmd_flags & REQ_OP_DRV_IN)
        strcat(buf, "DRV_IN");
    else if (cmd_flags & REQ_OP_DRV_OUT)
        strcat(buf, "DRV_OUT");

    if (cmd_flags & REQ_SYNC)
        strcat(buf, "|SYNC");
    if (cmd_flags & REQ_META)
        strcat(buf, "|META");
    if (cmd_flags & REQ_PRIO)
        strcat(buf, "|PRIO");
    if (cmd_flags & REQ_FUA)
        strcat(buf, "|FUA");
    if (cmd_flags & REQ_RAHEAD)
        strcat(buf, "|RA");
    if (cmd_flags & REQ_DRV)
        strcat(buf, "|DRV");
    if (cmd_flags & REQ_SWAP)
        strcat(buf, "|SWAP");

    return buf;
}