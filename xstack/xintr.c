// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
// xintr - CPU interrupt stack sampler by Tanel Poder [0x.tools]
//
// This is currently an experimental prototype working only on 6.2+ or RHEL 5.14+ on x86_64
// Test this out on Ubuntu or Fedora compiled kernels, as RHEL, OEL, Debian have not enabled
// CONFIG_FRAME_POINTER=y for their kernel builds.
//
// I plan to experiment with stack forensics & ORC unwinding in userspace,
// to support such platforms.

// If you wonder what the FRED check in softirq processing is about, read this:
//   https://tanelpoder.com/posts/ebpf-pt-regs-error-on-linux-blame-fred/

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

#include "xintr.h"
#include "xintr.skel.h"

#ifdef USE_BLAZESYM
#include "blazesym.h"
#endif

#define XINTR_VERSION "3.0.0"
#define XINTR_AUTHOR "Tanel Poder [0x.tools]"

static volatile bool running = true;
static int sample_freq = 1;            // default 1 Hz
static bool quiet = false;             // do not print header
static bool debug_mode = false;
static bool show_all = false;          // show all CPUs even if they are not in interrupt
static bool show_every = false;        // show every symbol, including srso_return_thunk
static bool dump_stacks = false;       // dump raw stack memory to files
static bool everything_mode = false;   // -E flag: show all kernel addresses without frame validation
static bool include_softirq = false;   // -S flag: attempt to include softirq stack frames

// Two symbols for handling softirq processing, depending on if FRED is enabled on x86_64
static __u64 do_softirq_start = 0;     // traditional IDT
static __u64 do_softirq_end = 0;
static __u64 handle_softirq_start = 0; // CONFIG_FRED_ENABLED=y
static __u64 handle_softirq_end = 0;


// Look up handle_softirqs address (ignoring handle_softirqs.cold, etc variations for now)
// If a symbol is found (found=true), loop one more time to find next symbol's start addr
static bool lookup_symbol_range(const char *name, __u64 *start, __u64 *end)
{
    FILE *fp = fopen("/proc/kallsyms", "r");
    if (!fp)
        return false;

    char line[512];
    bool found = false;

    while (fgets(line, sizeof(line), fp)) {
        unsigned long long addr;
        char type;
        char sym[256];

        if (sscanf(line, "%llx %c %255s", &addr, &type, sym) != 3) // 3 fields successfully read
            continue;

        if (found) {
            *end = addr;
            fclose(fp);
            return true;
        }

        if (strcmp(sym, name) == 0) {
            *start = addr;
            found = true;
        }
    }

    fclose(fp);

    if (found) {
        *end = *start + 0x2000; // fallback range guess
        return true;
    }
    return false;
}

#ifdef USE_BLAZESYM
static blaze_symbolizer *symbolizer = NULL;
#endif

// Exit signal handler
static void sig_handler(int sig)
{
    running = false;
}

static inline bool is_kernel_text_addr(__u64 addr)
{
    // On aarch64 the ksym range will start at 0xFFFF800080000000

    return addr >= 0xFFFFFFFF80000000ULL;
}

static bool read_stack_value(const struct irq_stack_event *e, __u64 addr,
                             __u64 *value)
{
    __u64 stack_highest = e->hardirq_stack_ptr + 8;
    __u64 stack_lowest = stack_highest - IRQ_STACK_SIZE;

    if (addr < stack_lowest || addr + sizeof(__u64) > stack_highest)
        return false;

    size_t offset = addr - stack_lowest;
    memcpy(value, e->raw_stack + offset, sizeof(__u64));
    return true;
}

// Walk the stack memory dump in reverse, from its bottom (execution start) and
// construct a plausible call trace by using heuristics and valid caller checks
static int collect_stack_entries(const struct irq_stack_event *e, __u64 *out,
                                 int max_entries)
{
    if (!e->hardirq_in_use || !e->dump_enabled)
        return 0;

    __u64 stack_highest = e->hardirq_stack_ptr + 8;
    __u64 stack_lowest = stack_highest - IRQ_STACK_SIZE;
    int slots = IRQ_STACK_SIZE / sizeof(__u64);
    int found = 0;
    bool chain_started = false;
    int softirq_restarts = 0;

    for (int slot = slots - 1; slot >= 0 && found < max_entries; slot--) {
        __u64 rip;
        memcpy(&rip, e->raw_stack + (slot * sizeof(__u64)), sizeof(rip));

        if (!is_kernel_text_addr(rip))
            continue;

        bool accept = true;

        if (!everything_mode) {
            __u64 offset = rip & 0xFFFULL;
            bool offset_ok = (offset < 0x1000);
            bool entry_point = (offset < 0x200);
            bool caller_ok = false;

            if (slot > 0) {
                __u64 saved_rbp;
                memcpy(&saved_rbp, e->raw_stack + ((slot - 1) * sizeof(__u64)),
                       sizeof(saved_rbp));

                bool saved_rbp_valid = ((saved_rbp % sizeof(__u64)) == 0 &&
                                        saved_rbp >= stack_lowest &&
                                        saved_rbp + sizeof(__u64) <= stack_highest);

                if (saved_rbp_valid) {
                    __u64 caller_rip;
                    if (read_stack_value(e, saved_rbp + sizeof(__u64), &caller_rip) &&
                        is_kernel_text_addr(caller_rip)) {
                        caller_ok = true;
                    }
                }
            }

            if (!chain_started)
                accept = offset_ok && (entry_point || caller_ok);
            else
                accept = offset_ok && caller_ok;
        }

        if (accept) {
            if (found == 0 || out[found - 1] != rip)
                out[found++] = rip;
            chain_started = true;
        } else if (!everything_mode) {
            bool can_restart = false;

            // Allow "broken" caller validation in hardirq -> softirq handling transition
            if (chain_started && include_softirq && softirq_restarts < 2 && found > 0) {
                __u64 last_rip = out[found - 1];
            
                bool in_do_softirq = (do_softirq_start && do_softirq_end &&
                                      last_rip >= do_softirq_start && last_rip < do_softirq_end);
            
                bool in_handle_softirq = (handle_softirq_start && handle_softirq_end &&
                                          last_rip >= handle_softirq_start && last_rip < handle_softirq_end);
            
                if (in_do_softirq || in_handle_softirq)
                    can_restart = true;
            }

            if (can_restart) {
                chain_started = false;
                softirq_restarts++;
                continue;
            }

            if (chain_started)
                break;
        }
    }

    return found;
}

// Symbolize stack addresses
static char *symbolize_stack(__u64 *addrs, int count)
{
#ifdef USE_BLAZESYM
    if (!symbolizer || count <= 0)
        return strdup("");

    static char symbuf[8192];
    symbuf[0] = '\0';

    struct blaze_symbolize_src_kernel src = {
        .type_size = sizeof(src),
    };

    const struct blaze_syms *syms = blaze_symbolize_kernel_abs_addrs(
        symbolizer, &src, (const uintptr_t *)addrs, count);

    if (!syms || syms->cnt == 0) {
        if (syms) blaze_syms_free(syms);
        // Return hex addresses if symbolization did not work
        for (int i = 0; i < count; i++) {
            if (i > 0) strcat(symbuf, ";");
            char addr[32];
            snprintf(addr, sizeof(addr), "0x%llx", addrs[i]);
            strcat(symbuf, addr);
        }
        return strdup(symbuf);
    }

    char *ptr = symbuf;
    size_t remaining = sizeof(symbuf) - 1;
    bool first = true;

    for (size_t i = 0; i < syms->cnt && i < count; i++) {
        const struct blaze_sym *sym = &syms->syms[i];

        // Skip srso_return_thunk mitigation frames unless -e flag is set
        if (!show_every && sym->name && strncmp(sym->name, "srso_return_thunk", 17) == 0) {
            continue;
        }

        if (!first) {
            if (remaining > 1) {
                *ptr++ = ';';
                remaining--;
            }
        }
        first = false;

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

    *ptr = '\0';
    blaze_syms_free(syms);
    return strdup(symbuf);
#else
    // No blazesym return hex addresses
    static char addrbuf[8192];
    addrbuf[0] = '\0';

    for (int i = 0; i < count; i++) {
        if (i > 0) strcat(addrbuf, ";");
        char frame[32];
        snprintf(frame, sizeof(frame), "0x%llx", addrs[i]);
        strcat(addrbuf, frame);
    }
    return strdup(addrbuf);
#endif
}

// Ring buffer callback
static int handle_event(void *ctx, void *data, size_t data_sz)
{
    struct irq_stack_event *e = data;

    // Skip CPUs without active interrupt stack unless -a flag is set
    if (!show_all && !e->hardirq_in_use) {
        return 0;
    }

    // If dump mode is enabled and interrupt is in use, dump the raw stack
    if (dump_stacks && e->hardirq_in_use && e->dump_enabled) {
        char filename[32];
        snprintf(filename, sizeof(filename), "%llu.dmp", e->timestamp);

        FILE *fp = fopen(filename, "wb");
        if (fp) {
            // Write the captured IRQ stack snapshot
            fwrite(e->raw_stack, 1, IRQ_STACK_SIZE, fp);
            fclose(fp);
        }
    }

    __u64 stack_entries[MAX_STACK_DEPTH];
    int stack_cnt = collect_stack_entries(e, stack_entries, MAX_STACK_DEPTH);

    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    char timestamp[64];
    strftime(timestamp, sizeof(timestamp), "%Y-%m-%d %H:%M:%S", localtime(&ts.tv_sec));
    snprintf(timestamp + strlen(timestamp), sizeof(timestamp) - strlen(timestamp),
             ".%06ld", ts.tv_nsec / 1000);

    char *syms = symbolize_stack(stack_entries, stack_cnt);

    if (debug_mode) {
        printf("%s|%u|%llu|%d|0x%llx|0x%llx|DEBUG[0x%llx,0x%llx,0x%llx,0x%llx]|%s\n",
               timestamp,
               e->cpu,
               (unsigned long long)e->call_depth,
               e->hardirq_in_use,
               (unsigned long long)e->hardirq_stack_ptr,
               (unsigned long long)e->top_of_stack,
               (unsigned long long)e->debug_values[0],
               (unsigned long long)e->debug_values[1],
               (unsigned long long)e->debug_values[2],
               (unsigned long long)e->debug_values[3],
               syms ? syms : ""
            );
    } else {
        printf("%s|%u|%s\n",
               timestamp,
               e->cpu,
               syms ? syms : ""
            );
    }
    fflush(stdout);

    if (syms) free(syms);

    return 0;
}

static struct argp_option options[] = {
    {"freq", 'F', "HZ", 0, "Sampling frequency in Hz (0=max speed, default: 1)", 0},
    {"iterations", 'i', "NUM", 0, "Number of sampling iterations (default: infinite)", 0},
    {"quiet", 'q', 0, 0, "Suppress header output", 0},
    {"all", 'a', 0, 0, "Show all CPUs including those without active interrupts", 0},
    {"debug", 'd', 0, 0, "Show debug information", 0},
    {"every", 'e', 0, 0, "Show every symbol including mitigation frames (srso_return_thunk)", 0},
    {"dump", 'D', 0, 0, "Dump raw 16KB interrupt stack memory to timestamped .dmp files", 0},
    {"everything", 'E', 0, 0, "Show all kernel addresses without stack frame validation", 0},
    {"softirq", 'S', 0, 0, "Include softirq frames using heuristic stack validation", 0},
    {0}
};

struct arguments {
    int freq;
    int iterations;
    bool quiet;
    bool show_all;
    bool debug;
    bool show_every;
    bool dump;
    bool everything;
    bool softirq;
};

static error_t parse_opt(int key, char *arg, struct argp_state *state)
{
    struct arguments *args = state->input;

    switch (key) {
    case 'F':
        args->freq = atoi(arg);
        if (args->freq < 0 || args->freq > 1000000) {
            fprintf(stderr, "Invalid frequency: %s (must be 0-1000000)\n", arg);
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
    case 'a':
        args->show_all = true;
        break;
    case 'd':
        args->debug = true;
        break;
    case 'e':
        args->show_every = true;
        break;
    case 'D':
        args->dump = true;
        break;
    case 'E':
        args->everything = true;
        break;
    case 'S':
        args->softirq = true;
        break;
    default:
        return ARGP_ERR_UNKNOWN;
    }
    return 0;
}

const char *argp_program_version = "xintr v" XINTR_VERSION " by " XINTR_AUTHOR;
const char *argp_program_bug_address = "<https://github.com/tanelpoder/0xtools>";

static struct argp argp = {
    .options = options,
    .parser = parse_opt,
    .doc = "xintr v" XINTR_VERSION " by " XINTR_AUTHOR "\n"
           "Sample interrupt stacks from all CPUs\n\n"
           "USAGE: xintr [-F HZ] [-i NUM]\n\n"
           "EXAMPLES:\n"
           "  xintr           # Sample all CPUs at 1 Hz\n"
           "  xintr -F 10     # Sample at 10 Hz\n"
           "  xintr -F 0      # Sample at maximum speed\n"
           "  xintr -i 100    # Sample for 100 iterations\n",
};

int main(int argc, char **argv)
{
    struct arguments args = {
        .freq = 1,
        .iterations = -1,  // infinite by default
        .quiet = false,
        .show_all = false,
        .debug = false,
        .show_every = false,
        .dump = false,
        .everything = false,
        .softirq = false,
    };

    if (argp_parse(&argp, argc, argv, 0, 0, &args)) {
        return 1;
    }

    sample_freq = args.freq;
    quiet = args.quiet;
    debug_mode = args.debug;
    show_all = args.show_all;
    show_every = args.show_every;
    dump_stacks = args.dump;
    everything_mode = args.everything;
    include_softirq = args.softirq;

    if (include_softirq) {
        bool found = false;

        // Currently scanning through /proc/kallsyms twice on xintr startup, for code simplicity    
        if (lookup_symbol_range("__do_softirq", &do_softirq_start, &do_softirq_end))
            found = true;
        else
            fprintf(stderr, "Warning: failed to locate __do_softirq in /proc/kallsyms\n");
    
        if (lookup_symbol_range("handle_softirqs", &handle_softirq_start, &handle_softirq_end))
            found = true;
        else
            fprintf(stderr, "Warning: failed to locate handle_softirqs in /proc/kallsyms\n");
    
        if (!found) {
            fprintf(stderr, "softirq heuristic disabled\n");
            include_softirq = false;
        }
    }

    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);

    struct rlimit rlim = {
        .rlim_cur = 32 * 1024 * 1024, // 32MB
        .rlim_max = 32 * 1024 * 1024,
    };
    if (setrlimit(RLIMIT_MEMLOCK, &rlim)) {
        fprintf(stderr, "Failed to increase RLIMIT_MEMLOCK\n");
    }

    // Load and attach BPF program
    struct xintr_bpf *skel = xintr_bpf__open();
    if (!skel) {
        fprintf(stderr, "Failed to open BPF skeleton\n");
        return 1;
    }


    if (xintr_bpf__load(skel)) {
        fprintf(stderr, "Failed to load BPF skeleton\n");
        xintr_bpf__destroy(skel);
        return 1;
    }

    struct bpf_link *link = bpf_program__attach_iter(skel->progs.sample_cpu_irq_stacks, NULL);
    if (!link) {
        fprintf(stderr, "Failed to attach iterator\n");
        xintr_bpf__destroy(skel);
        return 1;
    }

    // Store the link FD, we'll (re)create iterator FDs from this
    int link_fd = bpf_link__fd(link);

    struct ring_buffer *rb = ring_buffer__new(bpf_map__fd(skel->maps.events),
                                              handle_event, NULL, NULL);
    if (!rb) {
        fprintf(stderr, "Failed to create ring buffer\n");
        xintr_bpf__destroy(skel);
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
        if (debug_mode) {
            printf("timestamp|cpu|call_depth|in_use|hardirq_stack_ptr|top_of_stack|debug|stack\n");
        } else {
            printf("timestamp|cpu|stack\n");
        }
        fflush(stdout);
    }

    long interval_ns = (sample_freq > 0) ? (1000000000L / sample_freq) : 0;

    // Main sampling loop
    int iteration = 0;
    static char buf[1];

    while (running) {
        if (args.iterations > 0 && iteration >= args.iterations) {
            break;
        }

        struct timespec start_time;
        clock_gettime(CLOCK_MONOTONIC, &start_time);

        // Create new iterator instance
        int iter_fd = bpf_iter_create(link_fd);
        if (iter_fd < 0) {
            fprintf(stderr, "Failed to create iterator FD: %s\n", strerror(errno));
            break;
        }

        // Trigger the iterator by reading from it, when this read call completes
        // the iterator is done with its processing and ringbuf writing in this cycle
        int ret = read(iter_fd, buf, sizeof(buf));
        if (ret < 0 && errno != EAGAIN) {
            fprintf(stderr, "read(iter_fd=%d) error: %s\n", iter_fd, strerror(errno));
        }

        close(iter_fd);

        while (ring_buffer__poll(rb, 0) > 0) {
            // Keep processing until no more events in ringbuf
        }

        if (sample_freq > 0) {
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
    xintr_bpf__destroy(skel);

    return 0;
}
