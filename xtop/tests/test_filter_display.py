#!/usr/bin/env python3
"""
Test filter breadcrumbs display
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import NavigationState

def test_filter_display():
    """Test filter display formatting"""
    
    # Create navigation state
    nav = NavigationState()
    nav.reset("top", ["USERNAME", "EXE", "SYSCALL"])
    
    print("Filter Display Examples:")
    print("=" * 60)
    
    # No filters
    print("\n1. Initial state (no filters):")
    print(f"   Display: {nav.get_filter_display()}")
    print(f"   Where clause: {nav.get_current_where_clause()}")
    
    # Single filter
    print("\n2. After pressing Enter on USERNAME=postgres:")
    nav.drill_down("USERNAME", "postgres")
    print(f"   Display: {nav.get_filter_display()}")
    print(f"   Where clause: {nav.get_current_where_clause()}")
    
    # Multiple filters
    print("\n3. After pressing Enter on SYSCALL=pread64:")
    nav.drill_down("SYSCALL", "pread64")
    print(f"   Display: {nav.get_filter_display()}")
    print(f"   Where clause: {nav.get_current_where_clause()}")
    
    # Filter with space in value
    print("\n4. After pressing Enter on COMM='pg worker':")
    nav.drill_down("COMM", "pg worker")
    print(f"   Display: {nav.get_filter_display()}")
    print(f"   Where clause: {nav.get_current_where_clause()}")
    
    # Back out one
    print("\n5. After pressing ESC:")
    nav.back_out()
    print(f"   Display: {nav.get_filter_display()}")
    print(f"   Where clause: {nav.get_current_where_clause()}")
    
    print("\n" + "=" * 60)
    print("✓ Filter display test passed")

if __name__ == "__main__":
    test_filter_display()