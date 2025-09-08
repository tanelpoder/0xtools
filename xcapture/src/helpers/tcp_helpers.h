#ifndef __TCP_HELPERS_H
#define __TCP_HELPERS_H

#include "vmlinux.h"
#include "tcp_stats.h"

// Extract TCP statistics from a tcp_sock
static __always_inline bool get_tcp_stats(struct sock *sk, struct tcp_stats_info *stats)
{
    if (!sk || !stats)
        return false;
    
    // Cast to tcp_sock - but we need to be careful about accessing fields
    // The verifier needs explicit reads through BPF_CORE_READ
    struct tcp_sock *tp = (struct tcp_sock *)sk;
    
    // Congestion control state - ca_state is a bitfield, need special handling
    // Use BPF_PROBE_READ to safely read the bitfield
    __u8 ca_state = 0;
    bpf_probe_read_kernel(&ca_state, sizeof(ca_state), 
                          (void *)sk + bpf_core_field_offset(struct tcp_sock, inet_conn.icsk_ca_state));
    stats->ca_state = ca_state & 0x7;  // ca_state is 3 bits
    stats->retransmits = BPF_CORE_READ(tp, inet_conn.icsk_retransmits);
    stats->probes_out = BPF_CORE_READ(tp, inet_conn.icsk_probes_out);
    stats->backoff = BPF_CORE_READ(tp, inet_conn.icsk_backoff);
    
    // Window sizes (snd_cwnd is in packets, need to check if we can get MSS)
    stats->snd_cwnd = BPF_CORE_READ(tp, snd_cwnd);
    stats->snd_ssthresh = BPF_CORE_READ(tp, snd_ssthresh);
    stats->rcv_wnd = BPF_CORE_READ(tp, rcv_wnd);
    stats->snd_wnd = BPF_CORE_READ(tp, snd_wnd);
    
    // RTT measurements - srtt_us and mdev_us are already in microseconds in newer kernels
    // For older kernels they might be in jiffies << 3 and jiffies << 2
    stats->srtt_us = BPF_CORE_READ(tp, srtt_us);
    stats->mdev_us = BPF_CORE_READ(tp, mdev_us);
    
    // Try to read min_rtt if available (kernel 4.10+)
    // The rtt_min field is a struct minmax with s[0].v containing the minimum value
    if (bpf_core_field_exists(tp->rtt_min)) {
        // Read the minimum RTT value directly using nested access
        stats->rtt_min = BPF_CORE_READ(tp, rtt_min.s[0].v);
    } else {
        stats->rtt_min = 0;
    }
    
    // Packets in flight
    stats->packets_out = BPF_CORE_READ(tp, packets_out);
    stats->retrans_out = BPF_CORE_READ(tp, retrans_out);
    
    // Total retransmits
    stats->total_retrans = BPF_CORE_READ(tp, total_retrans);
    
    // Try to read max_packets_out if available
    if (bpf_core_field_exists(tp->max_packets_out)) {
        stats->max_packets_out = BPF_CORE_READ(tp, max_packets_out);
    } else {
        stats->max_packets_out = 0;
    }
    
    // Sequence numbers (for calculating bytes in flight)
    stats->write_seq = BPF_CORE_READ(tp, write_seq);
    stats->snd_una = BPF_CORE_READ(tp, snd_una);
    stats->snd_nxt = BPF_CORE_READ(tp, snd_nxt);
    stats->rcv_nxt = BPF_CORE_READ(tp, rcv_nxt);
    stats->copied_seq = BPF_CORE_READ(tp, copied_seq);
    
    // Loss and reordering
    stats->lost_out = BPF_CORE_READ(tp, lost_out);
    stats->sacked_out = BPF_CORE_READ(tp, sacked_out);
    stats->reordering = BPF_CORE_READ(tp, reordering);
    
    // Delivery info (kernel 4.6+)
    if (bpf_core_field_exists(tp->delivered)) {
        stats->delivered = BPF_CORE_READ(tp, delivered);
        stats->delivered_ce = BPF_CORE_READ(tp, delivered_ce);
    } else {
        stats->delivered = 0;
        stats->delivered_ce = 0;
    }
    
    // Bytes counters
    if (bpf_core_field_exists(tp->bytes_sent)) {
        stats->bytes_sent = BPF_CORE_READ(tp, bytes_sent);
    } else {
        stats->bytes_sent = 0;
    }
    
    if (bpf_core_field_exists(tp->bytes_acked)) {
        stats->bytes_acked = BPF_CORE_READ(tp, bytes_acked);
    } else {
        stats->bytes_acked = 0;
    }
    
    if (bpf_core_field_exists(tp->bytes_received)) {
        stats->bytes_received = BPF_CORE_READ(tp, bytes_received);
    } else {
        stats->bytes_received = 0;
    }
    
    // ECN flags
    stats->ecn_flags = BPF_CORE_READ(tp, ecn_flags);
    
    // Reordering seen
    if (bpf_core_field_exists(tp->reord_seen)) {
        stats->reord_seen = BPF_CORE_READ(tp, reord_seen);
    } else {
        stats->reord_seen = 0;
    }
    
    // Check if connection is cwnd limited - is_cwnd_limited is a bitfield
    if (bpf_core_field_exists(tp->is_cwnd_limited)) {
        stats->is_cwnd_limited = BPF_CORE_READ_BITFIELD(tp, is_cwnd_limited);
    } else {
        stats->is_cwnd_limited = 0;
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