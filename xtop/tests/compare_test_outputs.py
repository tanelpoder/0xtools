#!/usr/bin/env python3
"""
Smart comparison of test outputs that handles row ordering differences.
"""

import sys
from pathlib import Path
import hashlib
import json


def parse_table_output(content):
    """Parse table output into structured data"""
    lines = content.strip().split('\n')
    
    # Find the header line (contains column names)
    header_idx = -1
    for i, line in enumerate(lines):
        if line and not line.startswith('=') and not line.startswith('Rows:'):
            # Skip separator lines
            if set(line.strip()) != {'-', ' '}:
                header_idx = i
                break
    
    if header_idx == -1:
        return None, None
    
    # Parse header
    headers = lines[header_idx].split()
    
    # Find separator line
    sep_idx = header_idx + 1
    while sep_idx < len(lines) and not set(lines[sep_idx].strip()) <= {'-', ' '}:
        sep_idx += 1
    
    # Parse data rows
    rows = []
    for line in lines[sep_idx + 1:]:
        if line.strip():
            # Split by multiple spaces (table columns)
            parts = line.split()
            if len(parts) >= len(headers):
                row = {}
                for i, header in enumerate(headers):
                    if i < len(parts):
                        row[header] = parts[i]
                rows.append(row)
    
    return headers, rows


def normalize_row_for_comparison(row):
    """Create a normalized string representation of a row for comparison"""
    # Sort keys to ensure consistent ordering
    sorted_keys = sorted(row.keys())
    values = [str(row.get(k, '')) for k in sorted_keys]
    return '|'.join(values)


def compare_table_outputs(content1, content2):
    """Compare two table outputs, ignoring row order"""
    headers1, rows1 = parse_table_output(content1)
    headers2, rows2 = parse_table_output(content2)
    
    # Check if parsing failed
    if headers1 is None or headers2 is None:
        return False, "Failed to parse table output"
    
    # Check headers match
    if set(headers1) != set(headers2):
        return False, f"Headers differ: {headers1} vs {headers2}"
    
    # Check row count
    if len(rows1) != len(rows2):
        return False, f"Row count differs: {len(rows1)} vs {len(rows2)}"
    
    # Compare rows as sets (order-independent)
    rows1_normalized = {normalize_row_for_comparison(row) for row in rows1}
    rows2_normalized = {normalize_row_for_comparison(row) for row in rows2}
    
    if rows1_normalized != rows2_normalized:
        # Find differences
        only_in_1 = rows1_normalized - rows2_normalized
        only_in_2 = rows2_normalized - rows1_normalized
        
        diff_msg = []
        if only_in_1:
            diff_msg.append(f"Rows only in before ({len(only_in_1)}): {list(only_in_1)[:2]}")
        if only_in_2:
            diff_msg.append(f"Rows only in after ({len(only_in_2)}): {list(only_in_2)[:2]}")
        
        return False, "; ".join(diff_msg)
    
    return True, "Data identical (ignoring row order)"


def compare_test_outputs(before_dir, after_dir):
    """Compare all test outputs intelligently"""
    before_path = Path(before_dir)
    after_path = Path(after_dir)
    
    # Get all test files
    test_files = sorted([f.name for f in before_path.glob("*.txt") if not f.name.endswith("_error.txt")])
    
    results = {
        "identical": [],
        "equivalent": [],  # Same data, different order
        "different": []
    }
    
    for test_file in test_files:
        before_file = before_path / test_file
        after_file = after_path / test_file
        
        if not after_file.exists():
            results["different"].append((test_file, "After file missing"))
            continue
        
        # Read contents
        with open(before_file, 'r') as f:
            before_content = f.read()
        with open(after_file, 'r') as f:
            after_content = f.read()
        
        # First check if files are byte-identical
        if before_content == after_content:
            results["identical"].append(test_file)
        else:
            # Try smart comparison
            is_same, msg = compare_table_outputs(before_content, after_content)
            if is_same:
                results["equivalent"].append((test_file, msg))
            else:
                results["different"].append((test_file, msg))
    
    return results


def main():
    """Main entry point"""
    before_dir = "test_outputs/before"
    after_dir = "test_outputs/after"
    
    if not Path(before_dir).exists() or not Path(after_dir).exists():
        print("Error: Test output directories not found. Run tests first.")
        sys.exit(1)
    
    print("=" * 60)
    print("Smart Comparison of Before/After Test Outputs")
    print("=" * 60)
    
    results = compare_test_outputs(before_dir, after_dir)
    
    # Print results
    total = len(results["identical"]) + len(results["equivalent"]) + len(results["different"])
    
    print(f"\n✅ Identical outputs: {len(results['identical'])}/{total}")
    if results["identical"]:
        for test in results["identical"][:5]:
            print(f"  - {test}")
        if len(results["identical"]) > 5:
            print(f"  ... and {len(results['identical'])-5} more")
    
    print(f"\n✅ Equivalent outputs (same data, different order): {len(results['equivalent'])}/{total}")
    if results["equivalent"]:
        for test, msg in results["equivalent"][:5]:
            print(f"  - {test}: {msg}")
        if len(results["equivalent"]) > 5:
            print(f"  ... and {len(results['equivalent'])-5} more")
    
    print(f"\n❌ Different outputs: {len(results['different'])}/{total}")
    if results["different"]:
        for test, msg in results["different"]:
            print(f"  - {test}: {msg}")
    
    # Summary
    print("\n" + "=" * 60)
    if len(results["different"]) == 0:
        print("✅ SUCCESS: All test outputs are identical or equivalent!")
        print(f"   {len(results['identical'])} byte-identical")
        print(f"   {len(results['equivalent'])} equivalent (row order differs)")
        sys.exit(0)
    else:
        print(f"❌ FAILURE: {len(results['different'])} tests have different data!")
        sys.exit(1)


if __name__ == "__main__":
    main()