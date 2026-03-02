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
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>
#include <strings.h>
#include <ctype.h>
#include <limits.h>
#include <bpf/bpf.h>
#include <bpf/libbpf.h>

#include "task/task.skel.h"
#include "syscall/syscall.skel.h"
#include "io/iorq.skel.h"

#include "blk_types.h"
#include "xcapture.h"
#include "xcapture_user.h"
#include "xcapture_context.h"
#include "columns.h"
#include "cgroup_cache.h"

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

#ifdef USE_BLAZESYM
#include "blazesym.h"
#endif

// globals, set once or only by one function
static struct xcapture_context g_ctx = {0};

static enum libbpf_print_level g_libbpf_log_level = LIBBPF_WARN;

static int libbpf_log_print(enum libbpf_print_level level, const char *format, va_list args)
{
    if (level > g_libbpf_log_level)
        return 0;

    return vfprintf(stderr, format, args);
}

static bool parse_libbpf_log_level(const char *value, enum libbpf_print_level *level_out)
{
    if (!value || !*value)
        return false;

    if (strcasecmp(value, "debug") == 0) {
        *level_out = LIBBPF_DEBUG;
        return true;
    }

    if (strcasecmp(value, "info") == 0) {
        *level_out = LIBBPF_INFO;
        return true;
    }

    if (strcasecmp(value, "warn") == 0 || strcasecmp(value, "warning") == 0) {
        *level_out = LIBBPF_WARN;
        return true;
    }

    return false;
}

static void setup_libbpf_logging(void)
{
    const char *env = getenv("LIBBPF_LOG_LEVEL");
    enum libbpf_print_level level = LIBBPF_WARN;

    if (env && env[0]) {
        if (!parse_libbpf_log_level(env, &level)) {
            fprintf(stderr,
                    "Warning: ignoring invalid LIBBPF_LOG_LEVEL value '%s' (expected warn, info, or debug)\n",
                    env);
            level = LIBBPF_WARN;
        }
    }

    g_libbpf_log_level = level;
    libbpf_set_print(libbpf_log_print);
}

static const char *get_bpf_pin_path(void)
{
    const char *env = getenv("XCAPTURE_BPFFS");
    if (env && env[0])
        return env;

    return NULL;
}

static void ensure_pin_path_directory(const char *path)
{
    if (!path || !path[0])
        return;

    if (mkdir(path, 0750) == -1 && errno != EEXIST) {
        if (errno != EACCES && errno != EROFS) {
            fprintf(stderr, "Warning: failed to create %s: %s\n", path, strerror(errno));
        }
    }
}

static int reuse_map(struct bpf_map *target, struct bpf_map *source)
{
    int fd;

    if (!target || !source)
        return 0;

    fd = bpf_map__fd(source);
    if (fd < 0)
        return fd;

    return bpf_map__reuse_fd(target, fd);
}

static int reuse_syscall_maps(struct syscall_bpf *sys_skel, struct task_bpf *task_skel)
{
    int err;

    if (!sys_skel || !task_skel)
        return 0;

    if ((err = reuse_map(sys_skel->maps.task_storage, task_skel->maps.task_storage))) return err;
    if ((err = reuse_map(sys_skel->maps.completion_events, task_skel->maps.completion_events))) return err;
    if ((err = reuse_map(sys_skel->maps.task_samples, task_skel->maps.task_samples))) return err;
    if ((err = reuse_map(sys_skel->maps.stack_traces, task_skel->maps.stack_traces))) return err;
    if ((err = reuse_map(sys_skel->maps.emitted_stacks, task_skel->maps.emitted_stacks))) return err;

    return 0;
}

static int reuse_iorq_maps(struct iorq_bpf *iorq_skel, struct task_bpf *task_skel)
{
    int err;

    if (!iorq_skel || !task_skel)
        return 0;

    if ((err = reuse_map(iorq_skel->maps.task_storage, task_skel->maps.task_storage))) return err;
    if ((err = reuse_map(iorq_skel->maps.completion_events, task_skel->maps.completion_events))) return err;
    if ((err = reuse_map(iorq_skel->maps.task_samples, task_skel->maps.task_samples))) return err;
    if ((err = reuse_map(iorq_skel->maps.stack_traces, task_skel->maps.stack_traces))) return err;
    if ((err = reuse_map(iorq_skel->maps.emitted_stacks, task_skel->maps.emitted_stacks))) return err;
    if ((err = reuse_map(iorq_skel->maps.iorq_tracking, task_skel->maps.iorq_tracking))) return err;

    return 0;
}

static int pin_map_to_root(struct bpf_map *map, const char *root)
{
    if (!map || !root || !root[0])
        return 0;

    const char *map_name = bpf_map__name(map);
    if (!map_name)
        return -EINVAL;

    char full_path[PATH_MAX];
    int written = snprintf(full_path, sizeof(full_path), "%s/%s", root, map_name);
    if (written < 0 || written >= (int)sizeof(full_path))
        return -ENAMETOOLONG;

    int err = bpf_map__pin(map, full_path);
    if (err && err != -EEXIST)
        return err;

    return 0;
}

static int pin_task_maps(struct task_bpf *task_skel, const char *root)
{
    int err;

    if (!task_skel || !root || !root[0])
        return 0;

    if ((err = pin_map_to_root(task_skel->maps.task_storage, root))) return err;
    if ((err = pin_map_to_root(task_skel->maps.completion_events, root))) return err;
    if ((err = pin_map_to_root(task_skel->maps.task_samples, root))) return err;
    if ((err = pin_map_to_root(task_skel->maps.stack_traces, root))) return err;
    if ((err = pin_map_to_root(task_skel->maps.emitted_stacks, root))) return err;
    if ((err = pin_map_to_root(task_skel->maps.iorq_tracking, root))) return err;

    return 0;
}

static void unpin_map_if_needed(struct bpf_map *map)
{
    if (!map)
        return;

    if (bpf_map__is_pinned(map))
        bpf_map__unpin(map, NULL);
}

#ifdef USE_BLAZESYM
blaze_symbolizer *g_symbolizer = NULL;
bool symbolize_stacks = true;  // Default to true when blazesym is available
#endif

// Track unique stack hashes seen in current iteration
#define MAX_UNIQUE_STACKS 131072
struct unique_stack {
    __u64 hash;
    bool is_kernel;
};
static struct unique_stack unique_stacks[MAX_UNIQUE_STACKS];
static int unique_stack_count = 0;

// Add a stack hash to the unique list if not already present
void add_unique_stack(__u64 hash, bool is_kernel) {
    if (hash == 0) return;
    
    // Check if already in list
    for (int i = 0; i < unique_stack_count; i++) {
        if (unique_stacks[i].hash == hash && unique_stacks[i].is_kernel == is_kernel) {
            return;
        }
    }
    
    // Add to list if space available
    if (unique_stack_count < MAX_UNIQUE_STACKS) {
        unique_stacks[unique_stack_count].hash = hash;
        unique_stacks[unique_stack_count].is_kernel = is_kernel;
        unique_stack_count++;
    }
}

// Reset unique stack list for new iteration
void reset_unique_stacks() {
    unique_stack_count = 0;
}

// Print all unique stacks collected during this iteration
void print_unique_stacks() {
    if (unique_stack_count == 0 || g_ctx.output_csv || !g_ctx.print_stack_traces) {
        return;
    }
    
    printf("\nStack traces:\n");
    
    for (int i = 0; i < unique_stack_count; i++) {
        const char *stack_str = lookup_cached_stack(unique_stacks[i].hash, unique_stacks[i].is_kernel);
        if (stack_str && stack_str[0]) {
            printf("%c:%016llx %s\n", 
                   unique_stacks[i].is_kernel ? 'K' : 'U',
                   unique_stacks[i].hash,
                   stack_str);
        } else {
            // No symbolized version available, just show the hash
            printf("%c:%016llx [no symbols]\n", 
                   unique_stacks[i].is_kernel ? 'K' : 'U',
                   unique_stacks[i].hash);
        }
    }
}

static int  sample_freq = 1;        // default 1 Hz
static bool show_all = false;       // show tasks in any state (except idle kernel workers)
static bool passive_only = false;   // allow only passive sampling with no overhead to other tasks
static bool track_syscalls = false; // but for maximum awesomeness you can enable
static bool track_iorq = false;     // tracking for additional events (syscall, iorq)
static bool dist_trace_http = false;
static bool dist_trace_https = false;
static bool dist_trace_grpc = false;
static bool dist_trace_enabled = false;
// Queue-based IORQ tracking has been removed - using hashtable approach
static int daemon_ports = 10000;    // default daemon ports heuristic threshold
static int max_iterations = -1;     // -1 means run forever, >0 means run N iterations
static pid_t filter_tgid = 0;       // filter by TGID (0 means no filter)

// Version and help string
const char *argp_program_version = "xcapture 3.0.3";
const char *argp_program_bug_address = "https://github.com/tanelpoder/0xtools";
const char argp_program_doc[] =
"xcapture thread state tracking & sampling by Tanel Poder [0x.tools]\n"
"\n"
"USAGE: xcapture [--help] [-o OUTPUT_DIRNAME] [-F HZ] [-p PID]\n"
"\n"
"EXAMPLES:\n"
"    xcapture              # output formatted text to stdout\n"
"    xcapture -F 20        # sample at 20 Hz\n"
"    xcapture -p 1234      # show only tasks with TGID 1234\n"
"    xcapture -o /tmp/data # write CSV files to /tmp/data directory\n";

// Command line options
enum {
    OPT_URING_DEBUG = 1000,
};

static const struct argp_option opts[] = {
    { "all", 'a', NULL, 0, "Show all tasks including sleeping ones", 0 },
    { "passive", 'P', NULL, 0, "Allow only passive task state sampling", 0 },
    { "pgid", 'p', "PID", 0, "Filter by process ID/thread group ID (shows all threads)", 0 },
    { "track", 't', "iorq,syscall", 0, "Enable active tracking with tracepoints & probes", 0 },
    { "dist-trace", 'D', "MODE[,MODE]", 0, "Enable distributed trace capture (http,https,grpc)", 0 },
    { "payload-trace", 'Y', NULL, 0, "Capture read/write payloads observed in tracked syscalls (experimental)", 0 },
    { "track-all", 'T', NULL, 0, "Enable all available tracking components", 0 },
    { "daemon-ports", 'd', "PORT", 0, "Port threshold for daemon connections (default: 10000)", 0 },
    { "freq", 'F', "HZ", 0, "Sampling frequency in Hz (default: 1)", 0 },
    { "output-dir", 'o', "DIR", 0, "Write CSV files to specified directory", 0 },
    { "kernel-stacks", 'k', NULL, 0, "Dump kernel stack traces to CSV files", 0 },
    { "print-stacks", 's', NULL, 0, "Print stack traces in stdout mode (requires -k and/or -u)", 0 },
    { "print-cgroups", 'C', NULL, 0, "Print cgroup paths in stdout mode", 0 },
    { "uring-debug", OPT_URING_DEBUG, NULL, 0, "Include io_uring debug fields in EXTRA_INFO", 0 },
    { "user-stacks", 'u', NULL, 0, "Dump userspace stack traces (requires -fno-omit-frame-pointer)", 0 },
    { "verbose", 'v', NULL, 0, "Report sampling metrics even in CSV output mode", 0 },
    { "wide-output", 'w', NULL, 0, "Show additional syscall timing columns in stdout mode", 0 },
    { "narrow-output", 'n', NULL, 0, "Show minimal columns (TID, TGID, STATE, USERNAME, EXE, COMM, SYSCALL, FILENAME)", 0 },
    { "get-columns", 'g', "COLUMNS", 0, "Custom column selection (comma-separated list or 'all')", 0 },
    { "append-columns", 'G', "COLUMNS", 0, "Append columns to the selected stdout layout", 0 },
    { "list", 'l', NULL, 0, "List all available columns and exit", 0 },
    { "iterations", 'i', "NUMBER", 0, "Exit after NUMBER sampling iterations (default: run forever)", 0 },
    { "help", 'h', NULL, 0, "Show this help message and exit", 0 },
#ifdef USE_BLAZESYM
    { "no-symbolize", 'N', NULL, 0, "Disable stack trace symbolization (show raw addresses)", 0 },
#endif
    {},
};

// argument parser
static error_t parse_arg(int key, char *arg, struct argp_state *state)
{
    switch (key) {
        case 'o':
            g_ctx.output_dirname = arg;
            g_ctx.output_csv = true;
            break;
        case 'F':
            errno = 0;
            sample_freq = strtol(arg, NULL, 10);
            if (errno || sample_freq <= 0) {
                fprintf(stderr, "Invalid sampling frequency. Must be a positive integer.\n");
                argp_usage(state);
                return EINVAL;
            }
            break;
        case 'a':
            show_all = true;
            break;
        case 'd':
            errno = 0;
            daemon_ports = strtol(arg, NULL, 10);
            if (errno || daemon_ports < 0 || daemon_ports > 65535) {
                fprintf(stderr, "Invalid daemon ports threshold. Must be 0-65535.\n");
                argp_usage(state);
                return EINVAL;
            }
            break;
        case 'k':
            g_ctx.dump_kernel_stack_traces = true;
            break;
        case 's':
            g_ctx.print_stack_traces = true;
            break;
        case 'C':
            g_ctx.print_cgroups = true;
            break;
        case OPT_URING_DEBUG:
            g_ctx.print_uring_debug = true;
            break;
        case 'u':
            g_ctx.dump_user_stack_traces = true;
            break;
        case 'v':
            g_ctx.output_verbose = true;
            break;
        case 'w':
            g_ctx.wide_output = true;
            break;
        case 'n':
            g_ctx.narrow_output = true;
            break;
        case 'g':
            if (!arg || !*arg) {
                fprintf(stderr, "Error: empty column list for --get-columns\n");
                argp_usage(state);
                return EINVAL;
            }
            g_ctx.custom_columns = strdup(arg);
            if (!g_ctx.custom_columns) {
                perror("strdup");
                return ENOMEM;
            }
            break;
        case 'G':
            if (!arg || !*arg) {
                fprintf(stderr, "Error: empty column list for --append-columns\n");
                argp_usage(state);
                return EINVAL;
            }
            if (g_ctx.append_columns) {
                fprintf(stderr, "Error: --append-columns (-G) may be specified only once\n");
                argp_usage(state);
                return EINVAL;
            }
            g_ctx.append_columns = strdup(arg);
            if (!g_ctx.append_columns) {
                perror("strdup");
                return ENOMEM;
            }
            break;
        case 'l':
            // This will be handled after argp_parse to use the columns module
            list_available_columns();
            exit(0);
            break;
        case 'h':
            argp_state_help(state, state->out_stream, ARGP_HELP_STD_HELP);
            exit(0);
            break;
        case 'P':
            passive_only = true;
            break;
        case 'p':
            errno = 0;
            filter_tgid = strtol(arg, NULL, 10);
            if (errno || filter_tgid <= 0) {
                fprintf(stderr, "Invalid process ID. Must be a positive integer.\n");
                argp_usage(state);
            }
            break;
        case 't':
            // Parse comma-separated tracking components
            if (strstr(arg, "syscall"))
                track_syscalls = true;
            if (strstr(arg, "iorq"))
                track_iorq = true;
            break;
        case 'D': {
            if (!arg || !*arg) {
                fprintf(stderr, "Invalid distributed trace modes. Expected comma-separated list.\n");
                argp_usage(state);
                return EINVAL;
            }

            char *modes = strdup(arg);
            if (!modes) {
                perror("strdup");
                argp_usage(state);
                return ENOMEM;
            }

            char *saveptr = NULL;
            for (char *token = strtok_r(modes, ",", &saveptr);
                 token;
                 token = strtok_r(NULL, ",", &saveptr))
            {
                while (isspace((unsigned char)*token)) token++;
                if (*token == '\0')
                    continue;

                char *end = token + strlen(token);
                while (end > token && isspace((unsigned char)*(end - 1))) {
                    *(--end) = '\0';
                }

                if (strcasecmp(token, "http") == 0) {
                    dist_trace_http = true;
                } else if (strcasecmp(token, "https") == 0) {
                    dist_trace_https = true;
                } else if (strcasecmp(token, "grpc") == 0) {
                    dist_trace_grpc = true;
                } else {
                    fprintf(stderr, "Unknown distributed trace mode '%s'. Supported: http, https, grpc.\n", token);
                    free(modes);
                    modes = NULL;
                    argp_usage(state);
                    return EINVAL;
                }
            }

            free(modes);

            dist_trace_enabled = dist_trace_http || dist_trace_https || dist_trace_grpc;
            if (!dist_trace_enabled) {
                fprintf(stderr, "No valid distributed trace modes supplied.\n");
                argp_usage(state);
                return EINVAL;
            }

            // Distributed tracing relies on syscall tracking for buffer access.
            track_syscalls = true;
            break;
        }
        case 'Y':
            g_ctx.payload_trace_enabled = true;
            track_syscalls = true;
            break;
        case 'T':
            track_syscalls = true;
            track_iorq = true;
            break;
        case 'i':
            errno = 0;
            max_iterations = strtol(arg, NULL, 10);
            if (errno || max_iterations <= 0) {
                fprintf(stderr, "Invalid iterations count. Must be a positive integer.\n");
                argp_usage(state);
            }
            break;
        case ARGP_KEY_ARG:
            argp_usage(state);
            break;
#ifdef USE_BLAZESYM
        case 'N':
            symbolize_stacks = false;
            break;
#endif
        default:
            return ARGP_ERR_UNKNOWN;
    }
    return 0;
}

// Add function to ensure output directory exists
static int ensure_output_dirname(void)
{
    struct stat st = {0};
    const char *dir = g_ctx.output_dirname ? g_ctx.output_dirname : DEFAULT_OUTPUT_DIR;

    if (stat(dir, &st) == -1) {
        if (mkdir(dir, 0750) == -1) {
            fprintf(stderr, "Failed to create output directory %s: %s\n",
                    dir, strerror(errno));
            return -1;
        }
    } else if (!S_ISDIR(st.st_mode)) {
        fprintf(stderr, "%s exists but is not a directory\n", dir);
        return -1;
    }

    return 0;
}

// handle CTRL+C and sigpipe etc
static volatile bool exiting = false;

static void sig_handler(int sig)
{
    (void)sig;
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

const char *format_task_state(__u32 state, int on_rq, int on_cpu, void *migration_pending)
{
    static char state_str[64];  // Buffer for state string with flags
    const char *base_state;
    
    // Determine base state string (TODO handle full bitset)
    switch (state & 0xFF) {
    case 0x0000: base_state = "RUN"; break;   // RUNNING
    case 0x0001: base_state = "SLEEP"; break; // INTERRUPTIBLE
    case 0x0002: base_state = "DISK"; break;  // UNINTERRUPTIBLE
    case 0x0004: base_state = "STOPPED"; break;
    case 0x0080: base_state = "DEAD"; break;
    case 0x0200: base_state = "WAKING"; break;
    case 0x0400: base_state = "NOLOAD"; break;
    case 0x0402: base_state = "IDLE"; break;
    case 0x0800: base_state = "NEW"; break;
    default:
        snprintf(state_str, sizeof(state_str), "0x%x", state);
        base_state = state_str;
    }
    
    // Copy base state to result buffer
    strncpy(state_str, base_state, sizeof(state_str) - 3);
    state_str[sizeof(state_str) - 3] = '\0';
    
    // Append flags
    // Q = on runqueue but not on CPU (waiting to run)
    if (on_rq > 0 && on_cpu == 0) {
        strcat(state_str, "Q");
    }
    if (migration_pending != NULL) {
        strcat(state_str, "M");
    }
    
    return state_str;
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

// let's go!
int main(int argc, char **argv)
{
    g_ctx.mypid = getpid();
    g_ctx.output_dirname = DEFAULT_OUTPUT_DIR;
    struct task_bpf *task_skel = NULL;
    struct syscall_bpf *syscall_skel = NULL;
    struct iorq_bpf *iorq_skel = NULL;
    struct bpf_program *get_tasks_prog = NULL;
    struct bpf_link *task_iter_link = NULL;
    int completion_fd = -1, task_samples_fd = -1, stack_traces_fd = -1;

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

    if (passive_only && (track_syscalls || track_iorq || dist_trace_enabled)) {
        fprintf(stderr, "Error: conflicting command line arguments\n");
        fprintf(stderr, "     --passive (-P) does not allow enabling active tracking probes\n\n");
        return 1;
    }

    // Note: -a and -p can be used together
    // -p selects which processes to examine
    // -a says to show all states (including sleeping) for selected processes

    // Check for mutually exclusive output format options
    int base_format_options = 0;
    if (g_ctx.wide_output) base_format_options++;
    if (g_ctx.narrow_output) base_format_options++;
    if (g_ctx.custom_columns) base_format_options++;

    if (base_format_options > 1) {
        fprintf(stderr, "Error: conflicting command line arguments\n");
        fprintf(stderr, "     Cannot use multiple output format options together:\n");
        fprintf(stderr, "     --wide-output (-w), --narrow-output (-n), --get-columns (-g)\n\n");
        return 1;
    }

    if (g_ctx.custom_columns && g_ctx.append_columns) {
        fprintf(stderr, "Error: conflicting command line arguments\n");
        fprintf(stderr, "     --get-columns (-g) cannot be combined with --append-columns (-G)\n\n");
        return 1;
    }

    // Check that format options are not used with CSV output
    if (g_ctx.output_csv && (base_format_options > 0 || g_ctx.append_columns)) {
        fprintf(stderr, "Error: conflicting command line arguments\n");
        fprintf(stderr, "     Output format options (-w, -n, -g, -G) cannot be used with CSV output (-o)\n");
        fprintf(stderr, "     CSV always outputs all columns for consistency\n\n");
        return 1;
    }

    if (g_ctx.output_csv) {
        err = ensure_output_dirname();
        if (err)
            return err;

        err = check_and_rotate_files(&g_ctx.files, &g_ctx);
        if (err)
            return err;
    }

    // Initialize cgroup cache
    cgroup_cache_init();

    signal(SIGINT,  sig_handler);
    signal(SIGTERM, sig_handler);
    signal(SIGPIPE, sig_handler);

    // output locale and reduce STDOUT output syscalls
    setlocale(LC_ALL,"en_US.UTF-8");
    char outbuf[XCAP_BUFSIZ];
    setbuffer(stdout, outbuf, XCAP_BUFSIZ);

    // declare ringbufs
    struct ring_buffer *task_rb = NULL;
    struct ring_buffer *stack_rb = NULL;
    struct ring_buffer *tracking_rb = NULL;

    setup_libbpf_logging();

    const char *bpf_pin_path = get_bpf_pin_path();
    ensure_pin_path_directory(bpf_pin_path);

    // Open the passive task sampler skeleton
    task_skel = task_bpf__open();
    if (!task_skel) { 
        fprintf(stderr, "Failed to open BPF skeleton: task\n"); 
        goto cleanup; 
    }

    if (!g_ctx.output_csv) {
        const char *columns_to_parse = NULL;

        if (g_ctx.custom_columns) {
            columns_to_parse = g_ctx.custom_columns;
        } else if (g_ctx.narrow_output) {
            columns_to_parse = narrow_columns;
        } else if (g_ctx.wide_output) {
            columns_to_parse = wide_columns;
        } else {
            columns_to_parse = normal_columns;
        }

        if (parse_column_list(columns_to_parse) < 0) {
            fprintf(stderr, "Failed to parse column list\n");
            goto cleanup;
        }

        if (g_ctx.append_columns) {
            if (append_column_list(g_ctx.append_columns) < 0) {
                fprintf(stderr, "Failed to append column list\n");
                goto cleanup;
            }
        }
    }
    
    // Set configuration via skeleton rodata before loading
    task_skel->rodata->xcap_show_all = show_all;
    task_skel->rodata->xcap_daemon_ports = daemon_ports;
    task_skel->rodata->xcap_filter_tgid = filter_tgid;
    task_skel->rodata->xcap_dump_kernel_stack_traces = g_ctx.dump_kernel_stack_traces;
    task_skel->rodata->xcap_dump_user_stack_traces = g_ctx.dump_user_stack_traces;
    task_skel->rodata->xcap_xcapture_pid = getpid();
    task_skel->rodata->xcap_dist_trace_http = dist_trace_http;
    task_skel->rodata->xcap_dist_trace_https = dist_trace_https;
    task_skel->rodata->xcap_dist_trace_grpc = dist_trace_grpc;
    task_skel->rodata->xcap_capture_cmdline = (!g_ctx.output_csv && column_is_active(COL_CMDLINE));
    
    // Load the BPF program with the configuration
    err = task_bpf__load(task_skel);
    if (err) { 
        fprintf(stderr, "Failed to load BPF skeleton: task\n"); 
        goto cleanup; 
    }

    err = pin_task_maps(task_skel, bpf_pin_path);
    if (err) {
        fprintf(stderr, "Failed to pin task maps under %s (err=%d)\n", bpf_pin_path, err);
        goto cleanup;
    }
    get_tasks_prog = task_skel->progs.get_tasks;
    completion_fd = bpf_map__fd(task_skel->maps.completion_events);
    task_samples_fd = bpf_map__fd(task_skel->maps.task_samples);
    stack_traces_fd = bpf_map__fd(task_skel->maps.stack_traces);

    bool iter_attached = false;
    // Attach task iterator with kernel-level TGID filtering when requested
    if (filter_tgid > 0) {
#ifdef HAVE_BPF_ITER_TASK_LINK_INFO
        // Use kernel-level task iterator filtering
        DECLARE_LIBBPF_OPTS(bpf_iter_attach_opts, iter_opts);
        union bpf_iter_link_info linfo;
        memset(&linfo, 0, sizeof(linfo));

        // Set up filtering by TGID (pid field filters by thread group)
        linfo.task.tid = 0;
        linfo.task.pid = filter_tgid;

        iter_opts.link_info = &linfo;
        iter_opts.link_info_len = sizeof(linfo);

        if (!g_ctx.output_csv || g_ctx.output_verbose) {
            printf("Using kernel-level task filtering for TGID %d\n", filter_tgid);
        }

        // Manually attach the task iterator with filtering options
        task_iter_link = bpf_program__attach_iter(get_tasks_prog, &iter_opts);
        if (!task_iter_link) {
            err = -errno;
            fprintf(stderr, "Failed to attach task iterator with TGID filter: %s (errno=%d)\n",
                    strerror(errno), errno);
            goto cleanup;
        }
        iter_attached = true;
#else
        if (!g_ctx.output_csv || g_ctx.output_verbose) {
            printf("Kernel headers lack task-iterator filtering; falling back to userspace TGID filter\n");
        }
#endif
    }

    if (!iter_attached) {
        // Standard attachment without filtering (or fallback when unavailable)
        err = task_bpf__attach(task_skel);
        if (err) {
            fprintf(stderr, "Failed to attach BPF skeleton: task\n");
            goto cleanup;
        }
    }

#ifdef USE_BLAZESYM
    /* Initialize BlazeSym symbolizer if requested */
    if ((g_ctx.dump_kernel_stack_traces || g_ctx.dump_user_stack_traces) && symbolize_stacks) {
        blaze_symbolizer_opts opts = {
            .type_size = sizeof(opts),
            .debug_dirs = NULL,       // Use default debug directories
            .debug_dirs_len = 0,
            .auto_reload = true,      // Reload changed binaries
            .code_info = true,        // Get source file/line info
            .inlined_fns = true,      // Show inlined functions
            .demangle = true,         // Demangle C++/Rust symbols
        };
        
        g_symbolizer = blaze_symbolizer_new_opts(&opts);
        if (!g_symbolizer) {
            fprintf(stderr, "Warning: Failed to initialize BlazeSym symbolizer: %s\n", 
                    blaze_err_str(blaze_err_last()));
            fprintf(stderr, "         Stack traces will show raw addresses only\n");
            symbolize_stacks = false;
        }
    }
#endif

    /* Only load active tracking probes if requested */
    if (!passive_only) {
        /* Only set up active tracking ring buffer if needed */
        tracking_rb = ring_buffer__new(completion_fd, handle_tracking_event, &g_ctx, NULL);
        if (!tracking_rb) {
            fprintf(stderr, "Failed to create tracking events ring buffer\n");
            goto cleanup;
        }

        if (track_syscalls) {
            syscall_skel = syscall_bpf__open();
            if (!syscall_skel) {
                fprintf(stderr, "Failed to open BPF skeleton: syscall\n");
                goto cleanup;
            }

            err = reuse_syscall_maps(syscall_skel, task_skel);
            if (err) {
                fprintf(stderr, "Failed to share maps with syscall skeleton (err=%d)\n", err);
                goto cleanup;
            }

            syscall_skel->rodata->xcap_dist_trace_http = dist_trace_http;
            syscall_skel->rodata->xcap_dist_trace_https = dist_trace_https;
            syscall_skel->rodata->xcap_dist_trace_grpc = dist_trace_grpc;
            syscall_skel->rodata->xcap_capture_rw_payloads = (track_syscalls && g_ctx.payload_trace_enabled);

            err = syscall_bpf__load(syscall_skel);
            if (err) {
                fprintf(stderr, "Failed to load BPF skeleton: syscall\n");
                goto cleanup;
            }

            err = syscall_bpf__attach(syscall_skel);
            if (err) {
                fprintf(stderr, "Failed to attach BPF skeleton: syscall\n");
                goto cleanup;
            }
        }

        // Only load and attach iorq tracking if explicitly requested
        if (track_iorq) {
            iorq_skel = iorq_bpf__open();
            if (!iorq_skel) { fprintf(stderr, "Failed to open BPF skeleton: iorq\n"); goto cleanup; }

            err = reuse_iorq_maps(iorq_skel, task_skel);
            if (err) { fprintf(stderr, "Failed to share maps with iorq skeleton (err=%d)\n", err); goto cleanup; }

            iorq_skel->rodata->xcap_dist_trace_http = dist_trace_http;
            iorq_skel->rodata->xcap_dist_trace_https = dist_trace_https;
            iorq_skel->rodata->xcap_dist_trace_grpc = dist_trace_grpc;

            err = iorq_bpf__load(iorq_skel);
            if (err) { fprintf(stderr, "Failed to load BPF skeleton: iorq\n"); goto cleanup; }
            if (iorq_bpf__attach(iorq_skel)) { fprintf(stderr, "Failed to attach BPF skeleton: iorq\n"); goto cleanup; }
        }
    }

    /* Always set up the passive task sampler ring buffer */
    task_rb = ring_buffer__new(task_samples_fd, handle_task_event, &g_ctx, NULL);
    if (!task_rb) {
        fprintf(stderr, "Failed to create task samples ring buffer\n");
        goto cleanup;
    }
    
    /* Set up stack traces ring buffer if stack collection is enabled */
    if (g_ctx.dump_kernel_stack_traces || g_ctx.dump_user_stack_traces) {
        stack_rb = ring_buffer__new(stack_traces_fd, handle_stack_event, &g_ctx, NULL);
        if (!stack_rb) {
            fprintf(stderr, "Failed to create stack traces ring buffer\n");
            goto cleanup;
        }
    }



    char timestamp[64];  // human readable timestamp string

    static struct timespec loop_start_ts; // for adjusting sleep duration between loop iterations
    static struct timespec loop_end_ts;
    static struct timespec iter_fd_start_ts;
    static struct timespec iter_fd_end_ts;
    static struct timespec iter_fd_inner_start_ts;
    static struct timespec iter_fd_inner_end_ts;

    long target_interval_ns = 1000000000L / sample_freq;
    int iteration_count = 0;
    
    // Calculate sample weight in microseconds based on sampling frequency
    g_ctx.sample_weight_us = 1000000L / sample_freq;

    // periodically sample and write task states to ringbuf
    while (!exiting) {
        clock_gettime(CLOCK_MONOTONIC, &loop_start_ts);
        clock_gettime(CLOCK_REALTIME, &g_ctx.tcorr.wall_time);
        clock_gettime(CLOCK_MONOTONIC, &g_ctx.tcorr.mono_time);

        struct tm *tm = localtime(&g_ctx.tcorr.wall_time.tv_sec);
        strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%S", tm);
        snprintf(timestamp + 19, sizeof(timestamp) - 19, ".%06ld", g_ctx.tcorr.wall_time.tv_nsec / 1000);

        // Reset unique stacks for new iteration
        reset_unique_stacks();
        
        // Print headers for every sampling iteration in plain text mode
        if (!g_ctx.output_csv) {
            print_column_headers();
        }

        // Trigger the task iterator to collect data - it will send results to the ring buffer
        clock_gettime(CLOCK_MONOTONIC, &iter_fd_start_ts);
        int iter_link_fd = task_iter_link ? bpf_link__fd(task_iter_link) :
            bpf_link__fd(task_skel->links.get_tasks);
        iter_fd = bpf_iter_create(iter_link_fd);
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

        // Poll stack traces ring buffer if stack collection is enabled
        if (stack_rb) {
            err = ring_buffer__poll(stack_rb, 0 /* timeout, ms */);
            if (err < 0) {
                fprintf(stderr, "Error polling stack ring buffer: %d\n", err);
                goto cleanup;
            }
        }

        // Only poll event completion tracking ring buffer if is set up and used
        if (!passive_only && tracking_rb) {

            if (!g_ctx.output_csv || g_ctx.output_verbose) {
                printf("\n");
            }

            err = ring_buffer__poll(tracking_rb, 0 /* timeout, ms */);
            if (err < 0) {
                fprintf(stderr, "Error polling tracking ring buffer: %d\n", err);
                goto cleanup;
            }
        }

        // Print unique stacks if -s is used
        if (!g_ctx.output_csv && g_ctx.print_stack_traces) {
            print_unique_stacks();
        }
        
        if (!g_ctx.output_csv || g_ctx.output_verbose) {
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
            if (!g_ctx.output_csv || g_ctx.output_verbose) {
                printf("Sampling took:   %'ld us (iter_fd: %'ld us, inner: %'ld us), sleeping for %'ld us\n",
                        sampling_ns / 1000L, iter_fd_ns / 1000L, iter_fd_inner_ns / 1000L, sleep_ns / 1000L);
                printf("\n");
            }
            fflush(NULL);
            usleep(sleep_ns / 1000); // Convert ns to microseconds for usleep
        } else {
            if (!g_ctx.output_csv || g_ctx.output_verbose) {
                printf("Warning: Sampling took longer than display interval (%ld.%06ld s)\n",
                    sampling_time.tv_sec, sampling_time.tv_nsec / 1000);
                printf("\n");
                fflush(NULL);
            }
        }

        // Check if we've reached the maximum number of iterations
        if (max_iterations > 0) {
            iteration_count++;
            if (iteration_count >= max_iterations) {
                if (!g_ctx.output_csv || g_ctx.output_verbose) {
                    printf("Reached maximum iterations (%d), exiting...\n", max_iterations);
                }
                break;
            }
        }
    }

cleanup:
    // flush all open file streams and close fds
    fflush(NULL);
    if (is_fd_open(iter_fd)) close(iter_fd);
    if (g_ctx.output_csv) close_output_files(&g_ctx.files);
    
    // Clean up cgroup cache
    cgroup_cache_destroy();

    // Unpin maps before destroying skeletons
    if (task_skel) {
        unpin_map_if_needed(task_skel->maps.task_storage);
        unpin_map_if_needed(task_skel->maps.completion_events);
        unpin_map_if_needed(task_skel->maps.task_samples);
        unpin_map_if_needed(task_skel->maps.emitted_stacks);
        unpin_map_if_needed(task_skel->maps.stack_traces);
    }

    // cleanup BUG: if iorq_tracking prog failed to load due to verifier
    // its map lingers around (sudo rm /sys/fs/bpf/iorq_tracking)
    if (iorq_skel)
        unpin_map_if_needed(iorq_skel->maps.iorq_tracking);
    
    // Destroy skeletons
    if (syscall_skel) syscall_bpf__destroy(syscall_skel);
    if (iorq_skel) iorq_bpf__destroy(iorq_skel);
    if (task_skel) task_bpf__destroy(task_skel);

    if (tracking_rb)  ring_buffer__free(tracking_rb);
    if (task_rb)      ring_buffer__free(task_rb);
    if (stack_rb)     ring_buffer__free(stack_rb);

#ifdef USE_BLAZESYM
    if (g_symbolizer) {
        blaze_symbolizer_free(g_symbolizer);
        g_symbolizer = NULL;
    }
#endif

    free(g_ctx.custom_columns);
    free(g_ctx.append_columns);

    return err < 0 ? -err : 0;
}
