// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
// xintr - CPU interrupt stack sampler by Tanel Poder [0x.tools]
//
// This is currently an experimental prototype working only on 6.2+ or RHEL 5.14+ on x86_64
// Test this out on Ubuntu or Fedora compiled kernels, as RHEL, OEL, Debian have not enabled
// CONFIG_FRAME_POINTER=y for their kernel builds.
//
// I plan to experiment with stack forensics & ORC unwinding in userspace,
// to support such platforms.

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

// Define pcpu_hot structure (present in 6.1+ kernels)
// I will add support for 5.x in a future release
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

// Per-CPU "hot items struct" symbol defined in x86 kernels (mainline 6.1+ or RHEL 5.14+)
extern struct pcpu_hot pcpu_hot __ksym;

// Callback function for bpf_loop to process each CPU
static long process_cpu(u32 index, void *ctx)
{
    __u32 cpu = index;

    // Get per-CPU data using BTF info. later we'll use bpf_probe_read_kernel
    // instead of BTF pointer deref as it's a per-CPU struct
    struct pcpu_hot *hot = bpf_per_cpu_ptr(&pcpu_hot, cpu);
    if (!hot)
        return 0;

    // Reserve space in ring buffer and initialize the output event
    struct irq_stack_event *event;
    event = bpf_ringbuf_reserve(&events, sizeof(*event), 0);
    if (!event)
        return 0;

    event->cpu = cpu;
    event->timestamp = bpf_ktime_get_ns();
    event->stack_sz = 0;
    event->hardirq_in_use = false;
    event->dump_enabled = 0;
    event->hardirq_stack_ptr = 0;
    event->top_of_stack = 0;
    event->call_depth = 0;

    #pragma unroll
    for (int i = 0; i < 4; i++)
        event->debug_values[i] = 0;

    bool in_use = false;

    bpf_probe_read_kernel(&in_use, sizeof(in_use), &hot->hardirq_stack_inuse);
    event->hardirq_in_use = in_use;

    bpf_probe_read_kernel(&event->hardirq_stack_ptr, sizeof(void *), &hot->hardirq_stack_ptr);

    // We are copying stack mem in reverse direction (from highest addr to lowest)
    // to get a more consistent snapshot of the fast changing stack
    if (event->hardirq_stack_ptr && in_use) {
        __u64 stack_highest = event->hardirq_stack_ptr + 8;
        __u64 stack_lowest = stack_highest - IRQ_STACK_SIZE;

        for (int offset = IRQ_STACK_SIZE - STACK_CHUNK_SIZE;
                 offset >= 0; offset -= STACK_CHUNK_SIZE) {
            bpf_probe_read_kernel(event->raw_stack + offset,
                                  STACK_CHUNK_SIZE,
                                  (void *)(stack_lowest + offset));
        }

        event->debug_values[0] = event->hardirq_stack_ptr;  // IRQ stack pointer
        event->debug_values[1] = stack_lowest;
        event->debug_values[2] = stack_highest;
        event->dump_enabled = 1;
    }

    // Some other potentially useful values, currently unused
    bpf_probe_read_kernel(&event->top_of_stack, sizeof(event->top_of_stack), &hot->top_of_stack);
    bpf_probe_read_kernel(&event->call_depth, sizeof(event->call_depth), &hot->call_depth);

    // todo: cancel event instead of submitting when !in_use
    bpf_ringbuf_submit(event, 0);
    return 0;
}

// Main BPF iterator loop. xintr uses the task iterator just to dive into eBPF
// kernel mode and loops through available CPU structs under the first task found
SEC("iter/task")
int sample_cpu_irq_stacks(struct bpf_iter__task *ctx)
{
    struct task_struct *task = ctx->task;
    if (!task)
        return 0;

    bpf_loop(MAX_CPUS, process_cpu, NULL, 0);

    return 1;
}
