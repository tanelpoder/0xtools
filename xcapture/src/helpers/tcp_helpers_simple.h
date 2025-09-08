#ifndef __TCP_HELPERS_H
#define __TCP_HELPERS_H

#include "vmlinux.h"
#include "tcp_stats.h"

// Ultra-simplified TCP statistics extraction to avoid verifier complexity
static __always_inline bool get_tcp_stats(struct sock *sk, struct tcp_stats_info *stats)
{
    if (!sk || !stats)
        return false;
    
    // Initialize all fields to 0
    __builtin_memset(stats, 0, sizeof(*stats));
    
    // Cast to tcp_sock - the verifier should understand this better
    struct tcp_sock *tp = (struct tcp_sock *)sk;
    
    // Read basic congestion control fields
    stats->snd_cwnd = BPF_CORE_READ(tp, snd_cwnd);
    stats->snd_ssthresh = BPF_CORE_READ(tp, snd_ssthresh);
    
    // Read packets and retransmission info
    stats->packets_out = BPF_CORE_READ(tp, packets_out);
    stats->retrans_out = BPF_CORE_READ(tp, retrans_out);
    stats->total_retrans = BPF_CORE_READ(tp, total_retrans);
    
    // Read RTT measurements (should be in microseconds in newer kernels)
    stats->srtt_us = BPF_CORE_READ(tp, srtt_us);
    stats->mdev_us = BPF_CORE_READ(tp, mdev_us);
    
    // Read window sizes
    stats->rcv_wnd = BPF_CORE_READ(tp, rcv_wnd);
    stats->snd_wnd = BPF_CORE_READ(tp, snd_wnd);
    
    // Read sequence numbers for calculating bytes in flight
    stats->write_seq = BPF_CORE_READ(tp, write_seq);
    stats->snd_una = BPF_CORE_READ(tp, snd_una);
    stats->snd_nxt = BPF_CORE_READ(tp, snd_nxt);
    stats->rcv_nxt = BPF_CORE_READ(tp, rcv_nxt);
    
    // Loss and reordering
    stats->lost_out = BPF_CORE_READ(tp, lost_out);
    stats->sacked_out = BPF_CORE_READ(tp, sacked_out);
    stats->reordering = BPF_CORE_READ(tp, reordering);
    
    // Try to read delivered if available (kernel 4.6+)
    if (bpf_core_field_exists(tp->delivered)) {
        stats->delivered = BPF_CORE_READ(tp, delivered);
    }
    
    return true;
}

// Helper to check if we should collect TCP stats for this socket
static __always_inline bool should_collect_tcp_stats(struct socket_info *si)
{
    // Only collect for TCP sockets that are not in LISTEN state
    return si && si->protocol == IPPROTO_TCP && si->state != TCP_LISTEN;
}

#endif /* __TCP_HELPERS_H */