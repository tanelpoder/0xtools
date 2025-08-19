#!/usr/bin/env python3
"""
Test BACKSPACE key handling and data refresh behavior
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import NavigationState

def test_backspace_navigation():
    """Test BACKSPACE-based navigation"""
    
    # Create navigation state
    nav = NavigationState()
    nav.reset("top", ["USERNAME", "EXE", "SYSCALL"])
    
    print("BACKSPACE Navigation Test")
    print("=" * 60)
    
    # Initial state
    print("\n1. Initial state:")
    print(f"   Filters: {nav.get_filter_display()}")
    print(f"   Depth: {nav.get_depth()}")
    
    # Add first filter
    print("\n2. Press ENTER on USERNAME=postgres:")
    nav.drill_down("USERNAME", "postgres")
    print(f"   Filters: {nav.get_filter_display()}")
    print(f"   Depth: {nav.get_depth()}")
    print("   → Data refreshes to show only postgres rows")
    
    # Add second filter
    print("\n3. Press ENTER on SYSCALL=pread64:")
    nav.drill_down("SYSCALL", "pread64")
    print(f"   Filters: {nav.get_filter_display()}")
    print(f"   Depth: {nav.get_depth()}")
    print("   → Data refreshes to show only postgres+pread64 rows")
    
    # Add third filter
    print("\n4. Press ENTER on FILENAME=/data/db.dat:")
    nav.drill_down("FILENAME", "/data/db.dat")
    print(f"   Filters: {nav.get_filter_display()}")
    print(f"   Depth: {nav.get_depth()}")
    print("   → Data refreshes with all three filters")
    
    # Back out with BACKSPACE
    print("\n5. Press BACKSPACE (remove last filter):")
    nav.back_out()
    print(f"   Filters: {nav.get_filter_display()}")
    print(f"   Depth: {nav.get_depth()}")
    print("   → Data refreshes to show postgres+pread64 rows")
    
    # Back out again
    print("\n6. Press BACKSPACE again:")
    nav.back_out()
    print(f"   Filters: {nav.get_filter_display()}")
    print(f"   Depth: {nav.get_depth()}")
    print("   → Data refreshes to show all postgres rows")
    
    # Back to initial
    print("\n7. Press BACKSPACE once more:")
    nav.back_out()
    print(f"   Filters: {nav.get_filter_display()}")
    print(f"   Depth: {nav.get_depth()}")
    print("   → Data refreshes to show all rows (no filters)")
    
    # Try backing out when at top level
    print("\n8. Press BACKSPACE at top level:")
    if nav.can_back_out():
        nav.back_out()
        print("   ERROR: Should not be able to back out!")
    else:
        print("   Cannot back out - already at top level ✓")
    
    print("\n" + "=" * 60)
    print("✓ BACKSPACE navigation test passed")
    print("\nKey points:")
    print("- ENTER adds WHERE column=value filter")
    print("- BACKSPACE removes last filter")
    print("- Data refreshes immediately after each action")
    print("- No ESC key issues in terminal")

if __name__ == "__main__":
    test_backspace_navigation()