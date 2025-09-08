// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024-2038 Tanel Poder [0x.tools]

#include <stdio.h>
#include <unistd.h>
#include <pwd.h>
#include <time.h>
#include <locale.h>
#include <signal.h>

#include <bpf/bpf.h>
#include <bpf/libbpf.h>

#include "xcapture.h"
#include "tracking_handler.h"
#include "xcapture_user.h"

// External variables from main.c that you need to access
extern struct output_files files;
extern struct time_correlation tcorr;
extern pid_t mypid;
extern bool output_csv;
extern bool output_verbose;

// Function declarations for functions you'll call
extern const char *safe_syscall_name(__s32 syscall_nr);
extern const char *get_iorq_op_flags(__u32 cmd_flags);
extern struct timespec get_wall_from_mono(struct time_correlation *tcorr, __u64 bpf_time);
extern void get_str_from_ts(struct timespec ts, char *buf, size_t bufsize);
extern int check_and_rotate_files(struct output_files *files);

int handle_tracking_event(void *ctx, void *data, size_t data_sz)
{
    // Implement the tracking event handler (copied from your current code)
    enum event_type *type_ptr = (enum event_type *)data;
    enum event_type event_type = *type_ptr;

    switch (event_type) {
        case EVENT_SYSCALL_COMPLETION:
            {
                const struct sc_completion_event *e = data;

                if (e->pid == mypid)
                    return 0;

                __u64 duration_ns = (e->completed_sc_exit_time - e->completed_sc_enter_time);
                char ts_enter[64], ts_exit[64];
                get_str_from_ts(get_wall_from_mono(&tcorr, e->completed_sc_enter_time), ts_enter, sizeof(ts_enter));
                get_str_from_ts(get_wall_from_mono(&tcorr, e->completed_sc_exit_time), ts_exit, sizeof(ts_exit));

                // syscall error vs large value formatting
                const char *printf_format_str;

                // CSV header: TYPE,TID,TGID,SYSCALL_NAME,DURATION_NS,SYSC_RET_VAL,SYSC_SEQ_NUM,SYSC_ENTER_TIME
                // stdout currently prints microseconds (CSV prints ns)
                if (e->completed_sc_ret_val >= -4095 && e->completed_sc_ret_val <= (1024*1024*16)) {
                    printf_format_str = "SYSC_END  %7d  %7d  %-20s dur= %-'10llu  ret= %-10lld  seq= %-10llu           %s\n";
                } else {
                    printf_format_str = "SYSC_END  %7d  %7d  %-20s dur= %-'10llu  ret= 0x%llx  seq= %-10llu   %s\n";
                }

                if (output_csv) {
                    if (check_and_rotate_files(&files) < 0) {
                        fprintf(stderr, "Failed to rotate output files\n");
                        return -1;
                    }

                    // Update CSV format to use single quotes for string fields
                    if (e->completed_sc_ret_val >= -4095 && e->completed_sc_ret_val <= (1024*1024*16)) {
                        fprintf(files.sc_completion_file, "SYSC_END,%d,%d,'%s',%llu,%lld,%llu,%s\n",
                                e->pid,
                                e->tgid,
                                safe_syscall_name(e->completed_syscall_nr),
                                duration_ns,
                                e->completed_sc_ret_val,
                                e->completed_sc_sequence_num,
                                ts_enter);
                    } else {
                        fprintf(files.sc_completion_file, "SYSC_END,%d,%d,'%s',%llu,0x%llx,%lld,%s\n",
                                e->pid,
                                e->tgid,
                                safe_syscall_name(e->completed_syscall_nr),
                                duration_ns,
                                e->completed_sc_ret_val,
                                e->completed_sc_sequence_num,
                                ts_enter);
                    }
                } else {
                    printf(printf_format_str,
                            e->pid,
                            e->tgid,
                            safe_syscall_name(e->completed_syscall_nr),
                            duration_ns / 1000, // print microsec in dev mode for narrower output
                            e->completed_sc_ret_val,
                            e->completed_sc_sequence_num,
                            ts_exit); // seeing syscall completion ts is more useful in dev mode
                }
            }
            break;

        case EVENT_IORQ_COMPLETION:
        {
            const struct iorq_completion_event *e = data;

                // if insert_time == issue_time then io queue was bypassed (no queuing time)
                __u64 duration_ns = (e->iorq_complete_time - e->iorq_insert_time);
                __u64 service_ns  = (e->iorq_complete_time - e->iorq_issue_time);
                char iorq_insert_str[64], iorq_issue_str[64], iorq_complete_str[64];

                get_str_from_ts(get_wall_from_mono(&tcorr, e->iorq_insert_time), iorq_insert_str, sizeof(iorq_insert_str));
                get_str_from_ts(get_wall_from_mono(&tcorr, e->iorq_issue_time), iorq_issue_str, sizeof(iorq_issue_str));
                get_str_from_ts(get_wall_from_mono(&tcorr, e->iorq_complete_time), iorq_complete_str, sizeof(iorq_complete_str));

                if (output_csv) {
                    if (check_and_rotate_files(&files) < 0) {
                        fprintf(stderr, "Failed to rotate output files\n");
                        return -1;
                    }
                    
                    // nanosec granularity for csv
                    fprintf(files.iorq_completion_file,
                        "IORQ_END,%d,%d,%d,%d,%d,%d,%u,%u,%llu,%u,'%s',%llu,%llu,%llu,%llu,%s,%d\n",
                        e->insert_pid, e->insert_tgid, e->issue_pid, e->issue_tgid,
                        e->complete_pid, e->complete_tgid,
                        MAJOR(e->iorq_dev), MINOR(e->iorq_dev), e->iorq_sector, e->iorq_bytes,
                        get_iorq_op_flags(e->iorq_cmd_flags), e->iorq_sequence_num,
                        duration_ns, service_ns, (duration_ns - service_ns),
                        iorq_insert_str, e->iorq_error);
                } else {
                    // microsec granularity for dev display mode
                    printf("IORQ_END  %7d  %7d  %7d  %7d  %7d  %7d  %-20s dur= %-'10llu  que= %-'10llu  svc= %-'10llu  "
                        "%3u:%-3u  %26s  %7d  %7d  %10llu  %12llu  %8u err= %-5d\n",
                        e->insert_pid, e->insert_tgid, e->issue_pid, e->issue_tgid,
                        e->complete_pid, e->complete_tgid,
                        get_iorq_op_flags(e->iorq_cmd_flags),
                        duration_ns / 1000, (duration_ns - service_ns) / 1000, service_ns / 1000,
                        MAJOR(e->iorq_dev), MINOR(e->iorq_dev),
                        iorq_insert_str, e->issue_pid, e->issue_tgid,
                        e->iorq_sector, e->iorq_sequence_num, e->iorq_bytes, e->iorq_error
                    );
                }
            }
            break;

        default:
            fprintf(stderr, "Unknown event type in tracking ring buffer: %d\n", event_type);
            break;
    }

    return 0;
}
