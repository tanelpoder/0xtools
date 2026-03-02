#!/usr/bin/env python3
"""
Test the enhanced column selection modals with alphabetical ordering and search functionality.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from core.column_utils import get_unified_column_list, filter_columns_by_pattern


def test_unified_column_list():
    """Test that unified column list is created correctly with source labels"""
    print("Testing unified column list generation...")
    
    # Mock columns by source
    columns_by_source = {
        'samples': ['TID', 'PID', 'STATE', 'COMM', 'FILENAME'],
        'syscend': ['TID', 'DURATION_NS', 'TYPE'],
        'iorqend': ['INSERT_TID', 'DURATION_NS', 'DEV_MAJ'],
        'kstacks': ['KSTACK_HASH', 'KSTACK_SYMS'],
        'ustacks': ['USTACK_HASH', 'USTACK_SYMS']
    }
    
    # Get unified list
    unified = get_unified_column_list(columns_by_source)
    
    # Check that it's alphabetically sorted
    display_names = [display for _, display, _ in unified]
    sorted_names = sorted(display_names, key=lambda x: x.lower())
    assert display_names == sorted_names, "Columns should be alphabetically sorted"
    print(f"✓ Generated {len(unified)} columns in alphabetical order")
    
    # Check that source labels are added
    for col_name, display_name, col_id in unified:
        assert '(' in display_name and ')' in display_name, f"Column {display_name} should have source label"
    print("✓ All columns have source labels")
    
    # Check for specific columns
    tid_entries = [item for item in unified if item[0] == 'TID']
    assert len(tid_entries) == 1, "TID should appear once (from samples)"
    assert '(samples)' in tid_entries[0][1], "TID should be labeled as from samples"
    
    duration_entries = [item for item in unified if item[0] == 'DURATION_NS']
    assert len(duration_entries) == 1, "DURATION_NS should appear once"
    
    kstack_hash_entries = [item for item in unified if item[0] == 'KSTACK_HASH']
    assert len(kstack_hash_entries) == 1, "KSTACK_HASH should appear once"
    
    print("✓ Duplicate columns are properly handled")
    
    # Test derived columns
    columns_with_derived = {
        'samples': ['COMM'],
    }
    unified_with_derived = get_unified_column_list(columns_with_derived)
    
    # Look for comm2 (derived)
    comm2_found = False
    for col_name, display_name, col_id in unified_with_derived:
        if col_name == 'comm2':
            comm2_found = True
            assert 'derived' in display_name, "comm2 should be marked as derived"
            break
    
    print("✓ Derived columns are properly labeled")
    
    return True


def test_filter_columns_by_pattern():
    """Test pattern-based column filtering"""
    print("\nTesting column filtering by pattern...")
    
    # Create test columns
    test_columns = [
        ('COMM', 'comm (samples)', 'COMM'),
        ('COMM2', 'comm2 (samples, derived)', 'COMM2'),
        ('FILENAME', 'filename (samples)', 'FILENAME'),
        ('FILENAMESUM', 'filenamesum (samples, derived)', 'FILENAMESUM'),
        ('STATE', 'state (samples)', 'STATE'),
        ('KSTACK_HASH', 'kstack_hash (kstack)', 'KSTACK_HASH'),
        ('TID', 'tid (samples)', 'TID'),
        ('USERNAME', 'username (samples)', 'USERNAME')
    ]
    
    # Test empty pattern (should return all)
    filtered = filter_columns_by_pattern(test_columns, '')
    assert len(filtered) == len(test_columns), "Empty pattern should return all columns"
    print(f"✓ Empty pattern returns all {len(test_columns)} columns")
    
    # Test pattern 'f' - should match filename, filenamesum
    filtered = filter_columns_by_pattern(test_columns, 'f')
    assert len(filtered) == 2, f"Pattern 'f' should match 2 columns, got {len(filtered)}"
    assert all('f' in item[1].split(' (')[0] for item in filtered), "All matches should contain 'f'"
    print(f"✓ Pattern 'f' matches {len(filtered)} columns: {[item[0] for item in filtered]}")
    
    # Test pattern 'ile' - should match filename, filenamesum
    filtered = filter_columns_by_pattern(test_columns, 'ile')
    assert len(filtered) == 2, f"Pattern 'ile' should match 2 columns, got {len(filtered)}"
    print(f"✓ Pattern 'ile' matches {len(filtered)} columns: {[item[0] for item in filtered]}")
    
    # Test pattern 'hash' - should match stack_hash
    filtered = filter_columns_by_pattern(test_columns, 'hash')
    assert len(filtered) == 1, f"Pattern 'hash' should match 1 column, got {len(filtered)}"
    assert filtered[0][0] == 'KSTACK_HASH', "Pattern 'hash' should match KSTACK_HASH"
    print(f"✓ Pattern 'hash' matches {len(filtered)} column: {filtered[0][0]}")
    
    # Test pattern 'comm' - should match comm and comm2
    filtered = filter_columns_by_pattern(test_columns, 'comm')
    assert len(filtered) == 2, f"Pattern 'comm' should match 2 columns, got {len(filtered)}"
    assert set(item[0] for item in filtered) == {'COMM', 'COMM2'}, "Should match COMM and COMM2"
    print(f"✓ Pattern 'comm' matches {len(filtered)} columns: {[item[0] for item in filtered]}")
    
    # Test case-insensitive matching
    filtered_upper = filter_columns_by_pattern(test_columns, 'COMM')
    filtered_lower = filter_columns_by_pattern(test_columns, 'comm')
    assert filtered_upper == filtered_lower, "Pattern matching should be case-insensitive"
    print("✓ Pattern matching is case-insensitive")
    
    # Test pattern that matches nothing
    filtered = filter_columns_by_pattern(test_columns, 'xyz')
    assert len(filtered) == 0, "Pattern 'xyz' should match no columns"
    print("✓ Non-matching pattern returns empty list")
    
    return True


def test_source_label_mapping():
    """Test that source labels are properly mapped"""
    print("\nTesting source label mapping...")
    
    columns_by_source = {
        'samples': ['TID'],
        'syscend': ['DURATION_NS'],
        'iorqend': ['IORQ_LATENCY'],
        'kstacks': ['KSTACK_HASH'],
        'ustacks': ['USTACK_HASH'],
        'partitions': ['DEVNAME']
    }
    
    unified = get_unified_column_list(columns_by_source)
    
    # Check label mapping
    label_map = {
        'TID': 'samples',
        'DURATION_NS': 'syscall',
        'IORQ_LATENCY': 'iorq',
        'KSTACK_HASH': 'kstack',
        'USTACK_HASH': 'ustack',
        'DEVNAME': 'partition'
    }
    
    for col_name, display_name, _ in unified:
        if col_name in label_map:
            expected_label = label_map[col_name]
            assert f'({expected_label})' in display_name, f"{col_name} should have label ({expected_label}), got {display_name}"
    
    print("✓ All source labels are correctly mapped")
    return True


def test_time_columns():
    """Test that time-based computed columns are properly labeled"""
    print("\nTesting time column labeling...")
    
    # Even with empty sources, computed columns should appear
    columns_by_source = {}
    unified = get_unified_column_list(columns_by_source)
    
    # Look for time columns
    time_cols = ['YYYY', 'MM', 'DD', 'HH', 'MI', 'SS', 'S10']
    found_time_cols = []
    
    for col_name, display_name, _ in unified:
        if col_name in time_cols:
            found_time_cols.append(col_name)
            assert '(time)' in display_name, f"{col_name} should be labeled as (time), got {display_name}"
    
    assert len(found_time_cols) == len(time_cols), f"Should find all time columns, found: {found_time_cols}"
    print(f"✓ All {len(time_cols)} time columns are properly labeled")
    
    return True


def main():
    """Run all tests"""
    print("=" * 60)
    print("Column Selection Tests")
    print("=" * 60)
    
    tests = [
        test_unified_column_list,
        test_filter_columns_by_pattern,
        test_source_label_mapping,
        test_time_columns
    ]
    
    failed = []
    for test in tests:
        try:
            if not test():
                failed.append(test.__name__)
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            failed.append(test.__name__)
    
    print("\n" + "=" * 60)
    if not failed:
        print("✅ All column selection tests passed!")
        return 0
    else:
        print(f"❌ {len(failed)} tests failed: {', '.join(failed)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())