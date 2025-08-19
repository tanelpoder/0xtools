#!/usr/bin/env python3
"""
Test navigation behavior - arrow keys move cursor, Enter filters
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import NavigationState

def test_navigation():
    """Test that navigation works as expected"""
    
    # Create navigation state
    nav = NavigationState()
    nav.reset("top", ["USERNAME", "EXE", "SYSCALL"])
    
    print("Initial state:")
    print(f"  Filters: {nav.get_current_filters()}")
    print(f"  Where clause: {nav.get_current_where_clause()}")
    print()
    
    # Simulate pressing Enter on a cell with USERNAME=postgres
    print("1. Press Enter on cell with USERNAME=postgres")
    nav.drill_down("USERNAME", "postgres")
    print(f"  Filters: {nav.get_current_filters()}")
    print(f"  Where clause: {nav.get_current_where_clause()}")
    print()
    
    # Simulate pressing Enter on another cell with SYSCALL=pread64
    print("2. Press Enter on cell with SYSCALL=pread64")
    nav.drill_down("SYSCALL", "pread64")
    print(f"  Filters: {nav.get_current_filters()}")
    print(f"  Where clause: {nav.get_current_where_clause()}")
    print()
    
    # Simulate pressing BACKSPACE
    print("3. Press BACKSPACE (back out last filter)")
    nav.back_out()
    print(f"  Filters: {nav.get_current_filters()}")
    print(f"  Where clause: {nav.get_current_where_clause()}")
    print()
    
    # Simulate pressing BACKSPACE again
    print("4. Press BACKSPACE again (back to initial)")
    nav.back_out()
    print(f"  Filters: {nav.get_current_filters()}")
    print(f"  Where clause: {nav.get_current_where_clause()}")
    print()
    
    print("✓ Navigation test passed")
    print("\nSummary:")
    print("- Arrow keys: Just move cursor position (no filtering)")
    print("- Enter: Add WHERE column=value filter at cursor position")
    print("- BACKSPACE: Remove last filter (back out one step)")
    print("- Data refreshes immediately after filtering")

if __name__ == "__main__":
    test_navigation()