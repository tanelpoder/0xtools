// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
#ifndef __XINTR_H
#define __XINTR_H

#define MAX_STACK_DEPTH 32
#define MAX_CPUS 4096 // max on modern kernels

// IRQ stack sizes (x86_64)
#define IRQ_STACK_SIZE 16384  // 16KB for hardware IRQ stack (THREAD_SIZE)

// Event sent from kernel to userspace
struct irq_stack_event {
    __u32 cpu;                        // CPU number
    __u64 timestamp;                  // Timestamp in nanoseconds
    __s32 stack_sz;                   // Number of stack entries
    __u8  hardirq_in_use;             // Whether hardirq stack is in use
    __u8  dump_enabled;               // Whether to dump raw stack memory
    __u64 hardirq_stack_ptr;          // IRQ stack base pointer (for debugging)
    __u64 debug_values[4];            // Debug: values for debugging
    __u64 stack[MAX_STACK_DEPTH];     // Stack entries
    __u8  raw_stack[IRQ_STACK_SIZE];  // Raw 16KB stack dump (only populated when dump_enabled)
};

#endif /* __XINTR_H */
