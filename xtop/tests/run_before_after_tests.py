#!/usr/bin/env python3
"""
Comprehensive before/after testing script for XTOP.
Captures actual application data output for comparison.
"""

import subprocess
import os
import sys
from pathlib import Path
import json
import hashlib
from datetime import datetime

# Test configuration
DATADIR = "../out"
FROM_TIME = "2025-08-03T03:40:00"
TO_TIME = "2025-08-03T04:07:00"

# All test cases (basic + extended)
TEST_CASES = [
    # Basic tests
    {
        "name": "01_basic_dynamic",
        "description": "Basic dynamic query",
        "group": "",
        "latency": "",
        "where": ""
    },
    {
        "name": "02_group_by_state_user_comm",
        "description": "Dynamic with custom GROUP BY",
        "group": "STATE,USERNAME,COMM",
        "latency": "",
        "where": ""
    },
    {
        "name": "03_computed_columns",
        "description": "Dynamic with computed columns",
        "group": "STATE,FILENAMESUM,COMM2",
        "latency": "",
        "where": ""
    },
    {
        "name": "04_syscall_latency",
        "description": "Dynamic with syscall latency percentiles",
        "group": "STATE,SYSCALL",
        "latency": "sc.min_lat_us,sc.avg_lat_us,sc.p95_us",
        "where": ""
    },
    {
        "name": "05_io_latency",
        "description": "Dynamic with I/O latency percentiles",
        "group": "STATE,EXE",
        "latency": "io.min_lat_us,io.avg_lat_us,io.max_lat_us",
        "where": ""
    },
    {
        "name": "06_syscall_histogram",
        "description": "Dynamic with syscall latency histogram",
        "group": "STATE,SYSCALL",
        "latency": "SCLAT_HISTOGRAM",
        "where": ""
    },
    {
        "name": "07_kernel_stacks",
        "description": "Dynamic with kernel stack traces",
        "group": "STATE,KSTACK_CURRENT_FUNC,KSTACK_HASH",
        "latency": "",
        "where": ""
    },
    {
        "name": "08_both_stacks",
        "description": "Dynamic with both kernel and user stacks",
        "group": "STATE,KSTACK_CURRENT_FUNC,USTACK_CURRENT_FUNC",
        "latency": "",
        "where": ""
    },
    {
        "name": "09_with_where",
        "description": "Dynamic with WHERE clause",
        "group": "STATE,COMM",
        "latency": "",
        "where": "STATE = 'Running' OR STATE = 'R'"
    },
    {
        "name": "10_complex_multi",
        "description": "Complex query with multiple features",
        "group": "STATE,USERNAME,COMM2,KSTACK_CURRENT_FUNC",
        "latency": "sc.p95_us,SCLAT_HISTOGRAM",
        "where": ""
    },
    
    # Extended tests
    {
        "name": "11_username_exe_histogram",
        "description": "Username + EXE with syscall histogram",
        "group": "USERNAME,EXE",
        "latency": "SCLAT_HISTOGRAM,sc.p50_us,sc.p99_us",
        "where": ""
    },
    {
        "name": "12_filename_io_histogram",
        "description": "State + Filename patterns with I/O histogram",
        "group": "STATE,FILENAMESUM,FEXT",
        "latency": "IOLAT_HISTOGRAM,io.p95_us",
        "where": ""
    },
    {
        "name": "13_kstack_syscall_latency",
        "description": "Kernel stacks with syscall latency",
        "group": "KSTACK_CURRENT_FUNC,SYSCALL",
        "latency": "sc.min_lat_us,sc.avg_lat_us,sc.max_lat_us,sc.p999_us",
        "where": ""
    },
    {
        "name": "14_ustack_dual_histograms",
        "description": "User stacks with dual histograms",
        "group": "USTACK_CURRENT_FUNC,COMM",
        "latency": "SCLAT_HISTOGRAM,IOLAT_HISTOGRAM",
        "where": ""
    },
    {
        "name": "15_combined_stacks",
        "description": "Combined kernel and user stacks",
        "group": "KSTACK_HASH,USTACK_HASH,STATE",
        "latency": "sc.p50_us,sc.p95_us,io.p50_us,io.p95_us",
        "where": ""
    },
    {
        "name": "16_device_io_analysis",
        "description": "Device analysis with I/O metrics",
        "group": "devname,STATE,EXE",
        "latency": "io.min_lat_us,io.avg_lat_us,io.max_lat_us,IOLAT_HISTOGRAM",
        "where": ""
    },
    {
        "name": "17_connection_analysis",
        "description": "Connection info with syscall histogram",
        "group": "CONNECTION,USERNAME,COMM",
        "latency": "SCLAT_HISTOGRAM,sc.p95_us",
        "where": ""
    },
    {
        "name": "18_stack_hash_percentiles",
        "description": "Stack hashes with percentiles",
        "group": "KSTACK_HASH,SYSCALL",
        "latency": "sc.p50_us,sc.p75_us,sc.p90_us,sc.p95_us,sc.p99_us,sc.p999_us",
        "where": ""
    },
    {
        "name": "19_full_stack_files",
        "description": "Full stack with file patterns",
        "group": "KSTACK_CURRENT_FUNC,USTACK_CURRENT_FUNC,FILENAMESUM",
        "latency": "sc.avg_lat_us,io.avg_lat_us",
        "where": ""
    },
    {
        "name": "20_complex_grouping",
        "description": "Complex multi-dimensional grouping",
        "group": "STATE,USERNAME,EXE,COMM2,SYSCALL,FILENAME,KSTACK_CURRENT_FUNC",
        "latency": "sc.p95_us,io.p95_us,SCLAT_HISTOGRAM",
        "where": ""
    },
    {
        "name": "21_filtered_stacks",
        "description": "Filtered query with stacks",
        "group": "KSTACK_CURRENT_FUNC,COMM",
        "latency": "sc.p99_us",
        "where": "USERNAME = 'root'"
    },
    {
        "name": "22_all_computed",
        "description": "All computed columns",
        "group": "FILENAMESUM,FEXT,COMM2,CONNECTION",
        "latency": "",
        "where": ""
    }
]


def run_single_test(test_case, output_dir):
    """Run a single test and save output"""
    output_file = Path(output_dir) / f"{test_case['name']}.txt"
    
    # Build command
    cmd = [
        "python3", "../xtop-test.py",
        "-d", DATADIR,
        "-q", "dynamic",
        "--from", FROM_TIME,
        "--to", TO_TIME,
        "--limit", "10",
        "--format", "simple",
        "--duckdb-threads", "1"  # Use single thread for deterministic results
    ]
    
    if test_case["group"]:
        cmd.extend(["-g", test_case["group"]])
    
    if test_case["latency"]:
        cmd.extend(["-l", test_case["latency"]])
    
    if test_case["where"]:
        cmd.extend(["-w", test_case["where"]])
    
    # Run command and capture output
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Extract only the data output (remove log lines)
        lines = result.stdout.split('\n')
        data_lines = []
        in_data_section = False
        
        for line in lines:
            # Skip log lines (they contain timestamps)
            if line.startswith('2025-') and ' - INFO - ' in line:
                continue
            if line.startswith('2025-') and ' - DEBUG - ' in line:
                continue
            if line.startswith('2025-') and ' - ERROR - ' in line:
                continue
                
            # Start capturing after "MAIN QUERY RESULTS"
            if "=== MAIN QUERY RESULTS ===" in line:
                in_data_section = True
                data_lines.append(line)
            elif in_data_section:
                # Skip the timing line (e.g., "Rows: 10, Time: 0.257s")
                if line.startswith("Rows:") and "Time:" in line:
                    # Replace with a normalized version without timing
                    parts = line.split(',')
                    row_part = parts[0].strip()  # "Rows: 10"
                    data_lines.append(row_part)  # Only keep row count
                else:
                    data_lines.append(line)
        
        # Write data output to file
        with open(output_file, 'w') as f:
            f.write('\n'.join(data_lines))
        
        # Also save stderr if there were errors
        if result.stderr:
            error_file = Path(output_dir) / f"{test_case['name']}_error.txt"
            with open(error_file, 'w') as f:
                f.write(result.stderr)
        
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print(f"  ✗ Test timed out")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def calculate_file_hash(filepath):
    """Calculate MD5 hash of file content"""
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def run_all_tests(output_dir):
    """Run all tests and save outputs"""
    print(f"\nRunning tests - Output directory: {output_dir}")
    print("=" * 60)
    
    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    results = []
    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"\n[{i}/{len(TEST_CASES)}] {test_case['description']}")
        print(f"  Test: {test_case['name']}")
        
        success = run_single_test(test_case, output_dir)
        results.append({
            "name": test_case["name"],
            "description": test_case["description"],
            "success": success
        })
        
        if success:
            print(f"  ✓ Test completed")
        else:
            print(f"  ✗ Test failed")
    
    # Save test summary
    summary_file = Path(output_dir) / "test_summary.json"
    with open(summary_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(TEST_CASES),
            "passed": sum(1 for r in results if r["success"]),
            "failed": sum(1 for r in results if not r["success"]),
            "results": results
        }, f, indent=2)
    
    return results


def compare_outputs(before_dir, after_dir):
    """Compare before and after outputs"""
    print("\n" + "=" * 60)
    print("Comparing before/after outputs")
    print("=" * 60)
    
    before_path = Path(before_dir)
    after_path = Path(after_dir)
    
    differences = []
    identical = []
    
    for test_case in TEST_CASES:
        test_name = test_case["name"]
        before_file = before_path / f"{test_name}.txt"
        after_file = after_path / f"{test_name}.txt"
        
        if not before_file.exists():
            differences.append(f"{test_name}: Before file missing")
            continue
        
        if not after_file.exists():
            differences.append(f"{test_name}: After file missing")
            continue
        
        # Compare file hashes
        before_hash = calculate_file_hash(before_file)
        after_hash = calculate_file_hash(after_file)
        
        if before_hash == after_hash:
            identical.append(test_name)
        else:
            differences.append(f"{test_name}: Output differs")
            
            # Show first difference
            with open(before_file, 'r') as f:
                before_lines = f.readlines()
            with open(after_file, 'r') as f:
                after_lines = f.readlines()
            
            for i, (b_line, a_line) in enumerate(zip(before_lines, after_lines)):
                if b_line != a_line:
                    print(f"\n  First difference in {test_name} at line {i+1}:")
                    print(f"    Before: {b_line.rstrip()}")
                    print(f"    After:  {a_line.rstrip()}")
                    break
    
    # Print summary
    print(f"\n{'Summary':=^60}")
    print(f"Identical outputs: {len(identical)}/{len(TEST_CASES)}")
    print(f"Different outputs: {len(differences)}/{len(TEST_CASES)}")
    
    if identical:
        print(f"\n✓ Tests with identical output ({len(identical)}):")
        for test in identical[:5]:  # Show first 5
            print(f"  - {test}")
        if len(identical) > 5:
            print(f"  ... and {len(identical)-5} more")
    
    if differences:
        print(f"\n✗ Tests with differences ({len(differences)}):")
        for diff in differences:
            print(f"  - {diff}")
    
    return len(differences) == 0


def main():
    """Main entry point"""
    if len(sys.argv) > 1 and sys.argv[1] == "compare":
        # Just run comparison
        if compare_outputs("test_outputs/before", "test_outputs/after"):
            print("\n✅ All outputs are identical!")
            sys.exit(0)
        else:
            print("\n❌ Some outputs differ!")
            sys.exit(1)
    
    # Run before tests
    print("\n" + "=" * 60)
    print("BEFORE/AFTER TEST SUITE FOR XTOP")
    print("=" * 60)
    
    print("\n>>> Running BEFORE tests...")
    before_results = run_all_tests("test_outputs/before")
    
    print("\n>>> Running AFTER tests (should be identical)...")
    after_results = run_all_tests("test_outputs/after")
    
    # Compare results
    if compare_outputs("test_outputs/before", "test_outputs/after"):
        print("\n✅ SUCCESS: All before/after outputs are identical!")
        sys.exit(0)
    else:
        print("\n❌ FAILURE: Some outputs differ between before/after!")
        sys.exit(1)


if __name__ == "__main__":
    main()