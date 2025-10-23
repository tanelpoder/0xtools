// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Output file management helpers for xcapture

#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <time.h>
#include <sys/types.h>
#include <linux/limits.h>

#include "xcapture_user.h"
#include "xcapture_context.h"

static char samplebuf[XCAP_BUFSIZ];
static char syscbuf[XCAP_BUFSIZ];
static char iorqbuf[XCAP_BUFSIZ];
static char kstackbuf[XCAP_BUFSIZ];
static char ustackbuf[XCAP_BUFSIZ];

static FILE *open_csv_file(const char *filename, const char *header)
{
    FILE *f = fopen(filename, "a");
    if (!f) {
        fprintf(stderr, "Failed to open file %s: %s\n", filename, strerror(errno));
        return NULL;
    }

    if (fseek(f, 0, SEEK_END) == 0 && ftell(f) == 0 && header)
        fprintf(f, "%s\n", header);

    return f;
}

static char *get_hourly_filename(char *buf, size_t buf_len,
                                 const struct xcapture_context *ctx,
                                 const char *base_name,
                                 const struct tm *tm)
{
    snprintf(buf, buf_len, "%s/%s_%04d-%02d-%02d.%02d.csv",
             ctx->output_dirname ? ctx->output_dirname : DEFAULT_OUTPUT_DIR,
             base_name,
             tm->tm_year + 1900,
             tm->tm_mon + 1,
             tm->tm_mday,
             tm->tm_hour);
    return buf;
}

static int create_output_files(struct output_files *files,
                               const struct tm *tm,
                               const struct xcapture_context *ctx)
{
    char path[PATH_MAX];

    close_output_files(files);

    const char *sample_header = ctx->payload_trace_enabled ?
        "TIMESTAMP,WEIGHT_US,TID,TGID,PIDNS,CGROUP_ID,STATE,USERNAME,EXE,COMM,SYSCALL,SYSCALL_ACTIVE,"
        "SYSC_ENTRY_TIME,SYSC_NS_SO_FAR,SYSC_SEQ_NUM,IORQ_SEQ_NUM,"
        "SYSC_ARG1,SYSC_ARG2,SYSC_ARG3,SYSC_ARG4,SYSC_ARG5,SYSC_ARG6,"
        "FILENAME,CONNECTION,CONN_STATE,EXTRA_INFO,KSTACK_HASH,USTACK_HASH,TRACE_PAYLOAD,TRACE_PAYLOAD_LEN"
        :
        "TIMESTAMP,WEIGHT_US,TID,TGID,PIDNS,CGROUP_ID,STATE,USERNAME,EXE,COMM,SYSCALL,SYSCALL_ACTIVE,"
        "SYSC_ENTRY_TIME,SYSC_NS_SO_FAR,SYSC_SEQ_NUM,IORQ_SEQ_NUM,"
        "SYSC_ARG1,SYSC_ARG2,SYSC_ARG3,SYSC_ARG4,SYSC_ARG5,SYSC_ARG6,"
        "FILENAME,CONNECTION,CONN_STATE,EXTRA_INFO,KSTACK_HASH,USTACK_HASH";

    files->sample_file = open_csv_file(
        get_hourly_filename(path, sizeof(path), ctx, SAMPLE_CSV_FILENAME, tm),
        sample_header);
    if (!files->sample_file)
        return -1;
    setbuffer(files->sample_file, samplebuf, XCAP_BUFSIZ);

    const char *sysc_header = ctx->payload_trace_enabled ?
        "TYPE,TID,TGID,SYSCALL_NAME,DURATION_NS,SYSC_RET_VAL,SYSC_SEQ_NUM,SYSC_ENTER_TIME,TRACE_PAYLOAD,TRACE_PAYLOAD_LEN,TRACE_PAYLOAD_SYS,TRACE_PAYLOAD_SEQ"
        :
        "TYPE,TID,TGID,SYSCALL_NAME,DURATION_NS,SYSC_RET_VAL,SYSC_SEQ_NUM,SYSC_ENTER_TIME";

    files->sc_completion_file = open_csv_file(
        get_hourly_filename(path, sizeof(path), ctx, SYSC_COMPLETION_CSV_FILENAME, tm),
        sysc_header);
    if (!files->sc_completion_file)
        goto fail;
    setbuffer(files->sc_completion_file, syscbuf, XCAP_BUFSIZ);

    files->iorq_completion_file = open_csv_file(
        get_hourly_filename(path, sizeof(path), ctx, IORQ_COMPLETION_CSV_FILENAME, tm),
        "TYPE,INSERT_TID,INSERT_TGID,ISSUE_TID,ISSUE_TGID,COMPLETE_TID,COMPLETE_TGID,"
        "DEV_MAJ,DEV_MIN,SECTOR,BYTES,IORQ_FLAGS,IORQ_SEQ_NUM,"
        "DURATION_NS,SERVICE_NS,QUEUED_NS,ISSUE_TIMESTAMP,ERROR");
    if (!files->iorq_completion_file)
        goto fail;
    setbuffer(files->iorq_completion_file, iorqbuf, XCAP_BUFSIZ);

    if (ctx->dump_kernel_stack_traces) {
        files->kstack_file = open_csv_file(
            get_hourly_filename(path, sizeof(path), ctx, KSTACK_CSV_FILENAME, tm),
            "KSTACK_HASH,KSTACK_SYMS");
        if (!files->kstack_file)
            goto fail;
        setbuffer(files->kstack_file, kstackbuf, XCAP_BUFSIZ);
    }

    if (ctx->dump_user_stack_traces) {
        files->ustack_file = open_csv_file(
            get_hourly_filename(path, sizeof(path), ctx, USTACK_CSV_FILENAME, tm),
            "USTACK_HASH,USTACK_SYMS");
        if (!files->ustack_file)
            goto fail;
        setbuffer(files->ustack_file, ustackbuf, XCAP_BUFSIZ);
    }

    files->cgroup_file = open_csv_file(
        get_hourly_filename(path, sizeof(path), ctx, "xcapture_cgroups", tm),
        "CGROUP_ID,CGROUP_PATH");
    if (!files->cgroup_file)
        goto fail;

    files->current_year = tm->tm_year;
    files->current_month = tm->tm_mon;
    files->current_day = tm->tm_mday;
    files->current_hour = tm->tm_hour;

    return 0;

fail:
    close_output_files(files);
    return -1;
}

void close_output_files(struct output_files *files)
{
    if (!files)
        return;

    if (files->sample_file) {
        fflush(files->sample_file);
        fclose(files->sample_file);
        files->sample_file = NULL;
    }
    if (files->sc_completion_file) {
        fflush(files->sc_completion_file);
        fclose(files->sc_completion_file);
        files->sc_completion_file = NULL;
    }
    if (files->iorq_completion_file) {
        fflush(files->iorq_completion_file);
        fclose(files->iorq_completion_file);
        files->iorq_completion_file = NULL;
    }
    if (files->kstack_file) {
        fflush(files->kstack_file);
        fclose(files->kstack_file);
        files->kstack_file = NULL;
    }
    if (files->ustack_file) {
        fflush(files->ustack_file);
        fclose(files->ustack_file);
        files->ustack_file = NULL;
    }
    if (files->cgroup_file) {
        fflush(files->cgroup_file);
        fclose(files->cgroup_file);
        files->cgroup_file = NULL;
    }
}

int check_and_rotate_files(struct output_files *files, const struct xcapture_context *ctx)
{
    time_t now = time(NULL);
    struct tm *current_tm = localtime(&now);

    if (!current_tm)
        return -1;

    if (current_tm->tm_year != files->current_year  ||
        current_tm->tm_mon  != files->current_month ||
        current_tm->tm_mday != files->current_day   ||
        current_tm->tm_hour != files->current_hour)
        return create_output_files(files, current_tm, ctx);

    return (files->sample_file || files->sc_completion_file || files->iorq_completion_file)
        ? 0
        : create_output_files(files, current_tm, ctx);
}
