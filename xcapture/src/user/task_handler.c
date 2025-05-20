// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024-2038 Tanel Poder [0x.tools]

#include <stdio.h>
#include <unistd.h>
#include <pwd.h>
#include <time.h>

#include <bpf/bpf.h>
#include <bpf/libbpf.h>

#include "xcapture.h"
#include "task_handler.h"
#include "xcapture_user.h"
#include "md5.h"

// External variables from main.c
extern struct output_files files;
extern struct time_correlation tcorr;
extern pid_t mypid;
extern bool output_csv;
extern bool output_verbose;
extern bool dump_stack_traces;

// Function declarations for common functions
extern const char *getusername(uid_t uid);
extern const char *format_task_state(__u32 state);
extern const char *safe_syscall_name(__s32 syscall_nr);
extern const char *format_connection(const struct socket_info *si, char *buf, size_t buflen);
extern struct timespec get_wall_from_mono(struct time_correlation *tcorr, __u64 bpf_time);
extern struct timespec sub_ns_from_ts(struct timespec ts, __u64 ns);
extern void get_str_from_ts(struct timespec ts, char *buf, size_t bufsize);
extern int check_and_rotate_files(struct output_files *files);

int handle_task_event(void *ctx, void *data, size_t data_sz)
{
    enum event_type *type_ptr = (enum event_type *)data;
    enum event_type event_type = *type_ptr;

    // Safety check - only task info events should be in this ring buffer
    if (event_type != EVENT_TASK_INFO) {
        fprintf(stderr, "Unexpected event type in task samples ring buffer: %d\n", event_type);
        return 0;
    }

    const struct task_output_event *event = data;
    // struct bpf_print_ctx *printer_ctx = (struct bpf_print_ctx *)ctx;

    // Skip processing xcapture itself (it's always on CPU when sampling)
    if (event->pid == mypid)
        return 0;

    // get sample_start timestamp from when this task loop iteration started
    char timestamp[64];
    struct timespec current_sample_ts_iter_start = get_wall_from_mono(&tcorr, event->storage.sample_start_ktime);
    get_str_from_ts(current_sample_ts_iter_start, timestamp, sizeof(timestamp));

    // Process task info
    __u64 sc_duration_ns = 0;
    if (event->storage.sc_enter_time > 0) {
        sc_duration_ns = event->storage.sample_actual_ktime - event->storage.sc_enter_time;
    }

    char sc_start_time_str[64] = "";
    // when this task struct was actually read
    // struct timespec current_sample_ts_this_task = get_wall_from_mono(&tcorr, event->storage.sample_actual_ktime);

    // get syscall start timestamp string from ktime ns
    if (event->storage.sc_enter_time > 0) {
        struct timespec current_sc_start_ts = get_wall_from_mono(
            &tcorr, event->storage.sample_actual_ktime - sc_duration_ns);
        get_str_from_ts(current_sc_start_ts, sc_start_time_str, sizeof(sc_start_time_str));
    }

    char conn_buf[256] = "";
    if (event->has_socket_info) {
        format_connection(&event->sock_info, conn_buf, sizeof(conn_buf));
    }

    if (output_csv) {
        if (check_and_rotate_files(&files) < 0) {
            fprintf(stderr, "Failed to rotate output files\n");
            return -1;
        }

        fprintf(files.sample_file,
               "%s,%d,%d,%s,\"%s\",\"%s\",\"%s\",%s,%s,%s,%lld,%lld,%lld,%llx,%llx,%llx,%llx,%llx,%llx,\"%s\",\"%s\",%s,%d\n",
               timestamp,
               event->pid,
               event->tgid,
               format_task_state(event->state),
               getusername(event->euid),
               (event->flags & PF_KTHREAD) ? "[kernel]" : event->exe_file,
               event->comm,
               (event->flags & PF_KTHREAD) ? "-" : safe_syscall_name(event->syscall_nr),
               (event->flags & PF_KTHREAD) ? "-" : (
                   event->storage.sc_enter_time ? safe_syscall_name(event->storage.in_syscall_nr) : "?"
               ),
               event->storage.sc_enter_time > 0 ? sc_start_time_str : "", // todo validate bug
               sc_duration_ns,
               event->storage.sc_sequence_num,
               event->storage.iorq_sequence_num,
               event->syscall_args[0],
               event->syscall_args[1],
               event->syscall_args[2],
               event->syscall_args[3],
               event->syscall_args[4],
               event->syscall_args[5],
               event->filename[0] ? event->filename : "",
               event->has_socket_info ? conn_buf : "",
               get_syscall_info_desc(event->syscall_nr),
               event->storage.aio_inflight_reqs
        );
    }
    else {
        printf("%-26s  %'6lld  %7d  %7d  %-6s  %-6d  %-6d  %-4d  %-16s  %-20s  %-16s  %-20s  %-20s  %'16lld  %16llx  "
               "%-20s  %-40s  %-26s  %12lld  %-12s  %12d\n",
            timestamp,
            (event->storage.sample_actual_ktime - event->storage.sample_start_ktime) / 1000, // microsec for dev mode
            event->pid,
            event->tgid,
            format_task_state(event->state),
            event->on_cpu,
            event->on_rq,
            (bool) event->migration_pending,
            getusername(event->euid),
            (event->flags & PF_KTHREAD) ? "[kernel]" : event->exe_file,
            event->comm,
            event->flags & PF_KTHREAD ? "-" : safe_syscall_name(event->syscall_nr),
            (event->flags & PF_KTHREAD) ? "-" : (
                event->storage.sc_enter_time > 0 ? safe_syscall_name(event->storage.in_syscall_nr) : "?"
            ),
            (sc_duration_ns / 1000), // microseconds
            event->syscall_args[0],
            event->filename[0] ? event->filename : "-",
            event->has_socket_info ? conn_buf : "-",
            event->storage.sc_enter_time > 0 ? sc_start_time_str : "-", // todo validate bug
            event->storage.sc_sequence_num,
            get_syscall_info_desc(event->syscall_nr),
            event->storage.aio_inflight_reqs
        );
    }

    if (dump_stack_traces && files.kstack_file && event->kstack_len > 0) {
        // Get md5 hash of stack addresses (lower 64 bits)
        uint64_t stack_hash = hash_stack((uint64_t*)event->kstack, event->kstack_len);

        // Comma-separated list of stack trace addresses in hex
        fprintf(files.kstack_file, "%s,%d,%d,%lx,['", timestamp, event->pid, event->tgid, stack_hash);

        for (int i = 0; i < event->kstack_len; i++) {
            fprintf(files.kstack_file, "0x%llx", event->kstack[i]);
            if (i < event->kstack_len - 1) {
                fprintf(files.kstack_file, "','");
            }
        }

        fprintf(files.kstack_file, "']\n");
    }

    return 0;
}
