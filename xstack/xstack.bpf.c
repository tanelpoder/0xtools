// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
// Copyright 2024-2038 Tanel Poder [0x.tools]

#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_tracing.h>
#include "xstack.h"

char LICENSE[] SEC("license") = "Dual BSD/GPL";

// Configuration map
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct filter_config);
} config_map SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 8 * 1024 * 1024);  // 8MB
} events SEC(".maps");


// Sleepable task iterator is needed for reading userspace memory of other tasks
SEC("iter.s/task")
int dump_task(struct bpf_iter__task *ctx)
{
    struct task_struct *task = ctx->task;
    
    if (!task)
        return 0;
    
    // Apply filters, filter_mode == 0 shows all tasks
    __u32 key = 0;
    struct filter_config *cfg = bpf_map_lookup_elem(&config_map, &key);
    if (!cfg)
        return 0;
    
    __u32 pid = task->pid;
    __u32 tgid = task->tgid;
    
    if (cfg->filter_mode == 1) {  // Filter by TGID (process)
        if (tgid != cfg->target_tgid)
            return 0;
    } else if (cfg->filter_mode == 2) {  // Filter by PID (thread)
        if (pid != cfg->target_pid)
            return 0;
    }

    __u32 state = task->__state;    

    // do not emit IDLE kernel threads
    if ((task->flags & PF_KTHREAD) && (state & TASK_IDLE))
        return 0;
    
    // Allocate space in ring buffer and start populating output events
    struct stack_event *event = bpf_ringbuf_reserve(&events, sizeof(*event), 0);
    if (!event)
        return 0;
    
    event->pid = pid;
    event->tgid = tgid;
   
    event->state = state;

    bpf_probe_read_kernel_str(&event->comm, sizeof(event->comm), task->comm);
    
    // Get kernel stack - this works for all tasks
    event->kstack_sz = bpf_get_task_stack(task, event->kstack, 
                                          sizeof(event->kstack), 0);
    if (event->kstack_sz < 0)
        event->kstack_sz = 0;
    else
        event->kstack_sz /= sizeof(__u64);  // Convert bytes to number of entries
    
    // Get userspace stack - need manual unwinding when reading it from other task contexts
    // bpf_get_task_stack with BPF_F_USER_STACK only works for current task in a TP context
    event->ustack_sz = 0;
    
    // Don't try to manually unwind kernel threads as we have a BPF helper for that
    if (!(task->flags & PF_KTHREAD)) {
        // Get the current stack pointer from task's pt_regs
        struct pt_regs *regs = (struct pt_regs *)bpf_task_pt_regs(task);
        if (regs) {
            // Architecture-specific frame pointer unwinding
            #if defined(__TARGET_ARCH_x86)
                // x86_64 stack frame layout:
                // struct stack_frame {
                //     void *rbp;  // next frame pointer
                //     void *rip;  // return address
                // };
                __u64 fp = BPF_CORE_READ(regs, bp);  // Frame pointer (RBP)
                __u64 sp = BPF_CORE_READ(regs, sp);  // Stack pointer (RSP)
                
                for (int i = 0; i < MAX_STACK_DEPTH; i++) {
                    if (!fp || fp < sp || fp > sp + 0x100000) {
                        // Basic sanity check: fp should be above sp and within reasonable range
                        break;
                    }
                    
                    // Read the stack frame
                    __u64 next_fp, ret_addr;
                    if (bpf_copy_from_user_task(&next_fp, sizeof(next_fp), 
                                                (void *)fp, task, 0) < 0) {
                        break;
                    }
                    if (bpf_copy_from_user_task(&ret_addr, sizeof(ret_addr), 
                                                (void *)(fp + 8), task, 0) < 0) {
                        break;
                    }
                    
                    // Store the return address using loop index (verifier-safe)
                    if (i < MAX_STACK_DEPTH) {
                        event->ustack[i] = ret_addr;
                        event->ustack_sz = i + 1;
                    }
                    
                    // Move to next frame
                    fp = next_fp;
                }
            #elif defined(__TARGET_ARCH_arm64)
                // ARM64 frame pointer unwinding
                // struct stack_frame {
                //     void *fp;  // x29 - next frame pointer
                //     void *lr;  // x30 - return address
                // };
                __u64 fp = BPF_CORE_READ(regs, regs[29]);  // Frame pointer (x29)
                __u64 sp = BPF_CORE_READ(regs, sp);        // Stack pointer
                
                // #pragma unroll
                for (int i = 0; i < MAX_STACK_DEPTH; i++) {
                    if (!fp || fp < sp || fp > sp + 0x100000) {
                        break;
                    }
                    
                    // Read the stack frame
                    __u64 next_fp, ret_addr;
                    if (bpf_copy_from_user_task(&next_fp, sizeof(next_fp), 
                                                (void *)fp, task, 0) < 0) {
                        break;
                    }
                    if (bpf_copy_from_user_task(&ret_addr, sizeof(ret_addr), 
                                                (void *)(fp + 8), task, 0) < 0) {
                        break;
                    }
                    
                    // Store the return address using loop index (verifier-safe)
                    if (i < MAX_STACK_DEPTH) {
                        event->ustack[i] = ret_addr;
                        event->ustack_sz = i + 1;
                    }
                    
                    // Move to next frame
                    fp = next_fp;
                }
            #endif
        }
    }
    
    bpf_ringbuf_submit(event, 0);
    
    return 0;
}
