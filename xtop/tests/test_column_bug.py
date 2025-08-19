#!/usr/bin/env python3
"""
Test column filtering bug - wrong column being filtered
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import TableFormatter

def test_column_reordering():
    """Test how column reordering affects column indices"""
    
    formatter = TableFormatter()
    
    # Simulate columns from a query result
    original_columns = ['STATE', 'USERNAME', 'EXE', 'COMM', 'SYSCALL', 'samples', 'avg_threads']
    
    print("Original column order:")
    for i, col in enumerate(original_columns):
        print(f"  [{i}] {col}")
    
    # Reorder columns
    reordered = formatter.reorder_columns_samples_first(original_columns)
    
    print("\nReordered column order:")
    for i, col in enumerate(reordered):
        print(f"  [{i}] {col}")
    
    # Simulate clicking on STATE in the reordered view
    print("\nScenario: User clicks on STATE column in the display")
    
    # Find STATE position in original
    orig_state_idx = original_columns.index('STATE')
    print(f"  STATE is at index {orig_state_idx} in original")
    
    # Find STATE position in reordered
    reord_state_idx = reordered.index('STATE')
    print(f"  STATE is at index {reord_state_idx} in reordered (display)")
    
    # If user clicks on visual position 2 (where STATE appears)
    clicked_idx = reord_state_idx
    clicked_column = reordered[clicked_idx]
    print(f"\n  User clicks on display column index {clicked_idx}")
    print(f"  This corresponds to column: {clicked_column}")
    
    # But if we incorrectly use original column order...
    if clicked_idx < len(original_columns):
        wrong_column = original_columns[clicked_idx]
        print(f"  ERROR: If we use original order, we'd get: {wrong_column}")

if __name__ == "__main__":
    test_column_reordering()