#ifndef __XCAPTURE_CONTEXT_H
#define __XCAPTURE_CONTEXT_H

#include <stdbool.h>
#include <sys/types.h>
#include "xcapture_types.h"

struct xcapture_context {
    pid_t mypid;
    bool output_csv;
    bool output_verbose;
    bool dump_kernel_stack_traces;
    bool dump_user_stack_traces;
    bool wide_output;
    bool narrow_output;
    bool print_stack_traces;
    bool print_cgroups;
    bool print_uring_debug;
    bool payload_trace_enabled;
    const char *output_dirname;
    long sample_weight_us;
    char *custom_columns;
    char *append_columns;
    struct output_files files;
    struct time_correlation tcorr;
};

#endif /* __XCAPTURE_CONTEXT_H */
