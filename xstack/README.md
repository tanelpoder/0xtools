# xstack - Passive Linux stack profiling without any tracepoints

**xstack v3.0.0** by Tanel Poder [[0x.tools](https://0x.tools)]

A lightweight, completely passive stack profiler for Linux that uses eBPF task iterators to sample thread states and stack traces without injecting any tracepoints, kprobes, or perf events into the system.

## Features

- **Completely passive profiling** - No instrumentation or overhead on target processes
- **Dual stack capture** - Reads both kernel and userspace stack traces
- **Flexible filtering** - Sample all tasks, specific process, or individual thread
- **CSV output** - Easy to parse and analyze with standard tools
- **Stack symbolization** - Converts addresses to function names (with [BlazeSym](https://github.com/libbpf/blazesym))

## Installation

### Prerequisites

- Linux kernel **5.18+** (`bpf_copy_from_user_task()` helper)
  - RHEL 9.5+ works with its RHEL **5.14** kernel too as they [backported](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html-single/9.5_release_notes/index#new-features-kernel) eBPF 6.8 subsystem to RHEL 5.14
  - OEL 9 works with either RHEL compatible kernel (5.14) or Oracle UEK8 (6.12)
- Root privileges or CAP_BPF capability
- Development tools: `gcc`, `make`, `clang`, `llvm`
- Rust/Cargo (for BlazeSym stack symbolization support)

### Install system packages

Ubuntu 22.x or 24.x (with 6.x kernel):

```
sudo apt install make gcc pkg-config libbpf-dev libbpf-tools clang llvm libbfd-dev libelf1 libelf-dev zlib1g-dev rustc cargo
```

RHEL 9.5+ (with RHEL 5.14 kernel):

```
sudo dnf install libbpf libbpf-tools clang llvm-devel binutils-devel elfutils-libelf elfutils-libelf-devel zlib-devel rust cargo
```

## Build

The 0x.tools repository contains multiple tools in their own subdirectories, for **xstack** just `cd xstack` and run make there:

```bash
# Clone the repository
git clone https://github.com/tanelpoder/0xtools
cd 0xtools/xstack

# Clone libbpf and blazesym submodules
git submodule update --init --recursive

make

./xstack --help
```

## Usage

### Basic Syntax

```
xstack -a | -p PID | -t TID [-F HZ] [-i NUM] [-q] [-r]
```

You must specify one of: `-a` (all), `-p PID` (process), or `-t TID` (thread)

### Command-line Options

| Option | Long Form | Description |
|--------|-----------|-------------|
| `-a` | `--all` | Sample all tasks/threads in the system |
| `-p PID` | `--pid PID` | Filter by process ID (includes all threads) |
| `-t TID` | `--tid TID` | Filter by specific thread ID |
| `-F HZ` | `--freq HZ` | Sampling frequency in Hz (1-1000, default: 1) |
| `-i NUM` | `--iterations NUM` | Number of sampling iterations (default: infinite) |
| `-q` | `--quiet` | Suppress CSV header output |
| `-r` | `--reverse-stack` | Reverse stack order (outermost first) |

### Examples

```bash
# Sample all tasks continuously at 1 Hz
sudo xstack -a

# Sample specific process and its threads at 10 Hz
sudo xstack -p 1234 -F 10

# Sample specific thread for 100 iterations at 5 Hz
sudo xstack -t 5678 -F 5 -i 100

# Sample current shell at 10 Hz for 10 seconds
sudo xstack -p $$ -F 10 -i 100

# Quiet mode with reversed stacks (for FlameGraphs)
sudo xstack -qra
```

## Output Format

CSV format with the following columns:
1. `timestamp` - Wall clock time with microsecond precision
2. `tid` - Thread ID (kernel PID)
3. `tgid` - Process ID (kernel TGID)
4. `comm` - Command name (16 chars max)
5. `state` - Task state (RUNNING, SLEEP, DISK, etc.)
6. `ustack` - Userspace stack trace (semicolon-separated)
7. `kstack` - Kernel stack trace (semicolon-separated)

### Example Output

```csv
timestamp,tid,tgid,comm,state,ustack,kstack
2025-08-14 10:03:14.837215,1,1,systemd,SLEEP,main+0x123;__libc_start_main+0x45,ep_poll+0x372;do_epoll_wait+0xde
2025-08-14 10:03:14.837243,2,2,kthreadd,SLEEP,[no_ustack],kthread+0x173;ret_from_fork+0x22
```

## FlameGraph Generation

An example of how I feed xstack output to the [flamelens](https://github.com/YS-L/flamelens) terminal UI app is in my blog:

* https://tanelpoder.com/posts/xstack-passive-linux-stack-sampler-ebpf/

## Architecture Support

- **x86_64** - Full support with frame pointer unwinding
- **ARM64/aarch64** - Full support with frame pointer unwinding

## Limitations

- Requires frame pointers for simple userspace stack unwinding (`-fno-omit-frame-pointer`)

## License

GPL-2.0 OR BSD-3-Clause

## Author

Tanel Poder - [tanelpoder.com](https://tanelpoder.com)
