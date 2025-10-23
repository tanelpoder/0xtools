// Update xcapture_user.h
#ifndef __XCAPTURE_USER_H
#define __XCAPTURE_USER_H

#include <stdbool.h>
#include <stddef.h>
#include <linux/types.h>
#include "xcapture_types.h"

#define XCAP_UNUSED(x) (void)(x)

#define DEFAULT_OUTPUT_DIR "."
#define SAMPLE_CSV_FILENAME "xcapture_samples" // .csv will be appended later
#define KSTACK_CSV_FILENAME "xcapture_kstacks"
#define USTACK_CSV_FILENAME "xcapture_ustacks"
#define SYSC_COMPLETION_CSV_FILENAME "xcapture_syscend"
#define IORQ_COMPLETION_CSV_FILENAME "xcapture_iorqend"
#define XCAP_BUFSIZ (256 * 1024)

// Forward declarations
struct socket_info;
struct xcapture_context;

// Shared function declarations
extern const char *getusername(uid_t uid);
extern const char *format_task_state(__u32 state, int on_rq, int on_cpu, void *migration_pending);
extern const char *safe_syscall_name(__s32 syscall_nr);
extern const char *get_syscall_info_desc(__u32 syscall_nr);
extern const char *get_iorq_op_flags(__u32 cmd_flags);
extern const char *format_connection(const struct socket_info *si, char *buf, size_t buflen);
extern const char *get_connection_state(const struct socket_info *si);
extern struct timespec get_wall_from_mono(struct time_correlation *tcorr, __u64 bpf_time);
extern struct timespec sub_ns_from_ts(struct timespec ts, __u64 ns);
extern void get_str_from_ts(struct timespec ts, char *buf, size_t bufsize);
extern void close_output_files(struct output_files *files);
extern int check_and_rotate_files(struct output_files *files, const struct xcapture_context *ctx);
extern void add_unique_stack(__u64 hash, bool is_kernel);
extern void reset_unique_stacks();
extern const char* lookup_cached_stack(__u64 hash, bool is_kernel);

static inline void bytes_to_hex(const __u8 *src, size_t len, char *dst, size_t dstlen)
{
    if (!dst || dstlen == 0) return;

    size_t needed = len * 2 + 1;
    if (dstlen < needed) {
        dst[0] = '\0';
        return;
    }

    static const char hex[] = "0123456789abcdef";
    for (size_t i = 0; i < len; i++) {
        __u8 byte = src[i];
        dst[i * 2] = hex[byte >> 4];
        dst[i * 2 + 1] = hex[byte & 0x0F];
    }
    dst[len * 2] = '\0';
}

#endif /* __XCAPTURE_USER_H */
