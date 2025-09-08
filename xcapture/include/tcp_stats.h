#ifndef __TCP_STATS_H
#define __TCP_STATS_H

#ifndef __BPF__
#include <linux/types.h>
#endif

// TCP statistics structure for performance analysis
struct tcp_stats_info {
    // Connection state
    __u8 ca_state;          // Congestion avoidance state
    __u8 retransmits;       // Number of retransmits
    __u8 probes_out;        // Unanswered zero window probes
    __u8 backoff;           // Exponential backoff
    
    // Window sizes
    __u32 snd_cwnd;         // Congestion window
    __u32 snd_ssthresh;     // Slow start threshold
    __u32 rcv_wnd;          // Receive window
    __u32 snd_wnd;          // Send window (peer's receive window)
    
    // RTT measurements (in microseconds)
    __u32 srtt_us;          // Smoothed RTT
    __u32 mdev_us;          // Medium deviation
    __u32 rtt_min;          // Minimum RTT seen
    
    // Throughput related
    __u32 packets_out;      // Packets in flight
    __u32 retrans_out;      // Retransmitted packets out
    __u32 max_packets_out;  // Max packets in flight so far
    __u32 total_retrans;    // Total retransmits for this connection
    
    // Buffer/Queue sizes
    __u32 write_seq;        // Tail of data to send
    __u32 snd_una;          // First unacknowledged sequence
    __u32 snd_nxt;          // Next sequence to send
    __u32 rcv_nxt;          // Next sequence expected
    __u32 copied_seq;       // Head of yet unread data
    
    // Performance indicators  
    __u32 lost_out;         // Lost packets
    __u32 sacked_out;       // SACK'd packets
    __u32 reordering;       // Packet reordering metric
    __u32 delivered;        // Total packets delivered
    __u32 delivered_ce;     // Packets delivered with CE mark (ECN)
    
    // Bytes counters
    __u64 bytes_sent;       // Total bytes sent (if available)
    __u64 bytes_acked;      // Total bytes acked
    __u64 bytes_received;   // Total bytes received
    
    // Flags
    __u8 ecn_flags;         // ECN flags
    __u8 reord_seen:1;      // Reordering detected
    __u8 is_cwnd_limited:1; // Connection is cwnd limited
    __u8 reserved:6;
};

#endif /* __TCP_STATS_H */