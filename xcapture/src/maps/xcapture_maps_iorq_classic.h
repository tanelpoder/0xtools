#ifndef XCAPTURE_MAPS_IORQ_CLASSIC_H
#define XCAPTURE_MAPS_IORQ_CLASSIC_H

// Map for tracking block I/O operations (classic mode)
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 1024 * 1024);
    __type(key, struct request *);
    __type(value, struct iorq_info);
    __uint(pinning, XCAP_MAP_PINNING);
} iorq_tracking SEC(".maps");

#endif /* XCAPTURE_MAPS_IORQ_CLASSIC_H */
