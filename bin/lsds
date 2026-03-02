#!/usr/bin/env python3

#  lsds - List Disks (block devices) and their metadata
#
#  Copyright 2025 Tanel Poder [https://0x.tools]
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  SPDX-License-Identifier: GPL-2.0-or-later


import os
import sys
import argparse
import re
from pathlib import Path

# --- Constants ---
SYSFS_BASE = "/sys/class/block"
MODULE_BASE = "/sys/module"
SECTOR_SIZE = 512   # Standard sector size used in /sys/class/block/<dev>/size (if unknown)
VALUE_MISSING = "-"  # Default string for missing/inaccessible values
# ignore dm, loop devices and partitions but let /dev/sdp1 and such through
FILTER_REGEX = r"(^dm|^loop|^[a-z]+\d+p\d+$|^[a-z]+\d+n\d+p\d+$)"


# --- Available Columns Mapping ---
# Maps column names (used in CLI) to their corresponding sysfs path fragments
# or special handling functions/keys. Includes 'verbose_source' template.
COLUMN_MAP = {
    # Default Columns
    "DEVNAME": {"source": "devname", "verbose_source": "{dev_path}"},
    "MAJ:MIN": {"source": "file", "path": "dev", "verbose_source": "{dev_path}/dev"},
    "SIZE": {"source": "size", "verbose_source": "{dev_path}/size * {sector_size}"},
    "RO": {"source": "file", "path": "ro", "verbose_source": "{dev_path}/ro"},
    "TYPE": {"source": "type", "verbose_source": "devname, {dev_path}/partition"},
    "SCHED": {"source": "scheduler", "verbose_source": "{dev_path}/queue/scheduler"},
    "NR_RQ": {"source": "file", "path": "queue/nr_requests", "verbose_source": "{dev_path}/queue/nr_requests"},
    "ROT": {"source": "file", "path": "queue/rotational", "verbose_source": "{dev_path}/queue/rotational"},
    "VENDOR": {"source": "file", "path": "device/vendor", "verbose_source": "{dev_path}/device/vendor"},
    "MODEL": {"source": "file", "path": "device/model", "verbose_source": "{dev_path}/device/model"},
    "QDEPTH": {"source": "qdepth", "verbose_source": "{dev_path}/device/queue_depth (N/A for NVMe)"},
    "WCACHE": {"source": "file", "path": "queue/write_cache", "verbose_source": "{dev_path}/queue/write_cache"},
    # Additional Columns
    "WBT_LAT": {"source": "file", "path": "queue/wbt_lat_usec", "verbose_source": "{dev_path}/queue/wbt_lat_usec"},
    "LOGSEC": {"source": "file", "path": "queue/logical_block_size", "verbose_source": "{dev_path}/queue/logical_block_size"},
    "PHYSEC": {"source": "file", "path": "queue/physical_block_size", "verbose_source": "{dev_path}/queue/physical_block_size"},
    "HWSEC": {"source": "file", "path": "queue/hw_sector_size", "verbose_source": "{dev_path}/queue/hw_sector_size"},
    "DISCARD": {"source": "discard", "verbose_source": "{dev_path}/queue/discard_granularity"},
    "DISC_GRAN": {"source": "file", "path": "queue/discard_granularity", "verbose_source": "{dev_path}/queue/discard_granularity"},
    "DISC_MAX": {"source": "file", "path": "queue/discard_max_bytes", "verbose_source": "{dev_path}/queue/discard_max_bytes"},
    "DISC_MAXHW": {"source": "file", "path": "queue/discard_max_hw_bytes", "verbose_source": "{dev_path}/queue/discard_max_hw_bytes"},
    "FUA": {"source": "file", "path": "queue/fua", "verbose_source": "{dev_path}/queue/fua"},
    "DAX": {"source": "file", "path": "queue/dax", "verbose_source": "{dev_path}/queue/dax"},
    "TIMEOUT": {"source": "file", "path": "queue/io_timeout", "verbose_source": "{dev_path}/queue/io_timeout"},
    "INFLIGHT": {"source": "file", "path": "inflight", "verbose_source": "{dev_path}/inflight"},
    "CAP": {"source": "file", "path": "capability", "verbose_source": "{dev_path}/capability"},
    "REMOVABLE": {"source": "file", "path": "removable", "verbose_source": "{dev_path}/removable"},
    "IOPOLL": {"source": "file", "path": "queue/io_poll", "verbose_source": "{dev_path}/queue/io_poll"},
    "IOPOLL_DEL": {"source": "file", "path": "queue/io_poll_delay", "verbose_source": "{dev_path}/queue/io_poll_delay"},
    "RANDOM": {"source": "file", "path": "queue/add_random", "verbose_source": "{dev_path}/queue/add_random"},
    "IOSTATS": {"source": "file", "path": "queue/iostats", "verbose_source": "{dev_path}/queue/iostats"},
    "NVME_QDEPTH": {"source": "nvme_qdepth", "verbose_source": "{module_base}/nvme*/parameters/io_queue_depth"},
    "P2P_QUEUES": {"source": "file", "path": "device/num_p2p_queues", "verbose_source": "{dev_path}/device/num_p2p_queues"},
}

DEFAULT_COLUMNS = [ "DEVNAME", "MAJ:MIN", "SIZE", "TYPE", "SCHED", "ROT", "MODEL", "QDEPTH", "NR_RQ", "WCACHE" ]

# --- Helper Functions ---

def read_sysfs_attr(base_path, attr_path_fragment, default=VALUE_MISSING):
    """
    Safely reads a sysfs attribute file relative to a base path.
    Returns the value read or the default value on failure.
    Also returns the real path accessed and status (found, permission, error, ok).
    """
    value = default
    status = "unknown"
    real_path_accessed = VALUE_MISSING

    if not base_path or not attr_path_fragment:
        return value, real_path_accessed, "no_path"

    full_path = os.path.join(base_path, attr_path_fragment)
    try:
        # Resolve symlinks for accurate path reporting and access checks
        # Use pathlib for potentially easier handling of broken links etc.
        p = Path(full_path)
        if not p.exists():
             # Try resolving link even if target doesn't exist, to show intended path
             if p.is_symlink():
                 real_path_accessed = str(p.resolve()) # May still raise FileNotFoundError if link broken badly
             else:
                 real_path_accessed = str(p.absolute())
             status = "not_found"
             return value, real_path_accessed, status

        # If it exists, get the real path
        real_path_accessed = str(p.resolve())

        # Check readability after resolving
        if not os.access(real_path_accessed, os.R_OK):
            status = "permission"
            return value, real_path_accessed, status

        with open(real_path_accessed, 'r') as f:
            value_read = f.read().strip()
            # Handle potential empty files for some attributes
            value = value_read if value_read else default
            status = "ok"

    except PermissionError:
         status = "permission"
    except FileNotFoundError: # Can happen during resolve if link is broken
         status = "not_found"
         real_path_accessed = str(Path(full_path).absolute()) # Use original path if realpath failed
    except NotADirectoryError: # If intermediate path component is bad
         status = "not_found"
         real_path_accessed = str(Path(full_path).absolute())
    except OSError as e:
        # Catch other potential I/O errors
        # print(f"Debug: OSError reading {full_path} (real: {real_path_accessed}): {e}", file=sys.stderr) # Optional debug
        status = "read_error"
        real_path_accessed = str(Path(full_path).absolute())

    return value, real_path_accessed, status

def read_nvme_module_param(param_name, default=VALUE_MISSING):
    """ Reads an NVMe module parameter, trying both nvme and nvme_core. """
    val = default
    path_tried = VALUE_MISSING
    status = "not_found"
    # Prefer nvme_core if it exists
    for mod_name in ["nvme_core", "nvme"]:
        val, path_tried, status = read_sysfs_attr(MODULE_BASE, f"{mod_name}/parameters/{param_name}", default=default)
        if status == 'ok':
            break # Found it
    return val, path_tried, status


def parse_scheduler(raw_value, default=VALUE_MISSING):
    """
    Extracts the active scheduler name from the bracketed format.
    Example: "none [mq-deadline] kyber" -> "mq-deadline"
    """
    if raw_value == default or not isinstance(raw_value, str):
        return default
    match = re.search(r'\[(\w+(?:-\w+)?)\]', raw_value) # Handle names like mq-deadline
    return match.group(1) if match else raw_value # Fallback to raw if no brackets

def human_readable_size(size_bytes, default=VALUE_MISSING):
    """Converts size in bytes to human-readable format (GiB)."""
    if not isinstance(size_bytes, (int, float)) or size_bytes < 0:
        return default
    if size_bytes == 0:
        return "0.0 GiB"
    # Power of 1024 for GiB
    power = 3
    unit = "GiB"
    size_converted = size_bytes / (1024 ** power)
    return f"{size_converted:.1f} {unit}"

def infer_device_type(device_name, dev_path):
    """
    Infers the device type based on naming conventions and sysfs structure.
    """
    if device_name.startswith("loop"):
        return "Loop"
    if device_name.startswith("dm-"):
        return "DM"

    # Check for partition file first - most reliable for partitions
    partition_file = os.path.join(dev_path, "partition")
    if os.path.exists(partition_file):
        if device_name.startswith("nvme"):
            return "NVMePart"
        else:
            return "Part" # Generic partition

    # If no partition file, infer based on name
    if device_name.startswith("nvme"):
        if re.match(r'^nvme\d+n\d+$', device_name):
            return "NVMeDisk"
        else:
            return "NVMeDev" # Other NVMe device? Less common.

    if device_name.startswith("sd") or device_name.startswith("hd") or device_name.startswith("vd"):
        if re.match(r'^[svh]d[a-z]+$', device_name):
            return "Disk" # SCSI/SATA/IDE/VirtIO disk

    # Fallback for unknown types
    return "BlockDev"


def get_discard_info(device, dev_path):
    """ Checks if discard (TRIM/UNMAP) seems supported. Returns value and status dict. """
    value = "False"
    status_details = {'granularity_status': 'unknown', 'max_bytes_status': 'unknown'}
    dev_base_path = os.path.join(SYSFS_BASE, device)

    granularity, _, status_g = read_sysfs_attr(dev_base_path, "queue/discard_granularity", default='0')
    max_bytes, _, status_m = read_sysfs_attr(dev_base_path, "queue/discard_max_bytes", default='0')
    status_details['granularity_status'] = status_g
    status_details['max_bytes_status'] = status_m

    try:
        if int(granularity) > 0 and int(max_bytes) > 0:
            value = "True"
    except ValueError:
        pass # Keep value as "False"

    # Determine overall status - prefer showing error if any occurred
    final_status = "ok"
    if status_g!= 'ok' or status_m!= 'ok':
        if 'permission' in [status_g, status_m]:
            final_status = 'permission'
        elif 'not_found' in [status_g, status_m]:
             final_status = 'not_found'
        else:
             final_status = 'read_error' # Or other error

    return value, final_status


def get_qdepth_info(device, dev_path, device_type):
    """ Gets queue depth, handling SCSI vs NVMe differences. Returns value and status. """
    # NVMe devices use blk-mq and don't have a single 'queue_depth' like SCSI.
    if device_type.startswith("NVMe"):
        return VALUE_MISSING, "ok" # It's expected to be N/A for NVMe

    dev_base_path = os.path.join(SYSFS_BASE, device)
    # For SCSI/SATA/SAS, check the standard location first
    qdepth, real_path, status = read_sysfs_attr(dev_base_path, "device/queue_depth", default=VALUE_MISSING)

    # If not found there, try the scsi_device symlink path as a fallback
    if status == "not_found":
        scsi_device_path = os.path.join(dev_path, "device/scsi_device")
        if os.path.islink(scsi_device_path):
            try:
                real_scsi_path = os.path.realpath(scsi_device_path)
                qdepth_path = os.path.join(real_scsi_path, "queue_depth")

                if not os.path.exists(qdepth_path):
                     status = "not_found"
                elif not os.access(qdepth_path, os.R_OK):
                     status = "permission"
                else:
                    with open(qdepth_path, 'r') as f:
                        qdepth = f.read().strip()
                        status = "ok"

            except (FileNotFoundError, PermissionError, OSError):
                # If fallback fails, keep original status (not_found) or update if permission issue
                if isinstance(sys.exc_info()[1], PermissionError):
                    status = "permission"
                # Keep qdepth as default missing value

    return qdepth, status


# --- Core Logic Functions ---

# def get_block_devices():
#     """Scans /sys/class/block/ for block device names."""
#     try:
#         devices = sorted(os.listdir(SYSFS_BASE))
#         return devices
#     except FileNotFoundError:
#         print(f"Error: Sysfs block device directory not found at {SYSFS_BASE}", file=sys.stderr)
#         sys.exit(1)
#     except OSError as e:
#         print(f"Error: Could not list block devices in {SYSFS_BASE}: {e}", file=sys.stderr)
#         sys.exit(1)

import os
import sys
import re

SYSFS_BASE = "/sys/class/block"

def get_block_devices(filter_pattern=None):
    """
    Scans /sys/class/block/ for block device names.

    Args:
        filter_pattern (str, optional): A regex pattern to filter device names.
            If None, defaults to filtering out devices starting with "dm" or "loop",
            and any partition devices (ending with pN).

    Returns:
        list: Sorted list of block device names that pass the filter.
    """
    try:
        devices = sorted(os.listdir(SYSFS_BASE))

        # Exclude dm-*, loop*, and any partition (ending with pN)
        if filter_pattern is None:
            filter_pattern = FILTER_REGEX

        pattern = re.compile(filter_pattern)
        filtered_devices = [dev for dev in devices if not pattern.match(dev)]

        return filtered_devices
    except FileNotFoundError:
        print(f"Error: Sysfs block device directory not found at {SYSFS_BASE}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"Error: Could not list block devices in {SYSFS_BASE}: {e}", file=sys.stderr)
        sys.exit(1)

def get_device_info(device, columns_to_get):
    """
    Gathers the requested information for a single block device.
    Returns a dictionary where keys are column names and values are
    sub-dictionaries {'value':..., 'source':..., 'status':...}.
    """
    dev_path = os.path.join(SYSFS_BASE, device)
    info = {}

    # --- Pre-calculate some values needed by multiple columns ---
    device_type = infer_device_type(device, dev_path)

    # --- Populate info dictionary based on requested columns ---
    for col in columns_to_get:
        value = VALUE_MISSING
        source_description = VALUE_MISSING
        status = "unknown" # ok, not_found, permission, read_error, inferred, calculated

        if col not in COLUMN_MAP:
            value = "InvalidCol"
            source_description = "Internal Error"
            status = "error"
        else:
            device_info = COLUMN_MAP[col]
            source_type = device_info["source"]
            raw_source_tmpl = device_info.get("verbose_source", "Unknown Source")

            # Format the basic source template (will be updated for file sources)
            source_description = raw_source_tmpl.format(
                dev_path=dev_path, sysfs_base=SYSFS_BASE, module_base=MODULE_BASE,
                device=device, sector_size=SECTOR_SIZE
            )

            # --- Get value based on source type ---
            if source_type == "devname":
                value = device
                status = "ok" # Always available
            elif source_type == "type":
                value = device_type
                status = "inferred"
            elif source_type == "size":
                raw_size, real_path, read_status = read_sysfs_attr(dev_path, "size", default='0')
                status = read_status
                if args.realpath:
                    source_description = real_path # Update source path
                if status == 'ok':
                    try:
                        size_bytes = int(raw_size) * SECTOR_SIZE
                        value = human_readable_size(size_bytes, default=VALUE_MISSING)
                        status = "calculated" if value!= VALUE_MISSING else "error"
                    except ValueError:
                        value = VALUE_MISSING
                        status = "error" # Error during calculation
            elif source_type == "scheduler":
                raw_sched, real_path, read_status = read_sysfs_attr(dev_path, "queue/scheduler", default=VALUE_MISSING)
                status = read_status
                if args.realpath:
                    source_description = real_path
                if status == 'ok':
                    value = parse_scheduler(raw_sched, default=VALUE_MISSING)
                    status = "parsed" # Indicate parsing happened
            elif source_type == "qdepth":
                 value, status = get_qdepth_info(device, dev_path, device_type)
                 # Status from get_qdepth_info is already ok, permission, not_found etc.
                 # Source description is complex, keep template for now
            elif source_type == "discard":
                value, status = get_discard_info(device, dev_path)
                status = "inferred" if status == 'ok' else status # Mark as inferred if checks passed
            elif source_type == "nvme_qdepth":
                 if device_type.startswith("NVMe"):
                     value, real_path, status = read_nvme_module_param("io_queue_depth", default=VALUE_MISSING)
                     if args.realpath:
                         source_description = real_path if real_path!= VALUE_MISSING else source_description
                 else:
                     value = VALUE_MISSING # Not applicable
                     status = "ok" # Not an error, just not applicable
                     source_description = "N/A (Not NVMe)"
            elif source_type == "file":
                value, real_path, status = read_sysfs_attr(dev_path, device_info["path"], default=VALUE_MISSING)
                # Update source description with the actual path tried
                if args.realpath:
                    source_description = real_path
            else:
                value = VALUE_MISSING # Fallback for unhandled types
                status = "error"

            # Add status suffix to source description for non-ok cases in verbose mode
            if status not in ['ok', 'inferred', 'calculated', 'parsed']:
                 source_description += f" ({status.replace('_', ' ').title()})"


        info[col] = {'value': value, 'source': source_description, 'status': status}

    return info


# --- Argument Parsing ---

def parse_arguments():
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(
        description="lsds: List Linux block devices v1.0.0 by Tanel Poder [0x.tools]",
        epilog="Reads data directly from sysfs, does not execute external commands."
    )
    parser.add_argument(
        "-c", "--columns",
        nargs='+',
        metavar="COLUMN",
        # Default is handled later based on whether --add is used
        help=f"Specify which columns to display. Overrides defaults. Default: {' '.join(DEFAULT_COLUMNS)}"
    )
    parser.add_argument(
        "-a", "--add",
        metavar='COL1,COL2,...',
        help="Comma-separated list of columns to add to the default list."
    )
    parser.add_argument(
        "-l", "--list",
        action="store_true",
        help="List all available column names and exit."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show the source file path or derivation for each value."
    )
    parser.add_argument(
        "-p", "--pivot",
        action="store_true",
        help="Pivot output: print each device/column value on a separate line."
    )
    parser.add_argument(
        "-r", "--realpath",
        action="store_true",
        help="Show /sys source file real path instead of symlink."
    )

    return parser.parse_args()

# --- Output Formatting ---

def print_tabular_output(devices_info, columns, verbose=False):
    """Formats and prints the collected data in a standard table."""
    if not devices_info:
        print("No block devices found or accessible.")
        return

    # Prepare data for display (value or value + source)
    display_data = []
    for info in devices_info:
        row_data = {}
        for col in columns:
            cell_info = info.get(col, {'value': VALUE_MISSING, 'source': VALUE_MISSING, 'status': 'error'})
            value = cell_info['value']
            source = cell_info['source']

            if verbose:
                # In verbose mode, always show value and source
                if col == "DEVNAME":
                     display_val = str(value)
                else:
                     display_val = f"{value} ({source})"
            else:
                # Non-verbose, just show the value
                display_val = str(value)
            row_data[col] = display_val
        display_data.append(row_data)


    # Calculate column widths based on the display strings
    widths = {col: len(col) for col in columns}
    for row in display_data:
        for col in columns:
            widths[col] = max(widths[col], len(row.get(col, '')))

    # Print header
    header = "  ".join(f"{col:<{widths[col]}}" for col in columns)
    print(header)
    # print("-" * len(header)) # Optional separator

    # Print data rows
    for row in display_data:
        row_str = "  ".join(f"{row.get(col, VALUE_MISSING):<{widths[col]}}" for col in columns)
        print(row_str)
    if sys.stdout.isatty() or args.pivot:
        print()

def print_pivoted_output(devices_info, columns, verbose=False):
    """Formats and prints the collected data in pivoted format."""
    if not devices_info:
        print("No block devices found or accessible.")
        return

    print("DEVNAME      NAME         VALUE") # Header for pivoted output

    for device_info in devices_info:
        devname_info = device_info.get("DEVNAME", {'value': VALUE_MISSING})
        devname = devname_info['value']
        if devname == VALUE_MISSING:
            continue # Skip if we couldn't even get the device name

        for col in columns:
            if col == "DEVNAME": # Don't print DEVNAME as a separate row
                continue

            cell_info = device_info.get(col, {'value': VALUE_MISSING})
            value = cell_info['value']
            source = cell_info['source']

            if verbose:
                print(f"{devname:12} {col:12} {value:25} {source}")
            else:
                print(f"{devname:12} {col:12} {value}")

        print("")


if __name__ == "__main__":
    args = parse_arguments()

    available_columns = list(COLUMN_MAP.keys())

    # List available columns
    if args.list:
        # side by side in a terminal, otherwise one item per line
        col_width = max(len(c) for c in available_columns) + 2
        if sys.stdout.isatty() and not args.pivot:
            num_cols = max(1, os.get_terminal_size().columns // col_width)
        else:
            num_cols = 1

        for i, col_name in enumerate(sorted(available_columns)):
            if args.verbose and args.pivot:
                col_source = COLUMN_MAP[col_name].get("verbose_source", "Source not found")

                try:
                    formatted_source = col_source.format(**COLUMN_MAP[col_name])
                except KeyError as e:
                    formatted_source = col_source

                print(f"{col_name:{col_width}} {col_source}", end="")
            else:     
                print(f"{col_name:{col_width}}", end="")

            if (i + 1) % num_cols == 0:
                print()
        if len(available_columns) % num_cols!= 0:
            print()

        print()
        sys.exit(0)

    # Determine the list of columns to display
    if args.columns:
        # If --columns is specified, it overrides defaults and --add
        selected_columns = args.columns
        if args.add:
             print("Warning: --add ignored because --columns was specified.", file=sys.stderr)
    elif args.add:
        # Start with default and add specified columns
        selected_columns = list(DEFAULT_COLUMNS) # Make a copy
        added_cols_str = args.add.split(',')
        added_cols = [c.strip() for c in added_cols_str if c.strip()]

        # Validate added columns
        invalid_added = [c for c in added_cols if c not in available_columns]
        if invalid_added:
            print(f"Error: Invalid column(s) specified in --add: {', '.join(invalid_added)}", file=sys.stderr)
            print(f"Use --list to see available columns.", file=sys.stderr)
            sys.exit(1)

        # Add valid new columns, maintaining order somewhat
        for col in added_cols:
            if col not in selected_columns:
                selected_columns.append(col)
    else:
        # Default case
        selected_columns = list(DEFAULT_COLUMNS)


    # Final validation of the selected columns list
    invalid_columns = [col for col in selected_columns if col not in available_columns]
    if invalid_columns:
        # This case should ideally only happen if --columns had invalid ones
        print(f"Error: Invalid column(s) selected: {', '.join(invalid_columns)}", file=sys.stderr)
        print(f"Use --list to see available columns.", file=sys.stderr)
        sys.exit(1)

    # Ensure DEVNAME is always the first column if pivoting, for clarity
    if args.pivot and "DEVNAME" in selected_columns:
         selected_columns.remove("DEVNAME")
         selected_columns.insert(0, "DEVNAME")
    elif args.pivot and "DEVNAME" not in selected_columns:
         # Need DEVNAME for pivoted output format
         selected_columns.insert(0, "DEVNAME")


    block_devices = get_block_devices()

    all_device_data = []
    for device in block_devices:
        # Pass selected columns to get_device_info
        device_data = get_device_info(device, selected_columns)
        all_device_data.append(device_data)

    # Decide which output function to call
    if args.pivot:
        print_pivoted_output(all_device_data, selected_columns, args.verbose)
    else:
        # Pass verbose flag to standard tabular output
        print_tabular_output(all_device_data, selected_columns, args.verbose)

# end
