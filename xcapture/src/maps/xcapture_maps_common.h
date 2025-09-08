#ifndef XCAPTURE_MAPS_COMMON_H
#define XCAPTURE_MAPS_COMMON_H

// Common maps shared by multiple BPF programs

// Task storage map for maintaining per-task state (extended thread state)
struct {
    __uint(type, BPF_MAP_TYPE_TASK_STORAGE);
    __uint(map_flags, BPF_F_NO_PREALLOC);
    __type(key, int);
    __type(value, struct task_storage);
    __uint(pinning, LIBBPF_PIN_BY_NAME);
} task_storage SEC(".maps");

// Ring buffers for event completion records and sampled task info
struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 16 * 1024 * 1024);  // bytes
    __uint(pinning, LIBBPF_PIN_BY_NAME);
} completion_events SEC(".maps");

// The task_samples map has periodic bursts of task iterator record writes
struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 16 * 1024 * 1024);  // bytes
    __uint(pinning, LIBBPF_PIN_BY_NAME);
} task_samples SEC(".maps");

// Ring buffer for unique stack traces
struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 8 * 1024 * 1024);  // 8MB for stack traces
    __uint(pinning, LIBBPF_PIN_BY_NAME);
} stack_traces SEC(".maps");

// Map for tracking which stack traces have already been emitted
// Key is the MD5 hash of the stack, value is a flag (1 = emitted)
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 1024 * 1024);
    __type(key, __u64);
    __type(value, __u8);
    __uint(pinning, LIBBPF_PIN_BY_NAME);
} emitted_stacks SEC(".maps");


#endif /* XCAPTURE_MAPS_COMMON_H */
