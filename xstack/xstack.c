// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
// Copyright 2024-2038 Tanel Poder [0x.tools]

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <errno.h>
#include <unistd.h>
#include <time.h>
#include <argp.h>
#include <bpf/bpf.h>
#include <bpf/libbpf.h>
#include <sys/resource.h>
#include <fcntl.h>

#include "xstack.h"
#include "xstack.skel.h"

#define XSTACK_VERSION "3.0.0"
#define XSTACK_AUTHOR "Tanel Poder [0x.tools]"

#ifdef USE_BLAZESYM
#include "blazesym.h"
#endif

static volatile bool running = true;
static int sample_freq = 1;  // Default 1 Hz
static bool quiet = false;  // Whether to suppress header
static bool reverse_stack = false;  // Whether to reverse stack output
static pid_t my_pid = 0;  // Our own PID to filter out

#ifdef USE_BLAZESYM
static blaze_symbolizer *symbolizer = NULL;
#endif

// Signal handler
static void sig_handler(int sig)
{
    running = false;
}

// Convert task state to string
static const char *state_to_str(__u32 state)
{

    static char state_str[64];  // Buffer for dynamic state string

    if (state == TASK_RUNNING)
        return "RUNNING";
    else if (state & TASK_INTERRUPTIBLE)
        return "SLEEP";
    else if (state & TASK_UNINTERRUPTIBLE) // the calling function filters out IDLE kernel threads
        return "DISK";                     // that have TASK_UNINTERRUPTIBLE | TASK_NOLOAD flags set
    else if (state & TASK_IDLE)            // kernel threads can be IDLE (but xstack filters them out)
        return "IDLE";
    else if (state & TASK_WAKING)
        return "WAKING";
    else if (state & TASK_STOPPED)
        return "STOPPED";
    else if (state & TASK_TRACED)
        return "TRACED";
    else if (state & EXIT_ZOMBIE)
        return "ZOMBIE";
    else if (state & EXIT_DEAD)
        return "DEAD";
    else if (state & TASK_PARKED)
        return "PARKED";
    else {
        snprintf(state_str, sizeof(state_str), "0x%x", state);
        return state_str;
    }
}

// Symbolize a single stack
static char *symbolize_stack(__u64 *addrs, int count, pid_t pid, bool is_kernel)
{
#ifdef USE_BLAZESYM
    if (!symbolizer || count <= 0)
        return strdup(is_kernel ? "" : "[no_ustack]");

    static char symbuf[65536];  // Large buffer for symbols
    symbuf[0] = '\0';

    const struct blaze_syms *syms = NULL;

    if (is_kernel) {
        struct blaze_symbolize_src_kernel src = {
            .type_size = sizeof(src),
        };
        syms = blaze_symbolize_kernel_abs_addrs(symbolizer, &src,
                                                (const uintptr_t *)addrs, count);
    } else {
        struct blaze_symbolize_src_process src = {
            .type_size = sizeof(src),
            .pid = pid,
        };
        syms = blaze_symbolize_process_abs_addrs(symbolizer, &src,
                                                 (const uintptr_t *)addrs, count);
    }

    if (!syms || syms->cnt == 0) {
        if (syms) blaze_syms_free(syms);
        return strdup(is_kernel ? "[no_ksymbols]" : "[no_usymbols]");
    }

    char *ptr = symbuf;
    size_t remaining = sizeof(symbuf) - 1;

    // Iterate in reverse order if requested
    if (reverse_stack) {
        for (int i = count - 1; i >= 0; i--) {
            if (i < count - 1) {
                if (remaining > 1) {
                    *ptr++ = ';';
                    remaining--;
                }
            }

            if (i < syms->cnt) {
                const struct blaze_sym *sym = &syms->syms[i];
                if (sym->name && sym->name[0]) {
                    int written = snprintf(ptr, remaining, "%s+0x%lx",
                                         sym->name, sym->offset);
                    if (written > 0 && written < remaining) {
                        ptr += written;
                        remaining -= written;
                    }
                } else {
                    int written = snprintf(ptr, remaining, "0x%llx", addrs[i]);
                    if (written > 0 && written < remaining) {
                        ptr += written;
                        remaining -= written;
                    }
                }
            } else {
                int written = snprintf(ptr, remaining, "0x%llx", addrs[i]);
                if (written > 0 && written < remaining) {
                    ptr += written;
                    remaining -= written;
                }
            }
        }
    } else {
        for (size_t i = 0; i < syms->cnt && i < count; i++) {
            if (i > 0) {
                if (remaining > 1) {
                    *ptr++ = ';';
                    remaining--;
                }
            }

            const struct blaze_sym *sym = &syms->syms[i];
            if (sym->name && sym->name[0]) {
                int written = snprintf(ptr, remaining, "%s+0x%lx",
                                     sym->name, sym->offset);
                if (written > 0 && written < remaining) {
                    ptr += written;
                    remaining -= written;
                }
            } else {
                int written = snprintf(ptr, remaining, "0x%llx", addrs[i]);
                if (written > 0 && written < remaining) {
                    ptr += written;
                    remaining -= written;
                }
            }
        }
    }

    *ptr = '\0';
    blaze_syms_free(syms);
    return strdup(symbuf);
#else
    // No blazesym - just return addresses as hex
    static char addrbuf[8192];
    addrbuf[0] = '\0';

    if (count == 0)
        return strdup(is_kernel ? "" : "[no_ustack]");

    if (reverse_stack) {
        for (int i = count - 1; i >= 0; i--) {
            if (i < count - 1)
                strcat(addrbuf, ";");
            char frame[32];
            snprintf(frame, sizeof(frame), "0x%llx", addrs[i]);
            strcat(addrbuf, frame);
        }
    } else {
        for (int i = 0; i < count; i++) {
            if (i > 0)
                strcat(addrbuf, ";");
            char frame[32];
            snprintf(frame, sizeof(frame), "0x%llx", addrs[i]);
            strcat(addrbuf, frame);
        }
    }
    return strdup(addrbuf);
#endif
}

// Ring buffer callback
static int handle_event(void *ctx, void *data, size_t data_sz)
{
    struct stack_event *e = data;

    if (e->pid == my_pid)
        return 0;

    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    char timestamp[64];
    strftime(timestamp, sizeof(timestamp), "%Y-%m-%d %H:%M:%S", localtime(&ts.tv_sec));
    snprintf(timestamp + strlen(timestamp), sizeof(timestamp) - strlen(timestamp),
             ".%06ld", ts.tv_nsec / 1000);

    char *ksyms = symbolize_stack(e->kstack, e->kstack_sz, e->pid, true);
    char *usyms = symbolize_stack(e->ustack, e->ustack_sz, e->pid, false);

    // Print CSV values: timestamp,tid,tgid,comm,state,ustack,kstack
    printf("%s|%u|%u|%s|%s|%s|%s\n",
           timestamp,
           e->pid,
           e->tgid,
           e->comm,
           state_to_str(e->state),
           usyms ? usyms : "[no_ustack]",
           ksyms ? ksyms : "[no_kstack]"
        );

    if (ksyms) free(ksyms);
    if (usyms) free(usyms);

    return 0;
}

// Command-line arguments
static struct argp_option options[] = {
    {"all", 'a', 0, 0, "Sample all tasks/threads", 0},
    {"pid", 'p', "PID", 0, "Filter by process ID (TGID)", 0},
    {"tid", 't', "TID", 0, "Filter by thread ID (PID)", 0},
    {"freq", 'F', "HZ", 0, "Sampling frequency in Hz (default: 1)", 0},
    {"iterations", 'i', "NUM", 0, "Number of sampling iterations (default: infinite)", 0},
    {"quiet", 'q', 0, 0, "Suppress CSV header output", 0},
    {"reverse-stack", 'r', 0, 0, "Reverse stack trace order (innermost first)", 0},
    {0}
};

struct arguments {
    int filter_mode;  // 0=all, 1=by_tgid, 2=by_pid
    __u32 target_value;
    int freq;
    int iterations;  // -1 for infinite
    bool quiet;
    bool reverse_stack;
};

static error_t parse_opt(int key, char *arg, struct argp_state *state)
{
    struct arguments *args = state->input;

    switch (key) {
    case 'a':
        args->filter_mode = 0;
        break;
    case 'p':
        args->filter_mode = 1;
        args->target_value = atoi(arg);
        break;
    case 't':
        args->filter_mode = 2;
        args->target_value = atoi(arg);
        break;
    case 'F':
        args->freq = atoi(arg);
        if (args->freq <= 0 || args->freq > 1000) {
            fprintf(stderr, "Invalid frequency: %s (must be 1-1000)\n", arg);
            return ARGP_ERR_UNKNOWN;
        }
        break;
    case 'i':
        args->iterations = atoi(arg);
        if (args->iterations <= 0) {
            fprintf(stderr, "Invalid iterations: %s (must be > 0)\n", arg);
            return ARGP_ERR_UNKNOWN;
        }
        break;
    case 'q':
        args->quiet = true;
        break;
    case 'r':
        args->reverse_stack = true;
        break;
    case ARGP_KEY_END:
        if (args->filter_mode == -1) {
            argp_usage(state);
            return ARGP_ERR_UNKNOWN;
        }
        break;
    default:
        return ARGP_ERR_UNKNOWN;
    }
    return 0;
}

const char *argp_program_version = "xstack v" XSTACK_VERSION " by " XSTACK_AUTHOR;
const char *argp_program_bug_address = "<https://github.com/tanelpoder/0xtools>";

static struct argp argp = {
    .options = options,
    .parser = parse_opt,
    .doc = "xstack v" XSTACK_VERSION " by " XSTACK_AUTHOR "\n"
           "Completely passive stack profiling without injecting any tracepoints\n\n"
           "USAGE: xstack -a | -p PID | -t TID [-F HZ] [-i NUM]\n\n"
           "EXAMPLES:\n"
           "  xstack -a           # Sample all tasks continuously\n"
           "  xstack -p 1234      # Sample process 1234 and its threads\n"
           "  xstack -t 5678      # Sample only thread 5678\n"
           "  xstack -a -F 10     # Sample all tasks at 10 Hz\n"
           "  xstack -a -i 100    # Sample all tasks for 100 iterations\n"
           "  xstack -p $$ -F 5 -i 25  # Sample shell at 5 Hz for 5 seconds\n",
};

int main(int argc, char **argv)
{
    struct arguments args = {
        .filter_mode = -1,
        .target_value = 0,
        .freq = 1,
        .iterations = -1,  // infinite by default
        .quiet = false,
        .reverse_stack = false,
    };

    // Get our own PID to filter it out
    my_pid = getpid();

    if (argc == 1) {
        argp_help(&argp, stdout, ARGP_HELP_USAGE, argv[0]);
        return 0;
    }

    if (argp_parse(&argp, argc, argv, 0, 0, &args)) {
        return 1;
    }

    sample_freq = args.freq;
    quiet = args.quiet;
    reverse_stack = args.reverse_stack;

    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);

    // Bump RLIMIT_MEMLOCK for BPF
    struct rlimit rlim = {
        .rlim_cur = 512 * 1024 * 1024,  // 512 MB
        .rlim_max = 512 * 1024 * 1024,
    };
    if (setrlimit(RLIMIT_MEMLOCK, &rlim)) {
        fprintf(stderr, "Failed to increase RLIMIT_MEMLOCK\n");
    }

    // Load and attach BPF program
    struct xstack_bpf *skel = xstack_bpf__open();
    if (!skel) {
        fprintf(stderr, "Failed to open BPF skeleton\n");
        return 1;
    }

    if (xstack_bpf__load(skel)) {
        fprintf(stderr, "Failed to load BPF skeleton\n");
        xstack_bpf__destroy(skel);
        return 1;
    }

    // Set up configuration
    struct filter_config cfg = {
        .filter_mode = args.filter_mode,
        .target_tgid = (args.filter_mode == 1) ? args.target_value : 0,
        .target_pid = (args.filter_mode == 2) ? args.target_value : 0,
    };

    __u32 key = 0;
    if (bpf_map_update_elem(bpf_map__fd(skel->maps.config_map),
                            &key, &cfg, BPF_ANY)) {
        fprintf(stderr, "Failed to update config map\n");
        xstack_bpf__destroy(skel);
        return 1;
    }

    // Attach the iterator
    struct bpf_link *link = bpf_program__attach_iter(skel->progs.dump_task, NULL);
    if (!link) {
        fprintf(stderr, "Failed to attach iterator\n");
        xstack_bpf__destroy(skel);
        return 1;
    }

    // Store the link FD - we'll create iterator FDs from this
    int link_fd = bpf_link__fd(link);

    struct ring_buffer *rb = ring_buffer__new(bpf_map__fd(skel->maps.events),
                                              handle_event, NULL, NULL);
    if (!rb) {
        fprintf(stderr, "Failed to create ring buffer\n");
        bpf_link__destroy(link);
        xstack_bpf__destroy(skel);
        return 1;
    }

#ifdef USE_BLAZESYM
    blaze_symbolizer_opts opts = {
        .type_size = sizeof(opts),
        .debug_dirs = NULL,
        .debug_dirs_len = 0,
        .auto_reload = true,
        .code_info = false,
        .inlined_fns = false,
        .demangle = true,
    };

    symbolizer = blaze_symbolizer_new_opts(&opts);
    if (!symbolizer) {
        fprintf(stderr, "Warning: Failed to create symbolizer\n");
    }
#endif

    if (!quiet) {
        printf("timestamp|tid|tgid|comm|state|ustack|kstack\n");
        fflush(stdout);
    }

    long interval_ns = 1000000000L / sample_freq;

    // Main loop
    static char buf[1];
    int iteration = 0;
    while (running) {
        if (args.iterations > 0 && iteration >= args.iterations) {
            break;
        }

        struct timespec start_time;
        clock_gettime(CLOCK_MONOTONIC, &start_time);

        int iter_fd = bpf_iter_create(link_fd);
        if (iter_fd < 0) {
            fprintf(stderr, "Failed to create iterator FD: %s\n", strerror(errno));
            break;
        }

        int ret = read(iter_fd, buf, 1);

        if (ret)
            fprintf(stderr, "read(iter_fd=%d) error\n", iter_fd);

        while (ring_buffer__poll(rb, 0) > 0) {
            // Keep processing until no more events
        }

        close(iter_fd);

        // Calculate time spent and adjust sleep
        struct timespec end_time;
        clock_gettime(CLOCK_MONOTONIC, &end_time);

        long elapsed_ns = (end_time.tv_sec - start_time.tv_sec) * 1000000000L +
                         (end_time.tv_nsec - start_time.tv_nsec);

        long sleep_ns = interval_ns - elapsed_ns;
        if (sleep_ns > 0) {
            struct timespec sleep_time = {
                .tv_sec = sleep_ns / 1000000000L,
                .tv_nsec = sleep_ns % 1000000000L,
            };
            nanosleep(&sleep_time, NULL);
        }

        iteration++;
    }

    // Cleanup
#ifdef USE_BLAZESYM
    if (symbolizer)
        blaze_symbolizer_free(symbolizer);
#endif

    ring_buffer__free(rb);
    bpf_link__destroy(link);
    xstack_bpf__destroy(skel);

    return 0;
}
