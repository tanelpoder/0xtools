// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
// xintr - CPU interrupt stack sampler (refactored with modern eBPF)
//
// This is currently a prototype working only on 6.2+ or RHEL 5.14+ on x86_64
// Related: https://tanelpoder.com/posts/ebpf-pt-regs-error-on-linux-blame-fred/

#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_tracing.h>
#include "xintr.h"

char LICENSE[] SEC("license") = "Dual BSD/GPL";

const volatile bool dump_enabled = false;
const volatile bool everything_mode = false;

struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 8 * 1024 * 1024);  // 8MB
} events SEC(".maps");

// Define pcpu_hot structure (from kernel)
// Using preserve_access_index for BTF-based relocations
struct pcpu_hot {
    union {
        struct {
            struct task_struct *current_task;
            int preempt_count;
            int cpu_number;
            __u64 call_depth;
            unsigned long top_of_stack;
            void *hardirq_stack_ptr;
            __u16 softirq_pending;
            bool hardirq_stack_inuse;
        };
        __u8 pad[64];
    };
} __attribute__((preserve_access_index));

// Per-CPU "hot items struct" symbol defined in x86 kernels (mainline 6.2+ or RHEL 5.14+)
extern struct pcpu_hot pcpu_hot __ksym;

// Helper to check if address looks like kernel text
static __always_inline bool is_kernel_text_addr(__u64 addr)
{
    // Kernel text addresses on x86_64: 0xFFFFFFFF80000000+
    return (addr >> 48) == 0xFFFF && addr >= 0xFFFFFFFF80000000ULL;
}

// Context for stack scanning callback
struct stack_scan_ctx {
    struct irq_stack_event *event;
    __u64 stack_top;
    __u64 stack_bottom;
    int found;
    __u64 last_valid_rbp;   // Last valid RBP value we found
    bool everything_mode;   // Skip frame validation if true
};

// Callback for bpf_loop to scan stack
static long scan_stack_callback(u32 index, void *ctx)
{
    struct stack_scan_ctx *scan_ctx = (struct stack_scan_ctx *)ctx;

    if (scan_ctx->found >= MAX_STACK_DEPTH)
        return 1;

    // Scan from top downward, 8-byte aligned
    __u64 addr = scan_ctx->stack_top - (index * 8);

    if (addr < scan_ctx->stack_bottom)
        return 1;

    __u64 val = 0;
    if (bpf_probe_read_kernel(&val, sizeof(val), (void *)addr) == 0) {
        if (is_kernel_text_addr(val)) {

            bool valid_frame = false;

            if (scan_ctx->everything_mode) {
                valid_frame = true;

            } else {
                // Simplified frame validation that balances accuracy with completeness
                // Goal: capture legitimate frames while filtering obvious garbage
                
                __u64 saved_rbp = 0;
                bpf_probe_read_kernel(&saved_rbp, sizeof(saved_rbp), (void *)(addr - 8));
                
                // Basic sanity checks to filter out obvious garbage
                bool looks_valid = false;
                
                // Check 1: Is this likely an interrupt/exception entry?
                __u64 addr_offset = val & 0xFFFULL;
                bool is_likely_entry = (addr_offset < 0x200);  // Small offset from function start
                
                // Check 2: Does the saved RBP look reasonable?
                bool rbp_in_range = (saved_rbp >= scan_ctx->stack_bottom && 
                                     saved_rbp < scan_ctx->stack_top &&
                                     saved_rbp > addr);
                
                // Check 3: Avoid symbols with huge offsets (like tls_device_lock+0x3ebecf5e)
                // These are likely misidentified addresses at the end of kernel ksym space
                bool reasonable_offset = (addr_offset < 0x1000);  // Assume that IRQ handling functions rarely exceed 4KB
                
                if (scan_ctx->found == 0) {
                    // First frame: be permissive to start the chain
                    // Accept if it's an entry point OR has valid RBP OR looks reasonable
                    if (is_likely_entry || rbp_in_range || reasonable_offset) {
                        looks_valid = true;
                        scan_ctx->last_valid_rbp = saved_rbp;
                    }
                } else if (scan_ctx->found < 3) {
                    // Early frames: still be somewhat permissive
                    // Many interrupt handlers don't have perfect frame chains
                    if (reasonable_offset && (is_likely_entry || rbp_in_range)) {
                        looks_valid = true;
                        scan_ctx->last_valid_rbp = saved_rbp;
                    }
                } else {
                    // Later frames: apply stricter validation
                    if (rbp_in_range && reasonable_offset) {
                        // Optional: verify the chain points to something that looks like a frame
                        __u64 next_rip = 0;
                        if (bpf_probe_read_kernel(&next_rip, sizeof(next_rip),
                                                  (void *)(saved_rbp + 8)) == 0) {
                            if (is_kernel_text_addr(next_rip)) {
                                looks_valid = true;
                                scan_ctx->last_valid_rbp = saved_rbp;
                            }
                        }
                    }
                }
                
                valid_frame = looks_valid;
            }

            if (valid_frame) {
                scan_ctx->event->stack[scan_ctx->found++] = val;
            }
        }
    }

    return 0; // continue to next bpf_loop iteration
}

// Helper to collect stack trace from interrupt stack
static __always_inline void collect_irq_stack_trace(struct irq_stack_event *event,
                                                    __u64 stack_top, __u64 stack_bottom)
{
    // With VMAP_STACK: stack_bottom is the base, stack_top is the highest address
    // Scan from top downward to find kernel text addresses

    struct stack_scan_ctx ctx = {
        .event = event,
        .stack_top = stack_top,
        .stack_bottom = stack_bottom,
        .found = 0,
        .last_valid_rbp = 0,
        .everything_mode = everything_mode
    };

    // Scan up to 2048 stack positions (16KB / 8 bytes)
    bpf_loop(2048, scan_stack_callback, &ctx, 0);

    event->stack_sz = ctx.found;
}

// Callback function for bpf_loop to process each CPU
static long process_cpu(u32 index, void *ctx)
{
    __u32 cpu = index;

    // Get per-CPU data using BTF
    struct pcpu_hot *hot = bpf_per_cpu_ptr(&pcpu_hot, cpu);
    if (!hot)
        return 0;

    // Reserve space in ring buffer
    struct irq_stack_event *event;
    event = bpf_ringbuf_reserve(&events, sizeof(*event), 0);
    if (!event)
        return 0;

    // Initialize output event (manually since structure is too large for memset)
    event->cpu = cpu;
    event->timestamp = bpf_ktime_get_ns();
    event->stack_sz = 0;
    event->hardirq_in_use = 0;
    event->dump_enabled = dump_enabled;
    event->hardirq_stack_ptr = 0;
    
    // Zero out debug values
    #pragma unroll
    for (int i = 0; i < 4; i++) {
        event->debug_values[i] = 0;
    }
    
    // Zero out stack entries
    #pragma unroll
    for (int i = 0; i < MAX_STACK_DEPTH; i++) {
        event->stack[i] = 0;
    }

    // For pcpu_hot, we still need to use bpf_probe_read_kernel as it's per-CPU
    bool in_use = false;
    void *irq_stack_ptr = NULL;

    bpf_probe_read_kernel(&in_use, sizeof(in_use), &hot->hardirq_stack_inuse);
    bpf_probe_read_kernel(&irq_stack_ptr, sizeof(irq_stack_ptr), &hot->hardirq_stack_ptr);

    event->hardirq_in_use = in_use ? 1 : 0;
    event->hardirq_stack_ptr = (__u64)irq_stack_ptr;

    if (irq_stack_ptr && in_use) {
        __u64 stack_top = (__u64)irq_stack_ptr + 8;  // Round up to page boundary
        __u64 stack_bottom = stack_top - IRQ_STACK_SIZE;

        event->debug_values[0] = (__u64) irq_stack_ptr;       // IRQ stack pointer
        event->debug_values[1] = stack_bottom;                // Stack bottom address
        event->debug_values[2] = stack_top;                   // Stack top address
        event->debug_values[3] = 0;                           // Reserved

        // Collect stack trace
        collect_irq_stack_trace(event, stack_top, stack_bottom);
        
        // If dump is enabled, copy the full 16KB raw stack
        if (dump_enabled) {
            // Copy the full IRQ stack from bottom to top
            bpf_probe_read_kernel(event->raw_stack, IRQ_STACK_SIZE, (void *)stack_bottom);
        }
    }

    bpf_ringbuf_submit(event, 0);
    return 0;
}

// Main BPF program
SEC("iter/task")
int sample_cpu_irq_stacks(struct bpf_iter__task *ctx)
{
    // Use task iterator as a trigger to run my CPU iterator program
    struct task_struct *task = ctx->task;
    if (!task)
        return 0;

    bpf_loop(MAX_CPUS, process_cpu, NULL, 0);

    // Stop iteration after first task
    return 1;
}
