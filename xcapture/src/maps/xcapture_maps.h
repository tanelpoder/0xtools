#ifndef XCAPTURE_MAPS_H
#define XCAPTURE_MAPS_H

// LIBBPF_PIN_BY_NAME is needed so that different object
// files would be able to share the same map (by design)
// and not create their own disconnected private copies

// Task storage map for maintaining per-task state (extended thread state)
struct {
    __uint(type, BPF_MAP_TYPE_TASK_STORAGE);
    __uint(map_flags, BPF_F_NO_PREALLOC);
    __type(key, int);
    __type(value, struct task_storage);
    __uint(pinning, LIBBPF_PIN_BY_NAME);
} task_storage SEC(".maps");

// Command line option passing for "tasks of interst" filtering
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct filter_config);
    __uint(pinning, LIBBPF_PIN_BY_NAME);
} filter_config_map SEC(".maps");

// Map for tracking block I/O operations
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 1024 * 1024);
    __type(key, struct request *);
    __type(value, struct iorq_info);
    __uint(pinning, LIBBPF_PIN_BY_NAME);
} iorq_tracking SEC(".maps");

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

#endif /* XCAPTURE_MAPS_H */
