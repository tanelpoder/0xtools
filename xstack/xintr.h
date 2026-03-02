// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
// xintr - CPU interrupt stack sampler by Tanel Poder [0x.tools]

#ifndef __XINTR_H
#define __XINTR_H

#define MAX_STACK_DEPTH          127 // used in userspace only (we copy full 16kB kernel/irq stack)
#define MAX_CPUS                1024 // max 4096 on modern kernels (reduce on kernels without bpf_loop())

// IRQ stack sizes (x86_64)   
#define IRQ_STACK_SIZE         16384  // 16KB for hardware IRQ stack (THREAD_SIZE)
#define STACK_CHUNK_SIZE          64  // Copy stack in 64-byte cache-line chunks in reverse direction

// Event sent from kernel to userspace
struct irq_stack_event {
    __u32 cpu;                        // CPU number
    __u64 timestamp;                  // Timestamp in nanoseconds
    __s32 stack_sz;                   // Number of stack entries
    bool  hardirq_in_use;             // Whether hardirq stack is in use
    __u8  dump_enabled;               // Whether to dump raw stack memory
    __u64 hardirq_stack_ptr;          // IRQ stack base pointer (for debugging)
    __u64 top_of_stack;               // IRQ stack top_of_stack value from pcpu_hot
    __u64 call_depth;                 // Hardirq call depth tracking value (not always populated)
    __u64 debug_values[4];            // Debug: values for debugging
    __u8  raw_stack[IRQ_STACK_SIZE];  // Raw 16KB stack dump (only populated when dump_enabled)
};

#endif /* __XINTR_H */
