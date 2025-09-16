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

// Callback function for bpf_loop to process each CPU
static long process_cpu(u32 index, void *ctx)
{
    __u32 cpu = index;

    // Get per-CPU data using BTF
    struct pcpu_hot *hot = bpf_per_cpu_ptr(&pcpu_hot, cpu);
    if (!hot)
        return 0;

    // Reserve space in ring buffer and initialise the event
    struct irq_stack_event *event;
    event = bpf_ringbuf_reserve(&events, sizeof(*event), 0);
    if (!event)
        return 0;

    event->cpu = cpu;
    event->timestamp = bpf_ktime_get_ns();
    event->stack_sz = 0;
    event->hardirq_in_use = 0;
    event->dump_enabled = 0;
    event->hardirq_stack_ptr = 0;

    #pragma unroll
    for (int i = 0; i < 4; i++)
        event->debug_values[i] = 0;

    // For pcpu_hot, we still need to use bpf_probe_read_kernel as it's per-CPU
    bool in_use = false;
    void *irq_stack_ptr = NULL;

    bpf_probe_read_kernel(&in_use, sizeof(in_use), &hot->hardirq_stack_inuse);
    bpf_probe_read_kernel(&irq_stack_ptr, sizeof(irq_stack_ptr), &hot->hardirq_stack_ptr);

    event->hardirq_in_use = in_use ? 1 : 0;
    event->hardirq_stack_ptr = (__u64)irq_stack_ptr;

    if (irq_stack_ptr && in_use) {
        __u64 stack_top = (__u64)irq_stack_ptr + 8;
        __u64 stack_bottom = stack_top - IRQ_STACK_SIZE;

        event->debug_values[0] = (__u64)irq_stack_ptr;  // IRQ stack pointer
        event->debug_values[1] = stack_bottom;
        event->debug_values[2] = stack_top;
        event->dump_enabled = 1;

        bpf_probe_read_kernel(event->raw_stack, IRQ_STACK_SIZE, (void *)stack_bottom);
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
