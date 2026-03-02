# IDLE Thread Determination in xcapture

This document explains how xcapture distinguishes between IDLE daemon threads and active client threads using the daemon_ports heuristic.

## Overview

xcapture uses a port-based heuristic to classify threads that appear as "SLEEPING" (TASK_INTERRUPTIBLE) at the kernel level but have different semantic meanings:
- **IDLE threads**: Server daemons waiting for incoming connections
- **ACTIVE threads**: Client threads waiting for RPC/network responses

## The Daemon Ports Logic

### Core Implementation

The logic is implemented in `src/probes/task/task.bpf.c` in the `should_emit_task()` function:

```c
if (task_state & TASK_INTERRUPTIBLE) {
    // Check daemon port logic for READ operations on TCP/UDP sockets
    if (read_local_port_num > 0 && is_read_syscall(syscall_nr)) {
        if (read_local_port_num <= cfg->daemon_ports) {
            // This is a daemon waiting for work - skip it
            return false;
        }
        // else: local_port > daemon_ports, this is an active client - include it
        return true;
    }
    // Not a READ operation on a socket, filter out sleeping task
    return false;
}
```

### Classification Rules

1. **Thread State**: Only applies to threads in TASK_INTERRUPTIBLE (sleeping) state
2. **Syscall Type**: Only checks threads in READ-type syscalls (read, recv*, poll, epoll_wait, etc.)
3. **Port Comparison**:
   - **Local port ≤ daemon_ports threshold** → IDLE daemon (filtered out by default)
   - **Local port > daemon_ports threshold** → Active client (shown)

### Default Configuration

- **Threshold**: 10000 (defined in `src/user/main.c:51`)
- **Command-line option**: `-d PORT` or `--daemon-ports PORT`
- **Configuration struct**: `filter_config.daemon_ports` in `include/xcapture.h:214`

## Why This Heuristic Works

### Port Number Conventions

1. **Well-known service ports (< 10000)**:
   - HTTP: 80
   - HTTPS: 443
   - SSH: 22
   - MySQL: 3306
   - PostgreSQL: 5432
   - Redis: 6379
   - Most standard services

2. **Ephemeral/dynamic ports (> 10000)**:
   - Typically 32768-65535 on Linux
   - Used by client applications for outgoing connections
   - Assigned dynamically by the OS

### Practical Examples

**IDLE (filtered out):**
- Apache/Nginx worker thread listening on port 80
- MySQL thread waiting for connections on port 3306
- SSH daemon on port 22

**ACTIVE (shown):**
- Application thread waiting for database query response (local port 45678)
- HTTP client waiting for API response (local port 52341)
- RPC client waiting for remote procedure result (local port 38902)

## Technical Details

### Port Extraction

The local port is extracted from socket information in the eBPF probe:
1. Checks if the file descriptor is a socket
2. Reads the `inet_sport` field from the socket structure
3. Converts from network byte order using `bpf_ntohs()`
4. Stores in `read_local_port_num` for the heuristic check

### Integration with Filtering

The daemon_ports logic integrates with xcapture's overall filtering system:
- When `-a` (show all) is specified, the daemon_ports logic is bypassed
- The logic only applies when filtering is active (default behavior)
- Other task states (RUNNING, UNINTERRUPTIBLE, etc.) are not affected

## Limitations and Considerations

1. **Heuristic Nature**: This is a heuristic that works well in practice but may need adjustment for non-standard environments
2. **Custom Port Ranges**: Some environments may use different port conventions
3. **Non-socket Sleeps**: Threads sleeping on non-socket operations are filtered regardless of this logic
4. **Protocol Agnostic**: Applies to both TCP and UDP sockets

## Tuning Guidelines

Adjust the daemon_ports threshold if:
- Your services run on high-numbered ports
- Your environment uses non-standard port ranges
- You want to see specific daemon threads

Example: `./xcapture -d 20000` to include daemons up to port 20000