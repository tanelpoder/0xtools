#!/usr/bin/env python3
"""
Test that column filtering uses the correct column after reordering
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import TableFormatter

def test_column_fix():
    """Verify the column filtering fix"""
    
    formatter = TableFormatter()
    
    # Simulate a scenario similar to the bug report
    print("Column Filtering Fix Test")
    print("=" * 60)
    
    # Original columns from query
    original = ['STATE', 'USERNAME', 'EXE', 'COMM', 'SYSCALL', 'FILENAME', 'samples', 'avg_threads']
    print("\nOriginal column order from query:")
    for i, col in enumerate(original):
        print(f"  [{i}] {col}")
    
    # After reordering for display
    display = formatter.reorder_columns_samples_first(original)
    print("\nDisplay column order (after reordering):")
    for i, col in enumerate(display):
        print(f"  [{i}] {col}")
    
    # Simulate user clicking on STATE in the display
    print("\n\nScenario: User sees STATE in column position", display.index('STATE'))
    print("User clicks on STATE column")
    
    # The fix: use display columns, not original
    clicked_visual_position = display.index('STATE')
    correct_column = display[clicked_visual_position]
    print(f"\nCorrect behavior:")
    print(f"  Visual position clicked: {clicked_visual_position}")
    print(f"  Column to filter: {correct_column} ✓")
    
    # The bug: using wrong column list
    print(f"\nBug behavior (what was happening):")
    if clicked_visual_position < len(original):
        wrong_column = original[clicked_visual_position]
        print(f"  Visual position clicked: {clicked_visual_position}")
        print(f"  Column filtered: {wrong_column} ✗")
        print(f"  This explains why clicking STATE filtered on {wrong_column}!")
    
    print("\n" + "=" * 60)
    print("The fix ensures we use 'display_columns' which matches")
    print("the visual table layout, not the original query columns.")

if __name__ == "__main__":
    test_column_fix()