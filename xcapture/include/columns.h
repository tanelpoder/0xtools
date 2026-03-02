#ifndef __XCAPTURE_COLUMNS_H
#define __XCAPTURE_COLUMNS_H

#include <stdbool.h>
#include <stddef.h>
#include "xcapture.h"

// Forward declaration
struct task_output_event;

// Column formatting context - passed to format functions
typedef struct {
    const char *timestamp;
    const char *conn_buf;
    const char *conn_state_str;
    const char *extra_info;
    const char *kstack_hash_str;
    const char *ustack_hash_str;
    long sample_weight_us;
    long long off_us;
    long long sysc_us_so_far;
    const char *sysc_entry_time_str;
} column_context_t;

// Column definition
typedef struct {
    const char *name;       // Column identifier (lowercase)
    const char *header;     // Display header
    int width;              // <0 for left align, >0 for right align
    void (*format_fn)(char *buf, size_t len, const struct task_output_event *event, 
                     const column_context_t *ctx);
} column_def_t;

// Column indices for internal use
typedef enum {
    COL_TIMESTAMP,
    COL_WEIGHT_US,
    COL_OFF_US,
    COL_TID,
    COL_TGID,
    COL_STATE,
    COL_USERNAME,
    COL_EXE,
    COL_COMM,
    COL_CMDLINE,
    COL_SYSCALL,
    COL_SYSCALL_ACTIVE,
    COL_SYSC_US_SO_FAR,
    COL_SYSC_ARG1,
    COL_SYSC_ARG2,
    COL_SYSC_ARG3,
    COL_SYSC_ARG4,
    COL_SYSC_ARG5,
    COL_SYSC_ARG6,
    COL_FILENAME,
    COL_AIO_FILENAME,
    COL_URING_FILENAME,
    COL_SYSC_ENTRY_TIME,
    COL_SYSC_SEQ_NUM,
    COL_IORQ_SEQ_NUM,
    COL_CONNECTION,
    COL_CONN_STATE,
    COL_EXTRA_INFO,
    COL_KSTACK_HASH,
    COL_USTACK_HASH,
    COL_PIDNS,
    COL_CGROUP_ID,
    COL_TRACE_PAYLOAD,
    COL_TRACE_PAYLOAD_LEN,
    NUM_COLUMNS
} column_id_t;

// Column selection management
extern bool active_columns[NUM_COLUMNS];
extern int active_column_indices[NUM_COLUMNS];
extern int num_active_columns;

// Column definitions array
extern const column_def_t column_definitions[NUM_COLUMNS];

// Function declarations
int parse_column_list(const char *column_list);
int append_column_list(const char *column_list);
void list_available_columns(void);
void print_column_headers(void);
void format_stdout_line(const struct task_output_event *event, const column_context_t *ctx);
bool column_is_active(column_id_t column);

// Predefined column sets
extern const char *narrow_columns;
extern const char *normal_columns;
extern const char *wide_columns;

#endif /* __XCAPTURE_COLUMNS_H */
