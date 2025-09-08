# xcapture - High-Performance Linux System Monitor

## Overview

**xcapture** is a sophisticated Linux system monitoring tool that leverages eBPF technology to provide high-performance, low-overhead system activity sampling and task state tracking. Part of the 0xtools performance analysis toolkit, it captures detailed information about running processes, system calls, and I/O operations with minimal impact on system performance.

## Key Features

- **Passive Sampling**: Non-intrusive periodic monitoring using BPF task iterators
- **Selective Tracking**: Optional syscall and I/O completion tracking for sampled operations
- **Stack Traces**: Kernel and userspace stack collection with deduplication
- **IDLE Detection**: Smart heuristic to distinguish idle daemons from active clients
- **Flexible Output**: Human-readable stdout or structured CSV with hourly rotation
- **Minimal Overhead**: Kernel-space filtering and selective emission reduce CPU impact

## Requirements

- Linux kernel 5.18 or newer (uses sleepable BPF iterators)
- Root privileges (required for eBPF operations)
- Optional: Rust/Cargo for stack symbolization support

## Installation

```bash
# Clone the repository
git clone https://github.com/0xtools/0xtools-next.git
cd 0xtools-next/xcapture

# Build xcapture
make

# Optional: Build without stack symbolization (faster)
make USE_BLAZESYM=0
```

## Usage

### Basic Examples

```bash
# Sample at default 1 Hz, showing only active tasks
sudo ./xcapture

# Sample all tasks including sleeping ones at 10 Hz
sudo ./xcapture -a -F 10

# Filter by process ID
sudo ./xcapture -p 1234

# Save output to CSV files
sudo ./xcapture -o /tmp/xcapture_data

# Run for exactly 100 iterations at 20 Hz (5 seconds)
sudo ./xcapture -F 20 -i 100
```

### Advanced Examples

```bash
# Collect kernel stack traces with symbolization
sudo ./xcapture -k -s

# Track system call completions
sudo ./xcapture -t syscall

# Track I/O request completions
sudo ./xcapture -t iorq

# Custom column selection
sudo ./xcapture -g "tid,comm,state,syscall"

# Wide output with all columns
sudo ./xcapture -w
```

## Output Modes

### Stdout Mode (Default)

Human-readable text output with configurable columns:
- **Narrow** (`-n`): Minimal essential columns
- **Normal**: Standard columns with timestamps
- **Wide** (`-w`): All columns including connection state and extra info

### CSV Mode (`-o DIR`)

Structured CSV files with hourly rotation:
- `xcapture_samples_*.csv`: Task sampling data
- `xcapture_syscend_*.csv`: System call completions
- `xcapture_iorqend_*.csv`: I/O request completions
- `xcapture_kstacks_*.csv`: Kernel stack traces
- `xcapture_ustacks_*.csv`: Userspace stack traces

## Command-Line Options

| Option | Description |
|--------|-------------|
| `-F HZ` | Sampling frequency in Hz (default: 1) |
| `-i N` | Exit after N iterations |
| `-a` | Show all tasks including sleeping |
| `-p PID` | Filter by process/thread group ID |
| `-k` | Dump kernel stack traces |
| `-u` | Dump userspace stack traces |
| `-s` | Print stack traces in stdout |
| `-t TYPE` | Enable tracking (syscall, iorq) |
| `-o DIR` | Output CSV files to directory |
| `-n` | Narrow output mode |
| `-w` | Wide output mode |
| `-g COLS` | Custom column selection |
| `-d PORT` | Daemon port threshold (default: 10000) |

## Architecture

xcapture uses a modular architecture with the main eBPF probe (`task.bpf.c`) leveraging helper libraries for specific functionality:

- **Core Probe**: Lightweight task iterator (549 lines) focuses on sampling logic
- **Helper Libraries**: Modular functions for I/O operations, file descriptors, and network analysis
- **User Space**: Processes events and formats output for human or machine consumption

## How It Works

### Sampling Architecture

xcapture uses a two-phase approach:

1. **Sampling Phase** (periodic):
   - BPF task iterator walks all system tasks
   - Collects state, syscall context, file descriptors
   - Marks active operations for tracking
   
2. **Tracking Phase** (optional, event-driven):
   - Monitors syscall and I/O completions
   - Only emits events for previously sampled operations
   - Minimizes overhead by selective tracking

### IDLE Thread Detection

xcapture uses a port-based heuristic to classify sleeping threads:
- Threads on ports ≤ daemon_ports (default 10000) are considered idle daemons
- Threads on higher ports are treated as active clients waiting for responses
- Adjustable via `-d` option for custom environments

### Performance Optimization

- **Kernel-space filtering**: Reduces data transfer to userspace
- **Stack deduplication**: FNV-1a hashing prevents duplicate transmission
- **Selective emission**: Only tracks sampled operations
- **Ring buffers**: Zero-copy data transfer from kernel

## Troubleshooting

### Common Issues

**"Failed to load BPF skeleton"**
- Ensure kernel version is 5.18 or newer
- Check for sufficient BPF permissions

**No output visible**
- Use `-a` to show all tasks including sleeping
- Check process filter with `-p` option

**Missing stack symbols**
- Build with `USE_BLAZESYM=1` (default)
- Install Rust/Cargo toolchain

**High CPU usage**
- Reduce sampling frequency (lower `-F` value)
- Use process filtering (`-p`) to limit scope

## Integration with 0xtools

xcapture is designed to work with other 0xtools utilities:
- Output format compatible with xtop for visualization
- Stack traces can be analyzed with flame graph tools
- CSV output suitable for further analysis with standard tools

## Contributing

Contributions are welcome! Please see the project's GitHub repository for guidelines.

## License

This project is licensed under the MIT License - see the LICENSE file for details.