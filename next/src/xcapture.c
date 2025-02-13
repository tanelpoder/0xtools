// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024 Tanel Poder [0x.tools]

// This code layout is based on https://github.com/libbpf/libbpf-bootstrap

#include <stdio.h>
#include <unistd.h>
#include <pwd.h>
#include <time.h>
#include <locale.h>
#include <signal.h>
#include <bpf/bpf.h>
#include "xcapture.h"
#include "xcapture.skel.h"
#include <syscall_names.h>

// globals, set once by one function
bool output_csv = false;
bool header_printed = false; // thread sample output
bool completion_header_printed = false; // completion events

FILE *sample_output_file = NULL;
FILE *completion_output_file = NULL;


// handle CTRL+C and sigpipe etc
static volatile bool exiting = false;

static void sig_handler(int sig)
{
    exiting = true;
    if (output_csv) {
        if (sample_output_file) {
            fflush(sample_output_file);
            fclose(sample_output_file);
        }
        if (completion_output_file) {
            fflush(completion_output_file);
            fclose(completion_output_file);
        }
    }
}


// translate uid to user name
const char *getusername(uid_t uid)
{
  struct passwd *pw = getpwuid(uid);
  if (pw)
  {
    return pw->pw_name;
  }

  return "-";
}

static const char *get_task_state(__u32 state)
{
    switch (state & 0xFFF) {
    case 0x0000: return "RUN";   // RUNNING
    case 0x0001: return "SLEEP"; // INTERRUPTIBLE"
    case 0x0002: return "DISK";  // UNINTERRUPTIBLE"
    case 0x0200: return "WAKING";
    case 0x0400: return "NOLOAD";
    case 0x0402: return "IDLE";
    case 0x0800: return "NEW";
    default: return "<unknown>";
    }
}

// the sysent0[] may have numbering gaps in it and since it's a 
// static .h file, there may be newer syscalls with higher nr too
static const char *safe_syscall_name(__s32 syscall_nr) 
{
    static char unknown_str[32];
    
    // syscall numbering starts from 0, gaps in number range usage also possible
    // however -1 is also possible when not in a syscall

    if (syscall_nr < 0)
        return "-";

    if (syscall_nr < NR_SYSCALLS && sysent0[syscall_nr].name != NULL) {
        return sysent0[syscall_nr].name;
    }
    
    snprintf(unknown_str, sizeof(unknown_str), "%d", syscall_nr);
    return unknown_str;
}


// ns is signed as sometimes there's small negative durations reported due to
// concurrency of BPF task iterator vs event capture probes running on different CPUs (?)
struct timespec subtract_ns_from_timespec(struct timespec ts, __s64 ns) 
{
    struct timespec result = ts;

    if (result.tv_nsec < (long)(ns % 1000000000)) {
        result.tv_sec--;  // Borrow a second
        result.tv_nsec = result.tv_nsec + 1000000000 - (ns % 1000000000);
    } else {
        result.tv_nsec -= (ns % 1000000000);
    }

    result.tv_sec -= (ns / 1000000000);
    return result;
}

// handle ringbuf completion events, don't bother trying to format 
// wallclock time as these are ktime timestamps
static int handle_event(void *ctx, void *data, size_t data_sz)
{
    const struct sc_completion_event *e = data;
    
    // Calculate duration in microseconds
    __u64 duration_us = (e->completed_sc_exit_time - e->completed_sc_enter_time) / 1000;

    if (output_csv) {
        // Print header once for completion events
        if (!completion_header_printed) {
            fprintf(completion_output_file,
                   "%s,%s,%s,%s,%s,%s,%s,%s\n",
                   "TYPE",
                   "TID",
                   "TGID",
                   "SYSCALL_NR",
                   "SC_SEQ_NUM",
                   "SC_ENTER_TIME",
                   "SC_EXIT_TIME",
                   "DURATION_US");
            completion_header_printed = true;
            fflush(completion_output_file);
        }

        fprintf(completion_output_file, 
                "SC_END,%d,%d,%d,%llu,%llu,%llu,%llu\n",
                e->pid,
                e->tgid,
                e->completed_syscall_nr,
                e->completed_sc_sequence_nr,
                e->completed_sc_enter_time,
                e->completed_sc_exit_time,
                duration_us);
        fflush(completion_output_file);
    } else {
        printf("SC_END  %7d  %7d  %-20s  %12llu  %26llu  %26llu  %'16llu\n",
               e->pid,
               e->tgid,
               safe_syscall_name(e->completed_syscall_nr), // we don't know the active syscall nr for syscalls started before
                                                           // xcapture start (0), but for completion we care about other fields
               e->completed_sc_sequence_nr,
               e->completed_sc_enter_time,
               e->completed_sc_exit_time,
               duration_us);
    }
    
    return 0;
}



int main(int argc, char **argv)
{
    // super simple check to avoid proper argument handling for now
    // if any args are given to xcapture, output CSV
    if (argc > 1) {
        output_csv = true;
        // Open output files
        sample_output_file = fopen(SAMPLE_CSV_FILE, "w");
        if (!sample_output_file) {
            fprintf(stderr, "Failed to open %s for writing\n", SAMPLE_CSV_FILE);
            return 1;
        }

        completion_output_file = fopen(COMPLETION_CSV_FILE, "w");
        if (!completion_output_file) {
            fprintf(stderr, "Failed to open %s for writing\n", COMPLETION_CSV_FILE);
            fclose(sample_output_file);
            return 1;
        }
    }


    struct xcapture_bpf *skel = 0;
    struct task_info buf;
    int iter_fd = 0;
    ssize_t ret = 0;
    int err = 0;

    /* Signal handling */
    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);
    signal(SIGPIPE, sig_handler);


    /* For number formatting for readability */
    setlocale(LC_ALL,"en_US.UTF-8");

    /* Load and attach all eBPF programs and structs */
    skel = xcapture_bpf__open_and_load();
    if (!skel) {
        fprintf(stderr, "Failed to open and load BPF skeleton\n");
        goto cleanup;
    }

    err = xcapture_bpf__attach(skel);
    if (err) {
        fprintf(stderr, "Failed to attach BPF skeleton\n");
        goto cleanup;
    }


    /* Set up ring buffer polling */
    struct ring_buffer *rb = NULL;
    rb = ring_buffer__new(bpf_map__fd(skel->maps.completion_events), handle_event, NULL, NULL);
    if (!rb) {
        fprintf(stderr, "Failed to create ring buffer\n");
        goto cleanup;
    }


    struct timespec sample_ts; // sample timestamp
    char timestamp[64];

    // sample and print every second
    while (!exiting) {
        clock_gettime(CLOCK_REALTIME, &sample_ts);
        // clock_gettime(CLOCK_MONOTONIC, &ktime); // TODO check twice and pick lowest diff in case of an interrupt/inv ctx switch

        struct tm *tm = localtime(&sample_ts.tv_sec);
        strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%S", tm);
        snprintf(timestamp + 19, sizeof(timestamp) - 19, ".%06ld", sample_ts.tv_nsec / 1000);

        // Print output (kernel pid printed as TID in userspace and kernel tgid as PID)
        if (output_csv) {
            if (!header_printed) {
                fprintf(sample_output_file, 
                       "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n",
                       "TIMESTAMP", "TID", "TGID", "STATE", "USER", "EXE", "COMM",
                       "SYSCALL_PASSIVE", "SYSCALL_ACTIVE", "SC_ENTRY_TIME", "SC_US_SO_FAR", 
                       "SC_SEQ_NUM", "ARG0", "FILENAME");
                fflush(sample_output_file);
            }
        } else {
            printf("%-26s  %7s  %7s  %-6s  %-16s  %-20s  %-16s  %-20s  %-20s  %-26s  %16s  %12s  %-16s  %s\n",
                   "TIMESTAMP", "TID", "TGID", "STATE", "USER", "EXE", "COMM",
                   "SYSCALL_PASSIVE", "SYSCALL_ACTIVE", "SC_ENTRY_TIME", "SC_US_SO_FAR", "SC_SEQ_NUM", "ARG0", "FILENAME");
        }

        header_printed = true;

        // iterate through all tasks (BPF task iterator program may choose to not emit some non-interesting tasks)
        iter_fd = bpf_iter_create(bpf_link__fd(skel->links.get_tasks));
        if (iter_fd < 0) {
            err = -1;
            fprintf(stderr, "Failed to create iter\n");
            goto cleanup;
        }

        while (true) {
            ret = read(iter_fd, &buf, sizeof(struct task_info));
            if (ret < 0) {
                if (errno == EAGAIN)
                    continue;
                err = -errno;
                break;
            }
            if (ret == 0)
                break;


            // event duration so far, from its start to sampling point
            // the eBPF side sets all ongoing syscalls start time to program start time
            __s64 duration_ns = 0;
            if (buf.storage.sc_enter_time) 
                duration_ns = buf.storage.sample_ktime - buf.storage.sc_enter_time;

            // knowing the duration so far (when sampled), calculate the event start time,
            // without relying on ktime to walltime conversion
            char   sc_start_time_str[64];
            struct timespec sc_start_timespec = subtract_ns_from_timespec(sample_ts, duration_ns);
            struct tm *sc_start_tm = localtime(&sc_start_timespec.tv_sec);

            strftime(sc_start_time_str, sizeof(sc_start_time_str), "%Y-%m-%dT%H:%M:%S", sc_start_tm);
            snprintf(sc_start_time_str + 19, sizeof(sc_start_time_str) - 19, ".%06ld", sc_start_timespec.tv_nsec / 1000);

            if (output_csv) {
               fprintf(sample_output_file,
                       "%s,%d,%d,%s,\"%s\",\"%s\",\"%s\",%s,%s,%s,%lld,%lld,%llx,\"%s\"\n",
                       timestamp,
                       buf.pid,
                       buf.tgid,
                       get_task_state(buf.state),
                       getusername(buf.euid),
                       buf.exe_file,
                       buf.comm,
                       (buf.flags & PF_KTHREAD) ? "-" : safe_syscall_name(buf.syscall_nr),
                       (buf.flags & PF_KTHREAD) ? "-" : ( // if sc_sequence_num == 0, we are in a syscall that started before xcapture ran
                           buf.storage.sc_sequence_num ? safe_syscall_name(buf.storage.in_syscall_nr) : "-"
                       ),
                       buf.storage.sc_enter_time > 0 ? sc_start_time_str : "",
                       (long long int) 0, // in CSV mode, use outer join with event completion records instead of "duration so far"
                       buf.storage.sc_sequence_num,
                       buf.syscall_args[0],
                       buf.filename[0] ? buf.filename : "-"
               );
               fflush(sample_output_file);
            }
            else {
                printf("%-26s  %7d  %7d  %-6s  %-16s  %-20s  %-16s  %-20s  %-20s  %-26s  %'16lld  %12lld  %-16llx  %s\n",
                    timestamp,
                    buf.pid,
                    buf.tgid,
                    get_task_state(buf.state),
                    getusername(buf.euid),
                    buf.exe_file,
                    buf.comm,
                    buf.flags & PF_KTHREAD ? "-" : safe_syscall_name(buf.syscall_nr),
                    (buf.flags & PF_KTHREAD) ? "-" : (
                        buf.storage.sc_sequence_num ? safe_syscall_name(buf.storage.in_syscall_nr) : "-"
                    ),
                    buf.storage.sc_enter_time > 0 ? sc_start_time_str : "-",
                    (duration_ns / 1000), // this is cumulative for long waits over samples, so don't sum it up
                    buf.storage.sc_sequence_num,
                    buf.syscall_args[0], 
                    buf.filename[0] ? buf.filename : "-"
                );
            }
        }


        /* Ring buffer poll for event completions */
        err = ring_buffer__poll(rb, 100 /* timeout, ms */);
        if (err < 0) {
            fprintf(stderr, "Error polling ring buffer: %d\n", err);
            goto cleanup;
        }


        if (!output_csv) {
            printf("\n");
        }

        // avoid seeing half-written lines when redirecting to a file
        fflush(stdout);

        close(iter_fd);

        // sleep for 1 second for now (even if prev sample took some time)
        // TODO sleep N microseconds less, based on how long the last sample took (like in original v1 xcapture.c)
        if (!exiting)
            usleep(1000000);
    }

    cleanup:
    /* Clean up */
    fflush(stdout);
    close(iter_fd); /* the fd might already be closed above, but this would just return an EBADF then */

    /* Release event completion ring buffer */
    if (rb) {
        ring_buffer__free(rb);
    }

    xcapture_bpf__destroy(skel);

    return err < 0 ? -err : 0;
}
