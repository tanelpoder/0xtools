// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024-2038 Tanel Poder [0x.tools]

#ifndef __XCAPTURE_H
#define __XCAPTURE_H

#ifdef __BPF__
#define UINT32_MAX 0xFFFFFFFF
#include "vmlinux.h"
#endif

#include "tcp_stats.h"

#define TASK_COMM_LEN      16
#define MAX_STACK_LEN     127
#define MAX_FILENAME_LEN  256
#define MAX_CMDLINE_LEN   128  // task argv
#define MAX_CONN_INFO_LEN 128  // "TCP 1.2.3.4:80->5.6.7.8:12345" for IPv4
#define TRACE_PAYLOAD_LEN 512

// kernel task states here so we don't have to include kernel headers
#define TASK_RUNNING          0x00000000
#define TASK_INTERRUPTIBLE    0x00000001
#define TASK_UNINTERRUPTIBLE  0x00000002
#define TASK_STOPPED          0x00000004
#define TASK_TRACED           0x00000008
/* Used in tsk->exit_state: */
#define EXIT_DEAD             0x00000010
#define EXIT_ZOMBIE           0x00000020
#define EXIT_TRACE (EXIT_ZOMBIE | EXIT_DEAD)
/* Used in tsk->state again: */
#define TASK_PARKED           0x00000040
#define TASK_DEAD             0x00000080
#define TASK_WAKEKILL         0x00000100
#define TASK_WAKING           0x00000200
#define TASK_NOLOAD           0x00000400
#define TASK_NEW              0x00000800
#define TASK_RTLOCK_WAIT      0x00001000
#define TASK_FREEZABLE        0x00002000
#define TASK_FREEZABLE_UNSAFE 0x00004000
#define TASK_FROZEN           0x00008000
#define TASK_STATE_MAX        0x00010000

#define TASK_IDLE (TASK_UNINTERRUPTIBLE | TASK_NOLOAD)

// task flags from linux/sched.h
#define PF_KSWAPD             0x00020000  /* I am kswapd */
#define PF_KTHREAD            0x00200000  /* I am a kernel thread */

// linux/vmalloc.h
#define VM_IOREMAP            0x00000001  /* ioremap() and friends */
#define VM_ALLOC              0x00000002  /* vmalloc() */
#define VM_MAP                0x00000004  /* vmap()ed pages */
#define VM_USERMAP            0x00000008  /* suitable for remap_vmalloc_range */
#define VM_DMA_COHERENT       0x00000010  /* dma_alloc_coherent */
#define VM_UNINITIALIZED      0x00000020  /* vm_struct is not fully initialized */
#define VM_NO_GUARD           0x00000040  /* *** DANGEROUS*** don't add guard page */
#define VM_KASAN              0x00000080  /* has allocated kasan shadow memory */
#define VM_FLUSH_RESET_PERMS  0x00000100  /* reset direct map and flush TLB on unmap, can't be freed in atomic context */
#define VM_MAP_PUT_PAGES      0x00000200  /* put pages and free array in vfree */
#define VM_ALLOW_HUGE_VMAP    0x00000400  /* Allow for huge pages on archs with HAVE_ARCH_HUGE_VMALLOC */
#define VM_DEFER_KMEMLEAK     0x00000800  /* defer kmemleak object creation */
#define VM_SPARSE             0x00001000  /* sparse vm_area. not all pages are present. */


// devices
#define MINORBITS 20
#define MINORMASK ((1U << MINORBITS) - 1)
#define MKDEV(ma,mi) (((ma) << MINORBITS) | (mi))
#define MAJOR(dev) ((unsigned int) ((dev) >> MINORBITS))
#define MINOR(dev) ((unsigned int) ((dev) & MINORMASK))

// tracking if there are any IO requests in aio rings for heuristic reasoning
// if the later io_[p]getevents calls are blocked or in an idle loop at app level
struct aio_ctx_key {
    __u32 tgid;
    __u64 ctx_id;
} __attribute__((packed));

struct aio_ctx_info {
    pid_t tid;              // Thread ID that last called io_submit
    __u64 last_submit_ts;   // Timestamp of last io_submit call
    __u32 submit_count;     // Number of io_submit calls for this context
};

// ringbuf struct type
enum event_type {
    EVENT_TASK_INFO = 1,
    EVENT_SYSCALL_COMPLETION = 2,
    EVENT_IORQ_COMPLETION = 3,
    EVENT_STACK_TRACE = 4
};

// Structure for tracking in-flight block I/O requests
struct iorq_info {
    bool iorq_sampled:1;       // Whether this was caught by task_iter sampler and must be emitted on completion
    __u64 iorq_sequence_num;   // Sequence number from submitting task
    pid_t insert_pid;          // Task that queued the I/O (if queuing was needed)
    pid_t insert_tgid;         // Process that queued the I/O
    pid_t issue_pid;           // Task that issued the I/O to block device driver
    pid_t issue_tgid;          // Process that issued the I/O
};

// Fields that need to be emitted to userspace (Extended Task State)
struct task_state {
    pid_t pid;                    // having pid/tgid duplicated here allow tracking probes
    pid_t tgid;                   // to avoid looking up the task_struct if they get the task_storage anyway
    __u64 sample_start_ktime;     // CLOCK_MONOTONIC ns (all tasks have same sample_time)
    __u64 sample_actual_ktime;    // CLOCK_MONOTONIC ns (debug for sample duration analysis)

    bool   sc_sampled:1;          // task iterator will set the following fields only if it catches a task in syscall
    __s32  in_syscall_nr;
    __u64  sc_enter_time;
    __u64  sc_sequence_num;       // any syscall entry in a task will increment this single counter (tracepoint)
    __u64  prev_sc_sequence_num;  // edge case: deal with long idle aio getevents calls ongoing before xcapture start

    __u64 iorq_sequence_num;           // sequence number for all iorq submissions by this task
    struct request *last_iorq_rq;      // Last iorq submitted, task_iter updates iorq_sampled=true for this
    __u32 last_iorq_dev;               // Device (MKDEV) for last iorq
    __u64 last_iorq_sector;            // Sector for last iorq
    struct request *last_iorq_sampled; // save the rq address that was ongoing during sample (for emitting later)
    __u32 last_iorq_dev_sampled;       // Saved device for sampled iorq
    __u64 last_iorq_sector_sampled;    // Saved sector for sampled iorq
    __u64 last_iorq_sequence_num;      // snapshot used by sampler for interesting IORQs (rq + seq)

    __u32 aio_inflight_reqs;      // number of inflight requests in aio ring (0 means idle, waiting for work)
    __u32 io_uring_sq_pending;    // number of pending submissions in io_uring SQ
    __u32 io_uring_cq_pending;    // number of pending completions in io_uring CQ

    // Context switch tracking for stack trace optimization
    __u64 nvcsw;                  // voluntary context switches
    __u64 nivcsw;                 // involuntary context switches
    __u64 last_total_ctxsw;       // nvcsw + nivcsw from previous sample

    // Namespace and cgroup information
    __u32 pid_ns_id;               // PID namespace inode number
    __u64 cgroup_id;               // Cgroup v2 ID from task->cgroups->dfl_cgrp->kn->id

    __u32 trace_payload_len;       // Length of captured request payload prefix
    __u8  trace_payload[TRACE_PAYLOAD_LEN];
    __s32 trace_payload_syscall;   // Syscall number associated with payload (if any)
    __u64 trace_payload_seq_num;   // Syscall sequence number that produced payload
};

// Fields for BPF internal task local caching only
struct task_cache {
    __u64 pending_trace_buf;        // userspace buffer pointer captured on syscall entry
    __u32 pending_trace_len;        // requested read length on syscall entry
    __s32 pending_trace_syscall;    // syscall number to correlate entry/exit
    __s32 pending_trace_fd;         // file descriptor associated with buffered payload
    __u8  pending_trace_is_write;   // direction hint (1=write,0=read)
    __u8  reserved_trace_flags[3];  // pad to keep alignment predictable
    int cached_kstack_len;              // Cached kernel stack length
    __u64 cached_kstack[MAX_STACK_LEN]; // Cached kernel stack (127 entries)
    int cached_ustack_len;              // Cached user stack length  
    __u64 cached_ustack[MAX_STACK_LEN]; // Cached user stack (127 entries)
    __u64 uring_last_user_data;       // Last SQE user_data tracked for CQ correlation
    __s32 uring_last_fd;              // Last SQE fd (or -1 for registered files)
    __s32 uring_last_reg_idx;         // Last registered index when IOSQE_FIXED_FILE was used
    __u64 uring_last_file_ptr;        // Kernel pointer to struct file when known
};

// This is the central "extended Task State Array" (eTSA)
// to be used with BPF_MAP_TYPE_TASK_STORAGE for maximum awesomeness
struct task_storage {
    struct task_state state;   // ~160 bytes - what we emit to userspace
    struct task_cache cache;   // ~2032 bytes - internal BPF use only
};

// Syscall completion event structure for ringbuf
struct sc_completion_event {
    enum event_type type;
    pid_t pid;
    pid_t tgid;
    __u64 completed_sc_sequence_num;
    __u64 completed_sc_enter_time;
    __u64 completed_sc_exit_time;
    __s64 completed_sc_ret_val;
    __s32 completed_syscall_nr;
    __u32 trace_payload_len;
    __s32 trace_payload_syscall;
    __u64 trace_payload_seq_num;
    __u8  trace_payload[TRACE_PAYLOAD_LEN];
};

// Block I/O completion event structure for ringbuf
struct iorq_completion_event {
    enum event_type type;
    void *rq;                 // request pointer (for debugging/reference)
    pid_t insert_pid;
    pid_t insert_tgid;
    pid_t issue_pid;
    pid_t issue_tgid;
    pid_t complete_pid;
    pid_t complete_tgid;
    __u64 iorq_sequence_num;
    __u64 iorq_insert_time;
    __u64 iorq_issue_time;
    __u64 iorq_complete_time;
    __u32 iorq_dev;
    __u64 iorq_sector;
    __u32 iorq_bytes;
    __u32 iorq_cmd_flags;
    __s32 iorq_error;
};


// network connection tracking
#define XCAPTURE_UNIX_PATH_MAX 108

struct socket_info {
    __u16 family;     // AF_INET or AF_INET6
    __u16 protocol;   // IPPROTO_TCP or IPPROTO_UDP
    __u8  state;      // TCP socket state (TCP_LISTEN, TCP_ESTABLISHED, etc.)
    __u8  socket_type;// SOCK_STREAM / SOCK_DGRAM / ...
    union {
        __u32 saddr_v4;
        __u8  saddr_v6[16];  // Changed from __int128
    };
    union {
        __u32 daddr_v4;
        __u8  daddr_v6[16];  // Changed from __int128
    };
    __u16 sport;
    __u16 dport;
    __u32 unix_peer_pid;      // Peer PID for AF_UNIX sockets (0 if unknown)
    __u32 unix_owner_uid;     // Owner UID for AF_UNIX sockets (0 if unknown)
    __u64 unix_inode;         // Inode number for AF_UNIX sockets (0 if unknown)
    __u64 unix_peer_inode;    // Peer inode when available (0 if unknown)
    __u16 unix_path_len;      // Length of valid bytes in unix_path
    __u8  unix_is_abstract;   // 1 when socket path is abstract (starts with @)
    __u8  unix_pad;           // Pad to 8-byte alignment
    char  unix_path[XCAPTURE_UNIX_PATH_MAX]; // Normalized Unix path (no leading @)
};


// This gets emitted to userspace via ringbuf
struct task_output_event {
    enum event_type type;

    // Task struct fields
    pid_t pid;
    pid_t tgid;
    __u32 state;
    __u32 flags;
    uid_t euid;
    char comm[TASK_COMM_LEN];

    __s32 emit_reason;

    // Task's additional data
    __s32 syscall_nr;
    __u64 syscall_args[6];
    char filename[MAX_FILENAME_LEN];
    char exe_file[MAX_FILENAME_LEN];
    __u32 cmdline_len;
    char cmdline[MAX_CMDLINE_LEN];

    // Socket info
    struct socket_info sock_info;
    bool has_socket_info:1;
    bool has_tcp_stats:1;

    // TCP statistics (only populated for TCP sockets)
    struct tcp_stats_info tcp_stats;

    // I/O file descriptor (for AIO operations, libaio only for now)
    int aio_fd;

    // io_uring CQE filename (when CQ has pending completions)
    char ur_filename[MAX_FILENAME_LEN];

    // io_uring SQE filename (when SQ has pending submissions)
    char ur_sq_filename[MAX_FILENAME_LEN];

    // AIO filename (when in io_submit/io_getevents syscalls)
    char aio_filename[MAX_FILENAME_LEN];

    // io_uring operation details (populated when CQ has pending completions)
    __s32 uring_fd;        // File descriptor from io_uring SQE (-1 for registered files)
    __s32 uring_reg_idx;   // Registered file index (when IOSQE_FIXED_FILE is set)
    __u64 uring_offset;    // File offset for io_uring operation
    __u32 uring_len;       // Buffer size for io_uring operation
    __u8 uring_opcode;     // io_uring operation code
    __u8 uring_flags;      // IOSQE_* flags
    __u32 uring_rw_flags;  // RWF_* flags for io_uring operation

    // Debug instrumentation for io_uring filename resolution
    __s32 uring_dbg_sq_idx;        // SQE index chosen for inspection
    __s32 uring_dbg_sq_fixed;      // 1 if IOSQE_FIXED_FILE was set
    __u64 uring_dbg_sq_user_data;  // user_data captured from SQE
    __u64 uring_dbg_sq_file_ptr;   // struct file * pointer resolved for SQE
    __s32 uring_dbg_cq_scanned;    // number of CQ entries scanned
    __s32 uring_dbg_cq_matched;    // 1 if CQ user_data matched tracked SQE
    __u64 uring_dbg_cq_file_ptr;   // struct file * pointer resolved for CQ

    // Task's scheduler state
    int on_cpu;
    int on_rq;
    void *migration_pending;
    bool in_execve:1;
    bool in_iowait:1;
    bool in_thrashing:1;
    bool sched_remote_wakeup:1;

    // Extended task state storage (only the state portion)
    struct task_state storage;  // Was: struct task_storage storage

    // Stack trace hashes (actual stacks are written separately to kstacks file)
    __u64 kstack_hash;  // Hash of kernel stack (0 = no stack)
    __u64 ustack_hash;  // Hash of userspace stack (0 = no stack)

};

// Stack trace event for unique stacks
struct stack_trace_event {
    enum event_type type;
    __u64 stack_hash;         // Unique hash of this stack
    bool is_kernel:1;         // true = kernel stack, false = userspace stack
    int stack_len;            // Number of addresses
    pid_t pid;                // PID for userspace stack symbolization
    __u64 stack[MAX_STACK_LEN]; // Stack addresses
};

#endif /* __XCAPTURE_H */
