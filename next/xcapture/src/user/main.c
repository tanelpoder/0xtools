// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024-2038 Tanel Poder [0x.tools]

#include <stdio.h>
#include <unistd.h>
#include <pwd.h>
#include <time.h>
#include <locale.h>
#include <signal.h>
#include <argp.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <errno.h>
#include <bpf/bpf.h>
#include <bpf/libbpf.h>

#include <arpa/inet.h>  // For inet_ntop()
#include <netinet/in.h> // For IPPROTO_* constants

#include "task/task.skel.h"
#include "syscall/syscall.skel.h"
#include "io/iorq.skel.h"

#include "blk_types.h"
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

#include "user/task_handler.h"
#include "user/tracking_handler.h"

// globals, set once or only by one function
pid_t mypid = 0;
bool output_csv = false;
bool output_verbose = false;
bool dump_stack_traces = false;

static int  sample_freq = 1;        // default 1 Hz
static bool show_all = false;       // show tasks in any state (except idle kernel workers)
static bool passive_only = false;   // allow only passive sampling with no overhead to other tasks
static bool track_syscalls = false; // but for maximum awesomeness you can enable
static bool track_iorq = false;     // tracking for additional events (syscall, iorq)

static char *output_dirname;
struct output_files files = {0};
static char *kallsyms_path = "/proc/kallsyms";
struct time_correlation tcorr = {0};

// XCAP_BUFSIZE is later used in setbuffer() calls too
#define XCAP_BUFSIZ 256*1024

char samplebuf[XCAP_BUFSIZ];
char syscbuf[XCAP_BUFSIZ];
char iorqbuf[XCAP_BUFSIZ];
char stackbuf[XCAP_BUFSIZ];

// Version and help string
const char *argp_program_version = "xcapture 3.0.0";
const char *argp_program_bug_address = "https://github.com/tanelpoder/0xtools";
const char argp_program_doc[] =
"xcapture thread state tracking & sampling by Tanel Poder [0x.tools]\n"
"\n"
"USAGE: xcapture [--help] [-o OUTPUT_DIRNAME] [-t TID] [-p PID]\n"
"\n"
"EXAMPLES:\n"
"    xcapture              # output formatted text to stdout\n"
"    xcapture -F 20        # sample at 20 Hz\n"
"    xcapture -o /tmp/data # write CSV files to /tmp/data directory\n";

// Command line options
static const struct argp_option opts[] = {
    { "all", 'a', NULL, 0, "Show all tasks including sleeping ones" },
    { "passive", 'p', NULL, 0, "Allow only passive task state sampling" },
    { "track", 't', "iorq,syscall", 0, "Enable active tracking with tracepoints & probes" },
    { "track-all", 'T', NULL, 0, "Enable all available tracking components" },
    { "freq", 'F', "HZ", 0, "Sampling frequency in Hz (default: 1)" },
    { "output-dir", 'o', "DIR", 0, "Write CSV files to specified directory" },
    { "stack-traces", 's', NULL, 0, "Dump kernel stack traces to CSV files" },
    { "kallsyms-file", 'k', "FILE", 0, "kallsyms file (default: /proc/kallsyms)" },
    { "verbose", 'v', NULL, 0, "Report sampling metrics even in CSV output mode" },
    {},
};

// argument parser
static error_t parse_arg(int key, char *arg, struct argp_state *state)
{
    switch (key) {
        case 'o':
            output_dirname = arg;
            output_csv = true;
            break;
        case 'F':
            errno = 0;
            sample_freq = strtol(arg, NULL, 10);
            if (errno || sample_freq <= 0) {
                fprintf(stderr, "Invalid sampling frequency. Must be a positive integer.\n");
                argp_usage(state);
            }
            break;
        case 'a':
            show_all = true;
            break;
        case 's':
            dump_stack_traces = true;
            break;
        case 'k':
            kallsyms_path = arg;
            break;
        case 'v':
            output_verbose = true;
            break;
        case 'p':
            passive_only = true;
            break;
        case 't':
            // Parse comma-separated tracking components
            if (strstr(arg, "syscall"))
                track_syscalls = true;
            if (strstr(arg, "iorq"))
                track_iorq = true;
            break;
        case 'T':
            track_syscalls = true;
            track_iorq = true;
            break;
        case ARGP_KEY_ARG:
            argp_usage(state);
            break;
        default:
            return ARGP_ERR_UNKNOWN;
    }
    return 0;
}

// Add function to ensure output directory exists
static int ensure_output_dirname() {
    struct stat st = {0};

    if (stat(output_dirname, &st) == -1) {
        if (mkdir(output_dirname, 0750) == -1) {
            fprintf(stderr, "Failed to create output directory %s: %s\n",
                    output_dirname, strerror(errno));
            return -1;
        }
    } else if (!S_ISDIR(st.st_mode)) {
        fprintf(stderr, "%s exists but is not a directory\n", output_dirname);
        return -1;
    }

    return 0;
}

// handle CTRL+C and sigpipe etc
static volatile bool exiting = false;

static void sig_handler(int sig)
{
    exiting = true;
}

// Check if fd is open before trying to close it in signal handling/exit
int is_fd_open(int fd)
{
    return fcntl(fd, F_GETFD) != -1 || errno != EBADF;
}

// Simple hash table for caching username lookups
#define USERNAME_CACHE_SIZE 256

struct username_entry {
    uid_t uid;
    bool valid;
    char username[64];
};

static struct username_entry username_cache[USERNAME_CACHE_SIZE] = {0};

// Simple hash function for UIDs
static inline unsigned int hash_uid(uid_t uid)
{
    return uid % USERNAME_CACHE_SIZE;
}

// translate uid to user name with hash table caching
const char *getusername(uid_t uid)
{
    // Check if the UID is already in cache
    unsigned int bucket = hash_uid(uid);

    if (username_cache[bucket].valid && username_cache[bucket].uid == uid) {
        return username_cache[bucket].username;
    }

    // Not in cache or bucket collision, look it up
    struct passwd *pw = getpwuid(uid);
    if (pw) {
        // Update cache at the calculated bucket (potentially overwriting)
        username_cache[bucket].uid = uid;
        username_cache[bucket].valid = true;
        strncpy(username_cache[bucket].username, pw->pw_name, sizeof(username_cache[bucket].username) - 1);
        username_cache[bucket].username[sizeof(username_cache[bucket].username) - 1] = '\0';

        return username_cache[bucket].username;
    }

    // UID not found, cache and return the "not found" value
    username_cache[bucket].uid = uid;
    username_cache[bucket].valid = true;
    strcpy(username_cache[bucket].username, "-");

    return username_cache[bucket].username;
}

const char *format_task_state(__u32 state)
{
    static char hex_state[32];  // Buffer for unknown states

    switch (state & 0xFF) {
    case 0x0000: return "RUN";   // RUNNING
    case 0x0001: return "SLEEP"; // INTERRUPTIBLE
    case 0x0002: return "DISK";  // UNINTERRUPTIBLE
    case 0x0004: return "STOPPED";
    case 0x0200: return "WAKING";
    case 0x0400: return "NOLOAD";
    case 0x0402: return "IDLE";
    case 0x0800: return "NEW";
    default:
        snprintf(hex_state, sizeof(hex_state), "0x%x", state);
        return hex_state;
    }
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

const char *safe_syscall_name(__s32 syscall_nr)
{
    static char unknown_str[32];

    if (syscall_nr < 0)
        return "-";

    if (syscall_nr < NR_SYSCALLS && sysent0[syscall_nr].name != NULL) {
        return sysent0[syscall_nr].name;
    }

    snprintf(unknown_str, sizeof(unknown_str), "%d", syscall_nr);
    return unknown_str;
}

// subtract nanoseconds from timespec
struct timespec sub_ns_from_ts(struct timespec ts, __u64 ns)
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

void get_str_from_ts(struct timespec ts, char *buf, size_t bufsize) {
    struct tm *tm = localtime(&ts.tv_sec);
    strftime(buf, bufsize, "%Y-%m-%dT%H:%M:%S", tm);
    snprintf(buf + 19, bufsize - 19, ".%06ld", ts.tv_nsec / 1000);
}

// get walltime timespec from monotonic clock ns (bpf ktime)
struct timespec get_wall_from_mono(struct time_correlation *tcorr, __u64 bpf_time)
{
    struct timespec result = tcorr->wall_time;
    __u64 mono_ns = tcorr->mono_time.tv_sec * 1000000000ULL + tcorr->mono_time.tv_nsec;
    __s64 ns_diff = bpf_time - mono_ns;

    result.tv_nsec += ns_diff % 1000000000;
    result.tv_sec += ns_diff / 1000000000;

    if (result.tv_nsec >= 1000000000) {
        result.tv_nsec -= 1000000000;
        result.tv_sec++;
    } else if (result.tv_nsec < 0) {
        result.tv_nsec += 1000000000;
        result.tv_sec--;
    }

    return result;
}

struct timespec get_ts_diff(struct timespec end, struct timespec start) {
    struct timespec diff;
    if ((end.tv_nsec - start.tv_nsec) < 0) {
        diff.tv_sec = end.tv_sec - start.tv_sec - 1;
        diff.tv_nsec = 1000000000 + end.tv_nsec - start.tv_nsec;
    } else {
        diff.tv_sec = end.tv_sec - start.tv_sec;
        diff.tv_nsec = end.tv_nsec - start.tv_nsec;
    }
    return diff;
}

char* get_hourly_filename(const char* base_name, const struct tm *tm) {
    static char filename[PATH_MAX];
    snprintf(filename, sizeof(filename), "%s/%s_%04d-%02d-%02d.%02d.csv",
             output_dirname,
             base_name,
             tm->tm_year + 1900,
             tm->tm_mon + 1,
             tm->tm_mday,
             tm->tm_hour);
    return filename;
}

void close_output_files(struct output_files *files) {
    if (files)
        fflush(NULL); // flush all open file streams

    if (files->sample_file) {
        fclose(files->sample_file);
        files->sample_file = NULL;
    }
    if (files->sc_completion_file) {
        fclose(files->sc_completion_file);
        files->sc_completion_file = NULL;
    }
    if (files->iorq_completion_file) {
        fclose(files->iorq_completion_file);
        files->iorq_completion_file = NULL;
    }
    if (files->kstack_file) {
        fclose(files->kstack_file);
        files->kstack_file = NULL;
    }
}

// socket inet connection endpoints
const char *format_connection(const struct socket_info *si, char *buf, size_t buflen)
{
    char src[INET6_ADDRSTRLEN], dst[INET6_ADDRSTRLEN];
    const char *proto = (si->protocol == IPPROTO_TCP) ? "TCP" :
                        (si->protocol == IPPROTO_UDP) ? "UDP" : "[unknown]";

    if (si->family == AF_INET) {
        struct in_addr src_addr = { .s_addr = si->saddr_v4 };
        struct in_addr dst_addr = { .s_addr = si->daddr_v4 };
        inet_ntop(AF_INET, &src_addr, src, sizeof(src));
        inet_ntop(AF_INET, &dst_addr, dst, sizeof(dst));
    } else {
        inet_ntop(AF_INET6, &si->saddr_v6, src, sizeof(src));
        inet_ntop(AF_INET6, &si->daddr_v6, dst, sizeof(dst));
    }

    snprintf(buf, buflen, "%s %s:%u->%s:%u",
             proto, src, ntohs(si->sport), dst, ntohs(si->dport));

    return buf;
}

FILE* open_csv_file(const char *filename, const char *header) {
    FILE *f = fopen(filename, "a");
    if (!f) {
        fprintf(stderr, "Failed to open file %s: %s\n", filename, strerror(errno));
        return NULL;
    }

    // If file size is zero, then write CSV header line first
    fseek(f, 0, SEEK_END);
    if (ftell(f) == 0 && header) {
        fprintf(f, "%s\n", header);
        fflush(f);
    }

    return f;
}

int create_output_files(struct output_files *files, const struct tm *tm) {
    // Close any existing files first
    close_output_files(files);

    // Open samples file (nanoseconds for CSV output)
    files->sample_file = open_csv_file(
            get_hourly_filename(SAMPLE_CSV_FILENAME, tm),
            "TIMESTAMP,TID,TGID,STATE,USERNAME,EXE,COMM,SYSCALL,SYSCALL_ACTIVE,"
            "SYSC_ENTRY_TIME,SYSC_NS_SO_FAR,SYSC_SEQ_NUM,IORQ_SEQ_NUM,"
            "SYSC_ARG1,SYSC_ARG2,SYSC_ARG3,SYSC_ARG4,SYSC_ARG5,SYSC_ARG6,"
            "FILENAME,CONNECTION,SYSC_INF_DSC,SYSC_INF_VAL"
        );
    if (!files->sample_file)
        return -1;
    else
        setbuffer(files->sample_file, samplebuf, XCAP_BUFSIZ);

    // Open syscall completion file
    files->sc_completion_file = open_csv_file(
        get_hourly_filename(SYSC_COMPLETION_CSV_FILENAME, tm),
        "TYPE,TID,TGID,SYSCALL_NAME,DURATION_NS,SYSC_RET_VAL,SYSC_SEQ_NUM,SYSC_ENTER_TIME"
    );
    if (!files->sc_completion_file) {
        close_output_files(files);
        return -1;
    } else {
        setbuffer(files->sc_completion_file, syscbuf, XCAP_BUFSIZ);
    }

    // Open iorq completion file
    files->iorq_completion_file = open_csv_file(
        get_hourly_filename(IORQ_COMPLETION_CSV_FILENAME, tm),
        "TYPE,INSERT_TID,INSERT_TGID,ISSUE_TID,ISSUE_TGID,COMPLETE_TID,COMPLETE_TGID,"
        "DEV_MAJ,DEV_MIN,SECTOR,BYTES,IORQ_FLAGS,IORQ_SEQ_NUM,"
        "DURATION_NS,SERVICE_NS,QUEUED_NS,ISSUE_TIMESTAMP,ERROR"
    );
    if (!files->iorq_completion_file) {
        close_output_files(files);
        return -1;
    } else {
        setbuffer(files->iorq_completion_file, iorqbuf, XCAP_BUFSIZ);
    }

    // Open kernel stack trace file
    files->kstack_file = open_csv_file(
        get_hourly_filename(KSTACK_CSV_FILENAME, tm),
         "TIMESTAMP,TID,TGID,STACK_HASH,ADDR_LIST"
    );
    if (!files->kstack_file) {
        close_output_files(files);
        return -1;
    } else {
        setbuffer(files->kstack_file, stackbuf, XCAP_BUFSIZ);
    }

    // Update current timestamp components
    files->current_year = tm->tm_year;
    files->current_month = tm->tm_mon;
    files->current_day = tm->tm_mday;
    files->current_hour = tm->tm_hour;

    return 0;
}

// use the current timestamp to update all open file types
int check_and_rotate_files(struct output_files *files) {
    // Always use current time for comparison and new file creation
    time_t now = time(NULL);
    struct tm *current_tm = localtime(&now);

    if (current_tm->tm_year != files->current_year  ||
        current_tm->tm_mon  != files->current_month ||
        current_tm->tm_mday != files->current_day   ||
        current_tm->tm_hour != files->current_hour)
    {
        return create_output_files(files, current_tm);
    }
    return 0;
}

// let's go!
int main(int argc, char **argv)
{
    mypid = getpid();
    struct task_bpf *task_skel = {0};
    struct syscall_bpf *syscall_skel = {0};
    struct iorq_bpf *iorq_skel = {0};

    int iter_fd = 0;
    int err = 0;

    // Add argp structure and parsing
    static const struct argp argp = {
        .options = opts,
        .parser = parse_arg,
        .doc = argp_program_doc,
    };

    err = argp_parse(&argp, argc, argv, 0, NULL, NULL);
    if (err)
        return err;

    if (passive_only && (track_syscalls || track_iorq)) {
        fprintf(stderr, "Error: conflicting command line arguments\n");
        fprintf(stderr, "     --passive (-p) does not allow enabling active tracking probes\n\n");
        return 1;
    }

    static struct output_files files = {
        .sample_file = NULL,
        .sc_completion_file = NULL,
        .iorq_completion_file = NULL,
        .kstack_file = NULL,
        .current_year  = -1,
        .current_month = -1,
        .current_day   = -1,
        .current_hour  = -1
    };

    if (output_csv) {
        err = ensure_output_dirname();
        if (err)
            return err;

        err = check_and_rotate_files(&files);
        if (err)
            return err;
    }

    signal(SIGINT,  sig_handler);
    signal(SIGTERM, sig_handler);
    signal(SIGPIPE, sig_handler);

    // output locale and reduce STDOUT output syscalls
    setlocale(LC_ALL,"en_US.UTF-8");
    char outbuf[XCAP_BUFSIZ];
    setbuffer(stdout, outbuf, XCAP_BUFSIZ);

    // declare ringbufs
    struct ring_buffer *task_rb = NULL;
    struct ring_buffer *tracking_rb = NULL;

    // always load and attach the passive task sampler BPF program
    task_skel = task_bpf__open();
    if (!task_skel) {
        fprintf(stderr, "Failed to open BPF skeleton: task\n");
        goto cleanup;
    }

    err = task_bpf__load(task_skel);
    if (err) {
        fprintf(stderr, "Failed to load BPF skeleton: task\n");
        goto cleanup;
    }

    err = task_bpf__attach(task_skel);
    if (err) {
        fprintf(stderr, "Failed to attach BPF skeleton: task\n");
        goto cleanup;
    }

    /* Only load active tracking probes if requested */
    if (!passive_only) {
        /* Only set up active tracking ring buffer if needed */
        tracking_rb = ring_buffer__new(bpf_map__fd(task_skel->maps.completion_events), handle_tracking_event, NULL, NULL);
        if (!tracking_rb) {
            fprintf(stderr, "Failed to create tracking events ring buffer\n");
            goto cleanup;
        }

        if (track_syscalls) {
            syscall_skel = syscall_bpf__open_and_load();
            if (!syscall_skel) {
                fprintf(stderr, "Failed to open and load BPF skeleton: syscall\n");
                goto cleanup;
            }

            err = syscall_bpf__attach(syscall_skel);
            if (err) {
                fprintf(stderr, "Failed to attach BPF skeleton: syscall\n");
                goto cleanup;
            }
        }

        // currently loading the iorq_tracking skeleton & map anyway
        // for map unpin & cleanup code simplicity...
        iorq_skel = iorq_bpf__open_and_load();
        if (!iorq_skel) {
            fprintf(stderr, "Failed to open and load BPF skeleton: iorq\n");
            goto cleanup;
        }

        // ... but actually attaching to the tracepoint only if iorq_tracking is enabled
        // there's no CPU overhead if iorq tracking is not actually enabled
        if (track_iorq) {
            err = iorq_bpf__attach(iorq_skel);
            if (err) {
                fprintf(stderr, "Failed to attach BPF skeleton: iorq\n");
                goto cleanup;
            }
        }
    }

    /* Always set up the passive task sampler ring buffer */
    task_rb = ring_buffer__new(bpf_map__fd(task_skel->maps.task_samples), handle_task_event, NULL, NULL);
    if (!task_rb) {
        fprintf(stderr, "Failed to create task samples ring buffer\n");
        goto cleanup;
    }

    /* Interesting task filtering config */
    struct filter_config cfg = {
        .show_all = show_all,
        .state_mask = TASK_INTERRUPTIBLE
    };

    int filter_fd = bpf_map__fd(task_skel->maps.filter_config_map);
    int key = 0;

    err = bpf_map_update_elem(filter_fd, &key, &cfg, BPF_ANY);
    if (err) {
        fprintf(stderr, "Failed to update filter config map: %d\n", err);
        goto cleanup;
    }

    char timestamp[64];  // human readable timestamp string

    static struct timespec loop_start_ts; // for adjusting sleep duration between loop iterations
    static struct timespec loop_end_ts;
    static struct timespec iter_fd_start_ts;
    static struct timespec iter_fd_end_ts;
    static struct timespec iter_fd_inner_start_ts;
    static struct timespec iter_fd_inner_end_ts;

    long target_interval_ns = 1000000000L / sample_freq;

    // periodically sample and write task states to ringbuf
    while (!exiting) {
        clock_gettime(CLOCK_MONOTONIC, &loop_start_ts);
        clock_gettime(CLOCK_REALTIME, &tcorr.wall_time);
        clock_gettime(CLOCK_MONOTONIC, &tcorr.mono_time);

        struct tm *tm = localtime(&tcorr.wall_time.tv_sec);
        strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%S", tm);
        snprintf(timestamp + 19, sizeof(timestamp) - 19, ".%06ld", tcorr.wall_time.tv_nsec / 1000);

        // Print headers for every sampling iteration in plain text mode (microseconds for this "dev" mode)
        if (!output_csv) {
            printf("%-26s  %6s  %7s  %7s  %-6s  %-6s  %-6s  %-4s  %-16s  %-20s  %-16s  %-20s  %-20s  %16s"
                   "  %16s  %-20s  %-40s  %-26s  %12s  %12s  %12s\n",
                   "TIMESTAMP", "OFF_US", "TID", "TGID", "STATE", "ON_CPU", "ON_RQ", "MIGP", "USERNAME",
                   "EXE", "COMM", "SYSCALL", "SYSCALL_ACTIVE", "SYSC_US_SO_FAR", "SYSC_ARG1", "FILENAME",
                   "CONNECTION", "SYSC_ENTRY_TIME", "SYSC_SEQ_NUM", "SYSC_INF_DSC", "SYSC_INF_VAL"
            );
        }

        // Trigger the task iterator to collect data - it will send results to the ring buffer
        clock_gettime(CLOCK_MONOTONIC, &iter_fd_start_ts);
        iter_fd = bpf_iter_create(bpf_link__fd(task_skel->links.get_tasks));
        if (iter_fd < 0) {
            err = -1;
            fprintf(stderr, "Failed to create iter\n");
            goto cleanup;
        }

        // Just trigger the iterator - we're not reading from it directly
        // This causes the get_tasks BPF program to submit task samples to ring buffer
        char dummy[4];
        clock_gettime(CLOCK_MONOTONIC, &iter_fd_inner_start_ts);
        read(iter_fd, dummy, sizeof(dummy)); // this runs the kernel sampling
        clock_gettime(CLOCK_MONOTONIC, &iter_fd_inner_end_ts);
        close(iter_fd);
        clock_gettime(CLOCK_MONOTONIC, &iter_fd_end_ts);

        // Poll the ring buffer for latest task samples
        err = ring_buffer__poll(task_rb, 0 /* timeout, ms */);
        if (err < 0) {
            fprintf(stderr, "Error polling task ring buffer: %d\n", err);
            goto cleanup;
        }

        // Only poll event completion tracking ring buffer if is set up and used
        if (!passive_only && tracking_rb) {
            err = ring_buffer__poll(tracking_rb, 0 /* timeout, ms */);
            if (err < 0) {
                fprintf(stderr, "Error polling tracking ring buffer: %d\n", err);
                goto cleanup;
            }
        }

        if (!output_csv || output_verbose) {
            printf("\n");
            printf("Wall clock time: %s\n", timestamp);
        }

        // exact sleep duration depends on how long it took to actively work on this iteration
        clock_gettime(CLOCK_MONOTONIC, &loop_end_ts);
        struct timespec sampling_time = get_ts_diff(loop_end_ts, loop_start_ts);
        long sampling_ns = sampling_time.tv_sec * 1000000000L + sampling_time.tv_nsec;
        long sleep_ns = target_interval_ns - sampling_ns;

        struct timespec iter_fd_time = get_ts_diff(iter_fd_end_ts, iter_fd_start_ts);
        long iter_fd_ns = iter_fd_time.tv_sec * 1000000000L + iter_fd_time.tv_nsec;
        struct timespec iter_fd_inner_time = get_ts_diff(iter_fd_inner_end_ts, iter_fd_inner_start_ts);
        long iter_fd_inner_ns = iter_fd_inner_time.tv_sec * 1000000000L + iter_fd_inner_time.tv_nsec;

        // Only sleep if the previous processing hasn't exceeded the requested interval
        if (!exiting && sleep_ns > 0) {
            if (!output_csv || output_verbose) {
                printf("Sampling took:   %'ld us (iter_fd: %'ld us, inner: %'ld us), sleeping for %'ld us\n",
                        sampling_ns / 1000L, iter_fd_ns / 1000L, iter_fd_inner_ns / 1000L, sleep_ns / 1000L);
                printf("\n");
            }
            fflush(NULL);
            usleep(sleep_ns / 1000); // Convert ns to microseconds for usleep
        } else {
            if (!output_csv || output_verbose) {
                printf("Warning: Sampling took longer than display interval (%ld.%06ld s)\n",
                    sampling_time.tv_sec, sampling_time.tv_nsec / 1000);
                printf("\n");
                fflush(NULL);
            }
        }
    }

cleanup:
    // flush all open file streams and close fds
    fflush(NULL);
    if (is_fd_open(iter_fd)) close(iter_fd);
    if (output_csv) close_output_files(&files);

    // Unpin maps before destroying skeletons
    if (task_skel) {
        bpf_map__unpin(task_skel->maps.filter_config_map, NULL);
        bpf_map__unpin(task_skel->maps.task_storage, NULL);
        bpf_map__unpin(task_skel->maps.completion_events, NULL);
        bpf_map__unpin(task_skel->maps.task_samples, NULL);
    }

    // cleanup BUG: if iorq_tracking prog failed to load due to verifier
    // its map lingers around (sudo rm /sys/fs/bpf/iorq_tracking)
    if (iorq_skel)    bpf_map__unpin(iorq_skel->maps.iorq_tracking, NULL);
    if (syscall_skel) syscall_bpf__destroy(syscall_skel);
    if (iorq_skel)    iorq_bpf__destroy(iorq_skel);
    if (task_skel)    task_bpf__destroy(task_skel);

    if (tracking_rb)  ring_buffer__free(tracking_rb);
    if (task_rb)      ring_buffer__free(task_rb);

    return err < 0 ? -err : 0;
}
