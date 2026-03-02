#ifndef __XCAPTURE_TYPES_H
#define __XCAPTURE_TYPES_H

#include <stdio.h>
#include <time.h>

struct time_correlation {
    struct timespec wall_time;    // CLOCK_REALTIME
    struct timespec mono_time;    // CLOCK_MONOTONIC: what bpf_ktime_get_ns() returns
};

struct output_files {
    FILE *sample_file;
    FILE *sc_completion_file;
    FILE *iorq_completion_file;
    FILE *kstack_file;
    FILE *ustack_file;
    FILE *cgroup_file;
    int current_year;    // Track full timestamp in case of long VM pauses
    int current_month;   // that may cause the timestamp to jump by 24 hours or more
    int current_day;
    int current_hour;
};

#endif /* __XCAPTURE_TYPES_H */
