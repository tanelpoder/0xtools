// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
// Copyright 2024 Tanel Poder [0x.tools]

#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "xcapture.h"

char LICENSE[] SEC("license") = "Dual BSD/GPL";
char VERSION[] = "3.0.0";

// ? figure this out without including kernel .h files (platform and kconfig-dependent)
#define PAGE_SIZE 4096
#define THREAD_SIZE (PAGE_SIZE << 2)

// for map_get lookups
static __u32 zero = 0;


// kernel 5.14 state to __state change
struct {
  __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
  __uint(max_entries, 1);
  __type(key, __u32);
  __type(value, struct task_info);
} task_info_buf SEC(".maps");

struct task_struct___post514 {
  unsigned int __state;
} __attribute__((preserve_access_index));

struct task_struct___pre514 {
  long state;
} __attribute__((preserve_access_index));


// extended task storage
struct {
    __uint(type, BPF_MAP_TYPE_TASK_STORAGE);
    __uint(map_flags, BPF_F_NO_PREALLOC);
    __type(key, int);
    __type(value, struct task_storage);
} task_storage SEC(".maps");


// static struct task_storage *get_task_storage(struct task_struct *task)
// {
//     struct task_storage *storage;
//     
//     storage = bpf_task_storage_get(&task_storage, task, NULL, BPF_LOCAL_STORAGE_GET_F_CREATE);
//     bpf_printk("bpf_task_storage_get = %llx \n", storage);
// 
//     if (!storage)
//         return NULL;
//         
//     return storage;
// }


static __u32 get_task_state(void *arg)
{
    if (bpf_core_field_exists(struct task_struct___pre514, state)) {
        struct task_struct___pre514 *task = arg;
        return task->state;
    } else {
        struct task_struct___post514 *task = arg;
        return task->__state;
    }
}



SEC("raw_tracepoint/sys_enter")
int handle_sys_enter(struct bpf_raw_tracepoint_args *ctx)
{
    struct task_storage *storage;

    storage = bpf_task_storage_get(&task_storage, bpf_get_current_task_btf(), 0, 
                                  BPF_LOCAL_STORAGE_GET_F_CREATE);

    if (!storage)
        return 0;
    
    storage->sc_enter_time = bpf_ktime_get_ns();
    storage->sc_sequence_num += 1;
    storage->in_syscall_nr = (s32)ctx->args[1];  // syscall nr
    return 0;
}

SEC("raw_tracepoint/sys_exit")
int handle_sys_exit(struct bpf_raw_tracepoint_args *ctx)
{
    struct task_storage *storage;
    
    storage = bpf_task_storage_get(&task_storage, bpf_get_current_task_btf(), 0,
                                  BPF_LOCAL_STORAGE_GET_F_CREATE);
    if (!storage)
        return 0;
    
    storage->in_syscall_nr = -1;
    storage->sc_enter_time = 0;
    return 0;
}


SEC("iter/task")
int get_tasks(struct bpf_iter__task *ctx)
{
    struct seq_file *seq = ctx->meta->seq;
    struct task_info *t;
    struct pt_regs *syscall_regs;
    long ret;

    struct task_struct *task = ctx->task;
    if (!task)
        return 0;

    // in-kernel filtering: early check and bailout if not a thread or state of interest
    __u32 task_state = get_task_state(task);
    __u32 task_flags = task->flags;
  
    // idle kernel worker thread waiting for work or other kernel threads in S state
    if ((task_state & TASK_NOLOAD) || ((task_flags & PF_KTHREAD) && (task_state & TASK_INTERRUPTIBLE)))
        return 0;

    // monotonic clock source for event duration sampling
    __u64  sample_ktime = bpf_ktime_get_ns();

    t = bpf_map_lookup_elem(&task_info_buf, &zero);
    if (!t)
        return 0;

    t->addr = task; // used later on for task storage lookup
    t->pid = task->pid;
    t->tgid = task->tgid;
    t->flags = task_flags;
    t->state = task_state;
    t->euid = BPF_CORE_READ(task, cred, euid.val);
    bpf_probe_read_kernel_str(t->comm, TASK_COMM_LEN, task->comm);

    // Read executable file name
    struct mm_struct *mm = BPF_CORE_READ(task, mm);
    if (mm) {
        struct file *exe_file = BPF_CORE_READ(mm, exe_file);
        if (exe_file) {
            struct path file_path;
            BPF_CORE_READ_INTO(&file_path, exe_file, f_path);
            struct dentry *dentry = BPF_CORE_READ(exe_file, f_path.dentry);

            if (dentry) {
                struct qstr d_name = BPF_CORE_READ(dentry, d_name);
                bpf_probe_read_kernel_str(t->exe_file, sizeof(t->exe_file), d_name.name);
            } else {
                __builtin_memcpy(t->exe_file, "[NO_DENTRY]", 12);
            }
        } else {
            __builtin_memcpy(t->exe_file, "[NO_EXE]", 9);
        }
    } else {
        __builtin_memcpy(t->exe_file, "[NO_MM]", 8);
    }

    // Read task (kernel) stack page start and find where the top stack frame is
    // https://www.kernel.org/doc/html/next/x86/kernel-stacks.html (actual THREAD_SIZE can be more than 2 x PAGE_SIZE)
    // Calculate the address of pt_regs
    unsigned long stack_pointer = (unsigned long) BPF_CORE_READ(task, stack);
    t->kstack_ptr = (void *) stack_pointer;
    struct pt_regs *regs = (struct pt_regs *)(stack_pointer + THREAD_SIZE) - 1;
    t->regs_ptr = regs;
    t->thread_size = THREAD_SIZE;

    // Read syscall nr and arguments from registers saved when invoking the syscall
    // on x86_64 ABI the args are stored in: rdi, rsi, rdx, r10, r8, r9
    if(regs) {
        t->syscall_nr = (__s32) BPF_CORE_READ(regs, orig_ax);  // orig_ax holds syscall number (TODO: change for ARM64)
        t->syscall_args[0] = PT_REGS_PARM1_CORE_SYSCALL(regs);
        t->syscall_args[1] = PT_REGS_PARM2_CORE_SYSCALL(regs);
        t->syscall_args[2] = PT_REGS_PARM3_CORE_SYSCALL(regs);
        t->syscall_args[3] = PT_REGS_PARM4_CORE_SYSCALL(regs);
        t->syscall_args[4] = PT_REGS_PARM5_CORE_SYSCALL(regs);
        t->syscall_args[5] = PT_REGS_PARM6_CORE_SYSCALL(regs);
    }
    else {
        t->syscall_nr = -2;
    }

    // this shorthand should be possible: filename = BPF_CORE_READ(task, files, fdt, fd, f_path.dentry, d_name.name);
    struct file *file;
    struct files_struct *files = BPF_CORE_READ(task, files);
    struct fdtable *fdt = BPF_CORE_READ(files, fdt);
    struct file **fd_array = BPF_CORE_READ(fdt, fd);

    char filename[MAX_FILENAME_LEN];

    // read fd nr: X from process'es fd array (TODO: only do this for syscalls that have a single-fd arg0)
    bpf_probe_read_kernel(&file, sizeof(file), &fd_array[t->syscall_args[0]]);

    if (file) {
        // bpf_d_path() doesn't work in a non-tracing task iterator program context?
        struct path file_path;
        bpf_probe_read_kernel(&file_path, sizeof(file_path), &file->f_path);
        struct dentry *dentry = BPF_CORE_READ(file, f_path.dentry);
        struct qstr d_name = BPF_CORE_READ(dentry, d_name);

        bpf_probe_read_kernel_str(t->filename, sizeof(t->filename), d_name.name);
    } else {
        t->full_path[0] = '-'; t->full_path[1] = '\0';
        t->filename[0] = '-'; t->filename[1] = '\0';
    }

    ret = bpf_get_task_stack(task, t->kstack, sizeof(__u64) * MAX_STACK_LEN, 0);
    t->kstack_len = ret <= 0 ? ret : ret / sizeof(t->kstack[0]);

    // read task storage map experiment
    struct task_storage *storage;

    storage = bpf_task_storage_get(&task_storage, task, NULL, BPF_LOCAL_STORAGE_GET_F_CREATE);

    if (!storage) // for the verifier
        return 0;

    t->storage.in_syscall_nr = storage->in_syscall_nr;
    t->storage.sample_ktime  = sample_ktime;
    t->storage.sc_enter_time = storage->sc_enter_time;
    t->storage.sc_sequence_num    = storage->sc_sequence_num;

    bpf_seq_write(seq, t, sizeof(struct task_info));
    return 0;
}



