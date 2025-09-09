// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024-2038 Tanel Poder [0x.tools]

#include <stdio.h>
#include <unistd.h>
#include <pwd.h>
#include <time.h>
#include <string.h>

#include <bpf/bpf.h>
#include <bpf/libbpf.h>

#include "xcapture.h"
#include "task_handler.h"
#include "xcapture_user.h"
#include "md5.h"
#include "columns.h"
#include "cgroup_cache.h"

#ifdef USE_BLAZESYM
#include "blazesym.h"
#endif

// Platform specific syscall numbers
#if defined(__TARGET_ARCH_arm64)
#include "syscall_aarch64.h"
#elif defined(__TARGET_ARCH_x86)
#include "syscall_x86_64.h"
#endif

// External variables from main.c
extern struct output_files files;
extern struct time_correlation tcorr;
extern pid_t mypid;
extern bool output_csv;
extern bool output_verbose;
extern bool dump_kernel_stack_traces;
extern bool dump_user_stack_traces;
extern bool print_cgroups;
extern bool wide_output;
extern bool print_stack_traces;
extern long sample_weight_us;

#ifdef USE_BLAZESYM
extern blaze_symbolizer *g_symbolizer;
extern bool symbolize_stacks;
#endif

// Simple hash table to store stack traces for stdout printing
#define STACK_CACHE_SIZE 4096
struct stack_cache_entry {
    __u64 hash;
    bool valid;
    char symbolized[4096];
};

static struct stack_cache_entry kernel_stack_cache[STACK_CACHE_SIZE] = {0};
static struct stack_cache_entry user_stack_cache[STACK_CACHE_SIZE] = {0};

static inline unsigned int hash_to_index(__u64 hash) {
    return (unsigned int)(hash % STACK_CACHE_SIZE);
}

// Lookup cached stack trace by hash
const char* lookup_cached_stack(__u64 hash, bool is_kernel) {
    if (hash == 0) return NULL;

    unsigned int idx = hash_to_index(hash);
    struct stack_cache_entry *cache = is_kernel ?
        &kernel_stack_cache[idx] : &user_stack_cache[idx];

    if (cache->valid && cache->hash == hash) {
        return cache->symbolized;
    }

    return NULL;
}

// Function declarations for common functions
extern const char *getusername(uid_t uid);
extern const char *format_task_state(__u32 state, int on_rq, int on_cpu, void *migration_pending);
extern const char *safe_syscall_name(__s32 syscall_nr);
extern const char *get_syscall_info_desc(__u32 syscall_nr);
extern const char *format_connection(const struct socket_info *si, char *buf, size_t buflen);
extern const char *get_connection_state(const struct socket_info *si);
extern struct timespec get_wall_from_mono(struct time_correlation *tcorr, __u64 bpf_time);
extern struct timespec sub_ns_from_ts(struct timespec ts, __u64 ns);
extern void get_str_from_ts(struct timespec ts, char *buf, size_t bufsize);
extern int check_and_rotate_files(struct output_files *files);

// Helper function to build JSON extra info string
static void build_extra_info_json(const struct task_output_event *event, char *buf, size_t buflen)
{
    buf[0] = '\0';
    char temp[512];
    int first = 1;

    strcat(buf, "{");

    // Add aio_fd if it's valid (not -1)
    if (event->aio_fd >= 0) {
        if (!first) strcat(buf, ",");
        snprintf(temp, sizeof(temp), "\"aio_fd\":%d", event->aio_fd);
        strcat(buf, temp);
        first = 0;
    }

    // Add aio_inflight_reqs for AIO syscalls (always show for AIO syscalls, even if 0)
    bool is_aio_syscall = (event->syscall_nr == __NR_io_submit ||
                          event->syscall_nr == __NR_io_getevents ||
                          event->syscall_nr == __NR_io_cancel ||
                          event->syscall_nr == __NR_io_destroy ||
                          event->syscall_nr == __NR_io_pgetevents);

    if (is_aio_syscall || event->storage.aio_inflight_reqs > 0) {
        if (!first) strcat(buf, ",");
        snprintf(temp, sizeof(temp), "\"aio_inflight_reqs\":%d", event->storage.aio_inflight_reqs);
        strcat(buf, temp);
        first = 0;
    }

    // Add io_uring SQ/CQ if they're non-zero
    if (event->storage.io_uring_sq_pending > 0) {
        if (!first) strcat(buf, ",");
        snprintf(temp, sizeof(temp), "\"uring_sq\":%d", event->storage.io_uring_sq_pending);
        strcat(buf, temp);
        first = 0;
    }

    if (event->storage.io_uring_cq_pending > 0) {
        if (!first) strcat(buf, ",");
        snprintf(temp, sizeof(temp), "\"uring_cq\":%d", event->storage.io_uring_cq_pending);
        strcat(buf, temp);
        first = 0;
    }

    // Add ur_filename if present
    if (event->ur_filename[0]) {
        if (!first) strcat(buf, ",");
        snprintf(temp, sizeof(temp), "\"uring_filename\":\"%s\"", event->ur_filename);
        strcat(buf, temp);
        first = 0;
    }

    // Add TCP stats if present
    if (event->has_tcp_stats) {
        const struct tcp_stats_info *tcp = &event->tcp_stats;

        if (!first) strcat(buf, ",");
        strcat(buf, "\"tcp\":{");

        // Congestion window and state
        snprintf(temp, sizeof(temp), "\"cwnd\":%u,\"ssthresh\":%u,\"ca_state\":%u",
                 tcp->snd_cwnd, tcp->snd_ssthresh, tcp->ca_state);
        strcat(buf, temp);

        // RTT measurements (in microseconds)
        snprintf(temp, sizeof(temp), ",\"srtt_us\":%u,\"mdev_us\":%u,\"rtt_min\":%u",
                 tcp->srtt_us, tcp->mdev_us, tcp->rtt_min);
        strcat(buf, temp);

        // Windows
        snprintf(temp, sizeof(temp), ",\"rcv_wnd\":%u,\"snd_wnd\":%u",
                 tcp->rcv_wnd, tcp->snd_wnd);
        strcat(buf, temp);

        // Packets in flight and retransmits
        snprintf(temp, sizeof(temp), ",\"packets_out\":%u,\"retrans_out\":%u,\"total_retrans\":%u",
                 tcp->packets_out, tcp->retrans_out, tcp->total_retrans);
        strcat(buf, temp);

        // Loss and reordering
        snprintf(temp, sizeof(temp), ",\"lost_out\":%u,\"sacked_out\":%u,\"reordering\":%u",
                 tcp->lost_out, tcp->sacked_out, tcp->reordering);
        strcat(buf, temp);

        // Bytes in flight (approximation: snd_nxt - snd_una)
        __u32 bytes_in_flight = tcp->snd_nxt - tcp->snd_una;
        __u32 bytes_unread = tcp->rcv_nxt - tcp->copied_seq;
        snprintf(temp, sizeof(temp), ",\"bytes_in_flight\":%u,\"bytes_unread\":%u",
                 bytes_in_flight, bytes_unread);
        strcat(buf, temp);

        // Bytes counters if available
        if (tcp->bytes_sent > 0 || tcp->bytes_acked > 0 || tcp->bytes_received > 0) {
            snprintf(temp, sizeof(temp), ",\"bytes_sent\":%llu,\"bytes_acked\":%llu,\"bytes_received\":%llu",
                     tcp->bytes_sent, tcp->bytes_acked, tcp->bytes_received);
            strcat(buf, temp);
        }

        // Delivery info
        if (tcp->delivered > 0) {
            snprintf(temp, sizeof(temp), ",\"delivered\":%u,\"delivered_ce\":%u",
                     tcp->delivered, tcp->delivered_ce);
            strcat(buf, temp);
        }

        // Flags
        if (tcp->is_cwnd_limited) {
            strcat(buf, ",\"cwnd_limited\":true");
        }
        if (tcp->reord_seen) {
            strcat(buf, ",\"reord_seen\":true");
        }
        if (tcp->retransmits > 0) {
            snprintf(temp, sizeof(temp), ",\"retransmits\":%u", tcp->retransmits);
            strcat(buf, temp);
        }

        strcat(buf, "}");
        first = 0;
    }

    // Add io_uring operation details if present
    if (event->uring_fd >= 0 || event->uring_opcode > 0 || event->uring_len > 0) {
        if (event->uring_fd >= 0) {
            if (!first) strcat(buf, ",");
            snprintf(temp, sizeof(temp), "\"uring_fd\":%d", event->uring_fd);
            strcat(buf, temp);
            first = 0;
        }

        if (!first) strcat(buf, ",");
        snprintf(temp, sizeof(temp), "\"uring_opcode\":%u", event->uring_opcode);
        strcat(buf, temp);
        first = 0;

        if (!first) strcat(buf, ",");
        snprintf(temp, sizeof(temp), "\"uring_offset\":%llu", event->uring_offset);
        strcat(buf, temp);

        if (!first) strcat(buf, ",");
        snprintf(temp, sizeof(temp), "\"uring_len\":%u", event->uring_len);
        strcat(buf, temp);

        if (event->uring_flags > 0) {
            if (!first) strcat(buf, ",");
            snprintf(temp, sizeof(temp), "\"uring_flags\":\"0x%x\"", event->uring_flags);
            strcat(buf, temp);
        }

        if (event->uring_rw_flags > 0) {
            if (!first) strcat(buf, ",");
            snprintf(temp, sizeof(temp), "\"uring_rw_flags\":\"0x%x\"", event->uring_rw_flags);
            strcat(buf, temp);
        }
    }

    // Add aio_filename if present
    if (event->aio_filename[0]) {
        if (!first) strcat(buf, ",");
        snprintf(temp, sizeof(temp), "\"aio_file\":\"%s\"", event->aio_filename);
        strcat(buf, temp);
        first = 0;
    }

    // Connection info is now displayed as separate columns, not in JSON
    // (Removed from extra_info JSON)

    // Add syscall info description if it's not "-" and not an AIO syscall (since we show actual value)
    if (!is_aio_syscall) {
        const char *sysc_desc = get_syscall_info_desc(event->syscall_nr);
        if (sysc_desc && strcmp(sysc_desc, "-") != 0) {
            if (!first) strcat(buf, ",");
            snprintf(temp, sizeof(temp), "\"info\":\"%s\"", sysc_desc);
            strcat(buf, temp);
            first = 0;
        }
    }

    strcat(buf, "}");

    // If nothing was added, return empty string instead of "{}"
    if (first) {
        buf[0] = '\0';
    }
}

#ifdef USE_BLAZESYM
// Structure to hold symbolized frame information
struct symbolized_frame {
    const char *name;
    uint64_t addr;
    uint64_t offset;
    const char *file;
    uint32_t line;
    const char *dir;
    bool is_inlined;
};

// Forward declaration
static int symbolize_user_stack(const __u64 *stack, int stack_len, pid_t pid, char *out_buf, size_t buflen);

// Symbolize kernel stack trace and format as CSV-friendly string
static int symbolize_kernel_stack(const __u64 *stack, int stack_len, char *out_buf, size_t buflen)
{
    if (!g_symbolizer || !symbolize_stacks || stack_len <= 0) {
        return 0;
    }

    struct blaze_symbolize_src_kernel src = {
        .type_size = sizeof(src),
    };

    const struct blaze_syms *syms = blaze_symbolize_kernel_abs_addrs(
        g_symbolizer, &src, (const uintptr_t *)stack, stack_len);

    if (!syms) {
        return 0;
    }

    char *ptr = out_buf;
    size_t remaining = buflen;
    int written_count = 0;

    // Format: symbol1+0xoffset;symbol2+0xoffset;...
    for (int i = 0; i < stack_len && i < syms->cnt && remaining > 1; i++) {
        if (syms->syms[i].name == NULL) continue;

        const struct blaze_sym *sym = &syms->syms[i];
        int written;

        if (written_count > 0 && remaining > 1) {
            *ptr++ = ';';
            remaining--;
        }

        // Write main symbol
        written = snprintf(ptr, remaining, "%s+0x%lx", sym->name, sym->offset);
        if (written >= remaining) break;

        ptr += written;
        remaining -= written;
        written_count++;

        // Add inlined functions if any
        for (int j = 0; j < sym->inlined_cnt && remaining > 1; j++) {
            const struct blaze_symbolize_inlined_fn *inlined = &sym->inlined[j];

            *ptr++ = ';';
            remaining--;

            written = snprintf(ptr, remaining, "%s[inlined]", inlined->name);
            if (written >= remaining) break;

            ptr += written;
            remaining -= written;
            written_count++;
        }
    }

    blaze_syms_free(syms);
    return written_count;
}


// Symbolize userspace stack trace using PID
static int symbolize_user_stack(const __u64 *stack, int stack_len, pid_t pid, char *out_buf, size_t buflen)
{
    if (!g_symbolizer || !symbolize_stacks || stack_len <= 0 || pid <= 0) {
        return 0;
    }

    struct blaze_symbolize_src_process src = {
        .type_size = sizeof(src),
        .pid = pid,
    };

    const struct blaze_syms *syms = blaze_symbolize_process_abs_addrs(
        g_symbolizer, &src, (const uintptr_t *)stack, stack_len);

    if (!syms) {
        return 0;
    }

    char *ptr = out_buf;
    size_t remaining = buflen;
    int written_count = 0;

    // Format: symbol1+0xoffset;symbol2+0xoffset;...
    for (int i = 0; i < stack_len && i < syms->cnt && remaining > 1; i++) {
        if (syms->syms[i].name == NULL) continue;

        const struct blaze_sym *sym = &syms->syms[i];
        int written;

        if (written_count > 0 && remaining > 1) {
            *ptr++ = ';';
            remaining--;
        }

        // Write main symbol
        written = snprintf(ptr, remaining, "%s+0x%lx", sym->name, sym->offset);
        if (written >= remaining) break;

        ptr += written;
        remaining -= written;
        written_count++;

        // Add inlined functions if any
        for (int j = 0; j < sym->inlined_cnt && remaining > 1; j++) {
            const struct blaze_symbolize_inlined_fn *inlined = &sym->inlined[j];

            *ptr++ = ';';
            remaining--;

            written = snprintf(ptr, remaining, "%s[inlined]", inlined->name);
            if (written >= remaining) break;

            ptr += written;
            remaining -= written;
            written_count++;
        }
    }

    blaze_syms_free(syms);
    return written_count;
}
#endif

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

    char extra_info[1024];
    build_extra_info_json(event, extra_info, sizeof(extra_info));

    // Format connection info for separate columns
    char conn_buf[256] = "";
    const char *conn_state_str = "";
    if (event->has_socket_info) {
        format_connection(&event->sock_info, conn_buf, sizeof(conn_buf));
        conn_state_str = get_connection_state(&event->sock_info);
        if (!conn_state_str) conn_state_str = "";
    }

    // Format stack hashes for stdout display based on what's enabled
    char kstack_hash_str[32] = "-";
    char ustack_hash_str[32] = "-";

    if (dump_kernel_stack_traces && event->kstack_hash != 0) {
        snprintf(kstack_hash_str, sizeof(kstack_hash_str), "%016llx", event->kstack_hash);
    }

    if (dump_user_stack_traces && event->ustack_hash != 0) {
        snprintf(ustack_hash_str, sizeof(ustack_hash_str), "%016llx", event->ustack_hash);
    }

    if (output_csv) {
        if (check_and_rotate_files(&files) < 0) {
            fprintf(stderr, "Failed to rotate output files\n");
            return -1;
        }

        fprintf(files.sample_file,
               "%s,%ld,%d,%d,%u,%llu,%s,'%s','%s','%s',%s,%s,%s,%lld,%lld,%lld,%llx,%llx,%llx,%llx,%llx,%llx,'%s','%s','%s','%s',%llx,%llx\n",
               timestamp,
               sample_weight_us,
               event->pid,
               event->tgid,
               event->storage.pid_ns_id,
               event->storage.cgroup_id,
               format_task_state(event->state, event->on_rq, event->on_cpu, event->migration_pending),
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
               conn_buf[0] ? conn_buf : "",
               conn_state_str[0] ? conn_state_str : "",
               extra_info,
               event->kstack_hash,
               event->ustack_hash
        );
    }
    else {
        // Use the new column-based formatting system for STDOUT developer mode
        column_context_t ctx = {
            .timestamp = timestamp,
            .conn_buf = conn_buf,
            .conn_state_str = conn_state_str,
            .extra_info = extra_info,
            .kstack_hash_str = kstack_hash_str,
            .ustack_hash_str = ustack_hash_str,
            .sample_weight_us = sample_weight_us,
            .off_us = (event->storage.sample_actual_ktime - event->storage.sample_start_ktime) / 1000,
            .sysc_us_so_far = sc_duration_ns / 1000,
            .sysc_entry_time_str = event->storage.sc_enter_time > 0 ? sc_start_time_str : "-"
        };

        format_stdout_line(event, &ctx);

        // Track unique stacks if needed
        if (print_stack_traces && !output_csv) {
            if (dump_kernel_stack_traces && event->kstack_hash != 0) {
                add_unique_stack(event->kstack_hash, true);
            }
            if (dump_user_stack_traces && event->ustack_hash != 0) {
                add_unique_stack(event->ustack_hash, false);
            }
        }
    }

    // Handle cgroup path resolution and caching
    if (event->storage.cgroup_id != 0 && !cgroup_cache_contains(event->storage.cgroup_id)) {
        char cgroup_path[CGROUP_PATH_MAX];
        if (resolve_cgroup_path(event->storage.cgroup_id, event->pid, cgroup_path, sizeof(cgroup_path)) == 0) {
            // Successfully resolved - it's now cached

            // Write to cgroup CSV file if in CSV mode
            if (output_csv && files.cgroup_file) {
                write_cgroup_entry(files.cgroup_file, event->storage.cgroup_id, cgroup_path);
            }

            // Print to stdout if requested (will add -c flag later)
            if (print_cgroups && !output_csv) {
                printf("CGROUP  %18llu  %s\n", event->storage.cgroup_id, cgroup_path);
            }
        }
    }

    return 0;
}

int handle_stack_event(void *ctx, void *data, size_t data_sz)
{
    enum event_type *type_ptr = (enum event_type *)data;
    enum event_type event_type = *type_ptr;

    // Safety check - only stack trace events should be in this ring buffer
    if (event_type != EVENT_STACK_TRACE) {
        fprintf(stderr, "Unexpected event type in stack traces ring buffer: %d\n", event_type);
        return 0;
    }

    const struct stack_trace_event *event = data;

    // Cache symbolized stack for stdout printing if needed
    if (print_stack_traces && !output_csv) {
        unsigned int idx = hash_to_index(event->stack_hash);
        struct stack_cache_entry *cache = event->is_kernel ?
            &kernel_stack_cache[idx] : &user_stack_cache[idx];

        cache->hash = event->stack_hash;
        cache->valid = true;

#ifdef USE_BLAZESYM
        if (g_symbolizer && symbolize_stacks) {
            int symbol_count;
            if (event->is_kernel) {
                symbol_count = symbolize_kernel_stack(event->stack, event->stack_len,
                                                     cache->symbolized, sizeof(cache->symbolized));
            } else {
                symbol_count = symbolize_user_stack(event->stack, event->stack_len,
                                                   event->pid, cache->symbolized, sizeof(cache->symbolized));
            }

            if (symbol_count == 0) {
                // Fall back to raw addresses if symbolization fails
                cache->symbolized[0] = '\0';
                for (int i = 0; i < event->stack_len && i < MAX_STACK_LEN; i++) {
                    char addr_buf[32];
                    snprintf(addr_buf, sizeof(addr_buf), "%llx;", event->stack[i]);
                    strncat(cache->symbolized, addr_buf,
                           sizeof(cache->symbolized) - strlen(cache->symbolized) - 1);
                }
            }
        } else {
#endif
            // No symbolization - just store raw addresses
            cache->symbolized[0] = '\0';
            for (int i = 0; i < event->stack_len && i < MAX_STACK_LEN; i++) {
                char addr_buf[32];
                snprintf(addr_buf, sizeof(addr_buf), "%llx;", event->stack[i]);
                strncat(cache->symbolized, addr_buf,
                       sizeof(cache->symbolized) - strlen(cache->symbolized) - 1);
            }
#ifdef USE_BLAZESYM
        }
#endif
    }

    // Determine which file to write to based on stack type
    FILE *output_file = NULL;
    if (event->is_kernel && files.kstack_file) {
        output_file = files.kstack_file;
    } else if (!event->is_kernel && files.ustack_file) {
        output_file = files.ustack_file;
    }

    // Skip if no appropriate file is open
    if (!output_file)
        return 0;

    // Write stack hash (no IS_KERNEL flag anymore)
    fprintf(output_file, "%llx,", event->stack_hash);

#ifdef USE_BLAZESYM
    // Add symbolized stack trace if available
    if (g_symbolizer && symbolize_stacks) {
        char symbol_buf[4096];
        int symbol_count;

        if (event->is_kernel) {
            symbol_count = symbolize_kernel_stack(event->stack, event->stack_len,
                                                 symbol_buf, sizeof(symbol_buf));
        } else {
            // Use PID-based symbolization for userspace stacks
            symbol_count = symbolize_user_stack(event->stack, event->stack_len,
                                               event->pid, symbol_buf, sizeof(symbol_buf));
        }

        if (symbol_count > 0) {
            fprintf(output_file, "'%s'", symbol_buf);
        } else {
            fprintf(output_file, "''");
        }
    } else {
        fprintf(output_file, "''");
    }
#else
    fprintf(output_file, "''");
#endif

    fprintf(output_file, "\n");
    fflush(output_file);

    return 0;
}
