#!/usr/bin/env python3
"""
Test that filtered columns remain visible in the output
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import NavigationState

def test_column_visibility():
    """Test that columns remain visible after filtering"""
    
    # Create navigation state
    nav = NavigationState()
    initial_cols = ['STATE', 'USERNAME', 'EXE', 'COMM', 'SYSCALL', 'FILENAME']
    nav.reset("top", initial_cols)
    
    print("Column Visibility Test")
    print("=" * 60)
    
    # Initial state
    print("\n1. Initial state:")
    print(f"   Group columns: {nav.get_current_group_cols()}")
    print(f"   Filters: {nav.get_filter_display()}")
    print(f"   Where clause: {nav.get_current_where_clause()}")
    
    # Filter by USERNAME
    print("\n2. Press ENTER on USERNAME=postgres:")
    nav.drill_down("USERNAME", "postgres")
    print(f"   Group columns: {nav.get_current_group_cols()}")
    print(f"   Filters: {nav.get_filter_display()}")
    print(f"   Where clause: {nav.get_current_where_clause()}")
    
    # Check if USERNAME is still in group columns
    if "USERNAME" in nav.get_current_group_cols():
        print("   ✓ USERNAME column remains visible")
    else:
        print("   ✗ USERNAME column was hidden (BUG)")
    
    # Filter by another column
    print("\n3. Press ENTER on SYSCALL=pread64:")
    nav.drill_down("SYSCALL", "pread64")
    print(f"   Group columns: {nav.get_current_group_cols()}")
    print(f"   Filters: {nav.get_filter_display()}")
    print(f"   Where clause: {nav.get_current_where_clause()}")
    
    # Check both columns are still visible
    visible_count = 0
    for col in ["USERNAME", "SYSCALL"]:
        if col in nav.get_current_group_cols():
            print(f"   ✓ {col} column remains visible")
            visible_count += 1
        else:
            print(f"   ✗ {col} column was hidden")
    
    print("\n" + "=" * 60)
    print("Summary:")
    print("- Filtered columns should remain visible in the table")
    print("- They will show the same value for all rows (the filtered value)")
    print("- This helps users understand what filters are active")
    print(f"- Filter breadcrumb shows: {nav.get_filter_display()}")

if __name__ == "__main__":
    test_column_visibility()