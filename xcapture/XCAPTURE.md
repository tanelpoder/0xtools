# xcapture - High-Performance Linux System Monitor

## Overview

**xcapture** samples Linux task state with eBPF task iterators and, when requested, tracks syscall and block I/O completions observed in the latest sample. The hybrid passive/active design keeps overhead low while still providing rich insight into running workloads. xcapture ships as part of the 0xtools performance toolkit.

## Requirements

- Linux kernel 5.18 or newer with BTF and sleepable iterator support
- `CAP_BPF` and `CAP_SYS_ADMIN`; the simplest workflow is to run with `sudo`
- Optional Rust/Cargo toolchain when building with BlazeSym stack symbolization (enabled by default)

## Build & Installation

```bash
# Configure and build (native example)
cmake -S . -B build -DCMAKE_INSTALL_PREFIX=/usr
cmake --build build

# Stage or install
DESTDIR=dest cmake --install build

# Package generation (inside build directory)
cpack -G DEB
cpack -G RPM        # requires the rpm package
```

- Maintain separate build directories per architecture (e.g., `build-x86_64`, `build-aarch64` with `cmake/toolchains/aarch64-linux-gnu.cmake`).
- Disable BlazeSym by adding `-DUSE_BLAZESYM=OFF` during configuration when stack symbolization is unnecessary.

## Service & Non-Root Operation

- Packages provision an `xcapture` service user, log (`/var/log/xcapture`) and data (`/var/lib/xcapture`) directories, and capability grants so the daemon can load programs and attach iterators.
- To run manually without full root privileges: `sudo setcap cap_bpf,cap_sys_admin+epi /usr/bin/xcapture`, ensure `/sys/fs/bpf` is writable if map pinning is needed, and set `ulimit -l unlimited` before launching the binary as the delegated user.

## Quickstart Usage

Always supply a finite iteration count for predictable runs.

```bash
# Default 1 Hz sampling, active tasks only
sudo ./build/xcapture -i 10

# Sample all tasks at 10 Hz
sudo ./build/xcapture -a -F 10 -i 50

# Focus on a single process
sudo ./build/xcapture -p 1234 -F 20 -i 40

# Record CSV output
sudo ./build/xcapture -o /tmp/xcapture_data -F 5 -i 60

# Capture and print kernel stacks
sudo ./build/xcapture -k -s -F 25 -i 100

# Capture HTTP trace context alongside task samples
sudo ./build/xcapture -D http -F 10 -i 30
```

## Command-Line Reference

| Option | Description |
|--------|-------------|
| `-F HZ` | Sampling frequency (default 1 Hz) |
| `-i N` | Stop after `N` iterations |
| `-a` | Include sleeping tasks normally filtered by heuristics |
| `-p PID` | Filter by process/thread-group ID |
| `-t TYPE` | Enable tracking (`syscall`, `iorq`) |
| `-T` | Enable all tracking components |
| `-D MODES` | Enable distributed trace capture (`http`, `https`, `grpc`) |
| `-Y` | Capture read/write payload prefixes for tracked syscalls (experimental; implies `-t syscall`) |
| `-P` | Disable tracking for passive sampling only |
| `-o DIR` | Write CSV files (hourly rotation) into `DIR` |
| `-n` / `-w` | Narrow or wide stdout layouts |
| `-g COLS` | Custom comma-separated column list |
| `-l` | List available columns |
| `-k` / `-u` | Capture kernel / userspace stacks |
| `-s` | Print unique stacks in stdout mode |
| `-N` | Disable stack symbolization even when BlazeSym is available |
| `-C` | Include resolved cgroup paths in stdout |
| `-d PORT` | Daemon port threshold for idle detection (default 10000) |
| `-v` | Emit verbose sampling metrics in CSV mode |

## Output Modes

### Stdout

- Default output surfaces active work; `-n` trims to essentials, `-w` adds namespace and cgroup columns, and `-g` offers bespoke layouts for ad-hoc investigations.
- When `-s` is combined with `-k`/`-u`, xcapture prints symbolized stacks inline; otherwise stacks are referenced by hash only.

### CSV (`-o DIR`)

- Hourly rotated files include:
  - `xcapture_samples_*.csv` (task samples)
  - `xcapture_syscend_*.csv` (syscall completions when tracking is enabled; includes `TRACE_PAYLOAD*` columns when payload capture is active)
  - `xcapture_iorqend_*.csv` (block I/O completions)
  - `xcapture_kstacks_*.csv` / `xcapture_ustacks_*.csv` (stack dictionaries)
  - `xcapture_cgroups_*.csv` (cgroup ID to path mapping when using `-C`)
- Column definitions, value semantics, and JSON payload layouts are documented in `SCHEMA.md`.
- When `--payload-trace` (`-Y`) is active alongside syscall tracking, both task samples and syscall completions surface `TRACE_PAYLOAD` and `TRACE_PAYLOAD_LEN`. Selecting `-D` also records protocol-specific metadata for distributed tracing.

## Stack Output

- Kernel and user stacks are hashed with a 64-bit FNV-1a value in the kernel; hashes appear in the main samples CSV as `KSTACK_HASH` and `USTACK_HASH`.
- Stack dictionary files store one row per unique hash with symbolized frames (semicolon-separated) when BlazeSym is active; empty strings indicate raw addresses only.
- Downstream tools such as xtop or flamegraph generators can join on the hash to reconstruct full call chains.

## Behaviour Highlights

- Passive sampling happens via a sleepable task iterator; ring buffers move task state, completion events, and deduplicated stacks to userspace with zero-copy semantics.
- Idle detection treats READ-class syscalls on ports ≤ `daemon_ports` as server daemons and omits them by default; raise `-d` or pair with `-a` to include them.
- Namespace and cgroup awareness capture PID namespace IDs and cgroup v2 IDs, providing container visibility in wide/custom layouts.
- Distributed trace capture currently copies the first 512 bytes of HTTP request payloads (when `-D http` is selected) into task samples so user space tools can extract tracing context.

## Performance Notes

- Configuration now flows through libbpf skeleton globals, removing hot-path map lookups and keeping per-sample overhead near 340–555 µs depending on enabled features.
- Kernel-side filtering dramatically cuts user-space load: PID filtering or `-a` sampling can reduce per-sample processing by 96–99% compared to unfiltered operation.
- Keep `MAX_STACK_LEN` conservative and avoid deep unrolled loops to stay within verifier limits when modifying probes.

## Testing & Troubleshooting

- Smoke test: `sudo ./build/xcapture -F 10 -i 5`.
- Full suite: `sudo ./test_xcapture.sh` (requires BlazeSym tooling when stacks are enabled).
- Common issues:
  - **Failed to load BPF skeleton** – ensure kernel ≥5.18, BTF availability, and proper capabilities.
  - **No output** – use `-a` or adjust PID filters; confirm the sampling frequency/iteration combination runs long enough to report.
  - **Missing stack symbols** – verify BlazeSym is enabled and Rust/Cargo is installed.
  - **High CPU usage** – lower `-F`, tighten filters, or disable tracking features that are not needed.

## Architecture Snapshot

- eBPF programs: `task/task.bpf.c` performs sampling, `syscall/syscall.bpf.c` and `io/iorq_hashmap.bpf.c` emit completion events linked to sampled operations.
- Helper libraries under `src/helpers/` encapsulate syscall classification, socket parsing, io_uring/libaio accounting, and TCP statistics.
- Userspace (`src/user/`) loads the skeleton, configures globals, polls ring buffers, formats stdout/CSV output, resolves namespaces/cgroups, and performs optional stack symbolization.

## License

This project is licensed under the MIT License; see `LICENSE` for details.
