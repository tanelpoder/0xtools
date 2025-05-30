// Update xcapture_user.h
#ifndef __XCAPTURE_USER_H
#define __XCAPTURE_USER_H

#include <time.h>
#include <stdio.h>

#define DEFAULT_OUTPUT_DIR "."
#define SAMPLE_CSV_FILENAME "xcapture_samples" // .csv will be appended later
#define KSTACK_CSV_FILENAME "xcapture_kstacks"
#define SYSC_COMPLETION_CSV_FILENAME "xcapture_syscend"
#define IORQ_COMPLETION_CSV_FILENAME "xcapture_iorqend"

// For converting BPF ktime to wallclock time
struct time_correlation {
    struct timespec wall_time;    // CLOCK_REALTIME
    struct timespec mono_time;    // CLOCK_MONOTONIC: what bpf_ktime_get_ns() returns
};

// Hourly csv output files
struct output_files {
    FILE *sample_file;
    FILE *sc_completion_file;
    FILE *iorq_completion_file;
    FILE *kstack_file;
    int current_year;    // Track full timestamp in case of long VM pauses
    int current_month;   // that may cause the timestamp to jump by 24 hours or more
    int current_day;
    int current_hour;
};

// Shared variables
extern pid_t mypid;
extern struct time_correlation tcorr;
extern struct output_files files;
extern bool output_csv;
extern bool output_verbose;
extern bool dump_stack_traces;

// Shared function declarations
extern const char *getusername(uid_t uid);
extern const char *format_task_state(__u32 state);
extern const char *safe_syscall_name(__s32 syscall_nr);
extern const char *get_syscall_info_desc(__u32 syscall_nr);
extern const char *get_iorq_op_flags(__u32 cmd_flags);
extern const char *format_connection(const struct socket_info *si, char *buf, size_t buflen);
extern struct timespec get_wall_from_mono(struct time_correlation *tcorr, __u64 bpf_time);
extern struct timespec sub_ns_from_ts(struct timespec ts, __u64 ns);
extern void get_str_from_ts(struct timespec ts, char *buf, size_t bufsize);
extern int check_and_rotate_files(struct output_files *files);

#endif /* __XCAPTURE_USER_H */
