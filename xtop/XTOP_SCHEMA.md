# XTOP Schema Documentation

This document describes the CSV data sources used by xtop queries, their relationships, and how the dynamic query system intelligently joins them.

## Primary Data Source

The `xcapture_samples_*.csv` files are the core data source that drives all xtop reports. All other data sources enrich this primary data through LEFT OUTER JOINs.

## Data Sources Overview

| Data Source | File Pattern | Description | Independence | JOIN CONDITIONS |
|-------------|--------------|-------------|--------------|-----------------|
| **Samples** | `xcapture_samples_*.csv` | Core task state sampling data with timestamps, process info, syscalls, filenames | **Independent** - Primary fact table | N/A - This is the base table |
| **System Call Completions** | `xcapture_syscend_*.csv` | System call completion events with duration measurements | Requires join to samples | `LEFT OUTER JOIN xcapture_syscend_*.csv sc ON samples.tid = sc.tid AND samples.sysc_seq_num = sc.sysc_seq_num` |
| **I/O Request Completions** | `xcapture_iorqend_*.csv` | Block I/O request completions with timing, bytes, device info | Requires join to samples | `LEFT OUTER JOIN xcapture_iorqend_*.csv io ON samples.tid = io.insert_tid AND samples.iorq_seq_num = io.iorq_seq_num` |
| **Kernel Stack Traces** | `xcapture_kstacks_*.csv` | Kernel stack trace symbols with hash mapping | Requires join to samples | `LEFT OUTER JOIN xcapture_kstacks_*.csv ks ON samples.kstack_hash = ks.stack_hash` |
| **Userspace Stack Traces** | `xcapture_ustacks_*.csv` | Userspace stack trace symbols with hash mapping | Requires join to samples | `LEFT OUTER JOIN xcapture_ustacks_*.csv us ON samples.ustack_hash = us.stack_hash` |
| **Block Device Metadata** | `/proc/partitions` | Maps device major/minor numbers to device names | External metadata | `LEFT OUTER JOIN partitions part ON io.dev_maj = part.dev_maj AND io.dev_min = part.dev_min` |

## Key Fields for Joining

### xcapture_samples_*.csv (Base Table)
Core columns always available:
- `tid` - Thread ID
- `pid` - Process ID
- `comm` - Command name
- `state` - Process state (R, S, D, etc.)
- `username` - User running the process
- `exe` - Executable path
- `syscall` - Current system call
- `filename` - File being accessed
- `extra_info` - Additional context (JSON)
- `timestamp` - Sample timestamp
- `sysc_seq_num` - System call sequence number
- `iorq_seq_num` - I/O request sequence number  
- `kstack_hash` - Kernel stack trace MD5 hash
- `ustack_hash` - Userspace stack trace MD5 hash

### Enrichment Data Sources

**xcapture_syscend_*.csv**:
- `tid` - Thread ID (join key)
- `sysc_seq_num` - System call sequence number (join key)
- `duration_ns` - System call duration in nanoseconds

**xcapture_iorqend_*.csv**:
- `insert_tid` - Thread ID that initiated I/O (join key)
- `iorq_seq_num` - I/O request sequence number (join key)
- `duration_ns` - Total I/O duration
- `service_ns` - Device service time
- `queued_ns` - Queue wait time
- `dev_maj`, `dev_min` - Device major/minor numbers
- `bytes` - Bytes transferred

**xcapture_kstacks_*.csv** and **xcapture_ustacks_*.csv**:
- `stack_hash` - MD5 hash of stack trace (join key)
- `stack_syms` - Semicolon-separated function symbols with offsets

## Computed Columns

The dynamic query system can generate these computed columns on-the-fly:

| Column | Description | Computation |
|--------|-------------|-------------|
| `FILENAMESUM` | Filename with numbers replaced by wildcards | `REGEXP_REPLACE(filename, '[0-9]+', '*', 'g')` |
| `FEXT` | File extension | Extracted from filename |
| `COMM2` | Normalized command name | Numbers replaced with `*` |
| `KSTACK_CURRENT_FUNC` | Top function in kernel stack | `SPLIT_PART(kstack_syms, ';', 1)` |
| `USTACK_CURRENT_FUNC` | Top function in user stack | `SPLIT_PART(ustack_syms, ';', 1)` |
| `CONNECTION` | Connection info from extra_info | JSON extraction |

## Dynamic Query System

The dynamic query builder (`query_engine.py`) automatically:

1. **Analyzes requested columns** to determine required data sources
2. **Builds minimal JOINs** - only includes necessary data sources
3. **Handles computed columns** - generates them in SELECT or CTE as needed
4. **Optimizes aggregations** - builds histograms efficiently with CTEs
5. **Manages aliases** - handles column name conflicts across sources

### Example: Dynamic JOIN Detection

When user requests `KSTACK_HASH` in GROUP BY:
```sql
-- System automatically adds:
LEFT OUTER JOIN (
    SELECT DISTINCT
        STACK_HASH AS KSTACK_HASH,
        STACK_SYMS AS KSTACK_SYMS
    FROM read_csv_auto('xcapture_kstacks_*.csv')
) ks ON samples.kstack_hash = ks.kstack_hash
```

When user requests system call latency columns:
```sql
-- System automatically adds:
LEFT OUTER JOIN read_csv_auto('xcapture_syscend_*.csv') sc
    ON samples.tid = sc.tid 
    AND samples.sysc_seq_num = sc.sysc_seq_num
```

## Query Patterns (Legacy)

| SQL File | Data Sources Used | Purpose | Status |
|----------|-------------------|---------|--------|
| `top.sql` | samples only | Basic task state analysis | Legacy |
| `summary.sql` | samples only | Aggregated system activity | Legacy |
| `topstacks.sql` | samples + kstacks + ustacks | Stack trace analysis | Legacy |
| `sclat.sql` | samples + syscend | System call latency | Legacy |
| `sclathist.sql` | samples + syscend | System call latency histogram | Legacy |
| `iolat.sql` | samples + iorqend + partitions | I/O latency with device names | Legacy |
| `iolathist.sql` | samples + iorqend + partitions | I/O latency histogram | Legacy |
| **dynamic** | Automatic based on columns | Intelligent query building | **Primary** |

## Important Implementation Notes

1. **Always use LEFT OUTER JOINs** to preserve all sample records
2. **Column name handling**:
   - The samples table uses `tid` for joins
   - The iorqend table uses `insert_tid` for joins
   - Stack columns may appear in multiple sources (handled by aliasing)
3. **Performance optimizations**:
   - Stack traces are deduplicated using MD5 hashes
   - Histograms use pre-aggregation in CTEs
   - Only required JOINs are performed
4. **Data availability**:
   - All timestamp fields are in the samples table
   - Enrichment tables only contain duration/latency data
   - Device names come from `/proc/partitions` snapshot

## Column Availability by Source

| Source | Key Columns | When Included |
|--------|-------------|---------------|
| samples | All base columns | Always |
| syscend | duration_ns, latency metrics | When syscall latency columns requested |
| iorqend | I/O duration, bytes, device info | When I/O latency columns requested |
| kstacks | Kernel stack symbols | When KSTACK_* columns requested |
| ustacks | User stack symbols | When USTACK_* columns requested |
| partitions | Device names | When DEVNAME requested with I/O data |

## Error Handling

The dynamic query system handles missing data gracefully:
- Missing CSV files are skipped silently
- NULL values propagate correctly through JOINs
- Computed columns default to '-' or appropriate empty values
- Query errors display in modal popups (TUI) or stderr (CLI)