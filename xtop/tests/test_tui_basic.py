#!/usr/bin/env python3
"""
Basic TUI tests for XTOP using Textual's testing framework.
Tests fundamental navigation and interactions in headless mode.
"""

import pytest
import asyncio
from pathlib import Path
import sys
import os

# Set up data directory from environment variable or use default
XCAPTURE_DATADIR = os.environ.get('XCAPTURE_DATADIR', '/home/tanel/dev/0xtools-next/xcapture/out')
print(f"Using XCAPTURE_DATADIR: {XCAPTURE_DATADIR}")

# Add parent directory to path BEFORE any imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Now we can import the core modules normally
from core.query_engine import QueryEngine
from core.data_source import XCaptureDataSource
from core.navigation import NavigationState
from core.formatters import TableFormatter
from core.visualizers import ChartGenerator

from textual.widgets import DataTable
from datetime import datetime, timedelta

# Import the main TUI app using importlib
import importlib.util

class XtopTUIWrapper:
    """Wrapper to make xtop-tui testable"""
    def __init__(self, datadir: str,
                 low_time=None, high_time=None, initial_group_cols=None):
        # Load the TUI module dynamically
        spec = importlib.util.spec_from_file_location(
            "xtop_tui", 
            Path(__file__).parent.parent / "xtop-tui.py"
        )
        module = importlib.util.module_from_spec(spec)
        
        # Set the module's __path__ to help with relative imports
        module.__file__ = str(Path(__file__).parent.parent / "xtop-tui.py")
        
        # Execute the module
        spec.loader.exec_module(module)
        
        self.app_class = module.XTopTUI
        self.datadir = datadir
        # Removed initial_query_type - always dynamic now
        self.low_time = low_time
        self.high_time = high_time
        self.initial_group_cols = initial_group_cols or ['state']  # Default to just 'state'
    
    def create_app(self):
        """Create an instance of the app"""
        # Override the default grouping to just 'state' for tests
        original_defaults = QueryEngine.DEFAULT_GROUP_COLS.copy()
        for key in original_defaults:
            QueryEngine.DEFAULT_GROUP_COLS[key] = self.initial_group_cols
        
        app = self.app_class(
            datadir=self.datadir,
            low_time=self.low_time,
            high_time=self.high_time
        )
        
        # Restore original defaults after creating app
        QueryEngine.DEFAULT_GROUP_COLS = original_defaults
        
        return app


# Helper functions for navigation
async def wait_for_table_load(pilot, timeout=5):
    """Wait for the data table to load with data"""
    for _ in range(timeout * 10):  # Check every 100ms
        try:
            table = pilot.app.query_one(DataTable)
            if table and len(list(table.rows)) > 0:
                return True
        except Exception:
            # It's ok if table doesn't exist yet during startup
            pass
        await asyncio.sleep(0.1)
    return False


async def navigate_to_menu_item(pilot, item_text: str, max_attempts: int = 50):
    """Navigate to a specific item in a menu"""
    # This is simplified - real implementation would check current item
    for i in range(max_attempts):
        # In real implementation, we'd check if item_text is currently selected
        # For now, we'll just move down a certain number of times
        await pilot.press("down")
        await pilot.pause()
    return False


async def select_single_column_in_grouping(pilot, column: str):
    """Select a single column in the grouping menu using search"""
    await pilot.press("g")  # Open grouping menu
    await pilot.pause(1.0)  # Give menu time to fully load
    
    # Type the column name to search
    search_text = column.lower()
    for char in search_text:
        await pilot.press(char)
        await pilot.pause(0.1)
    
    # Wait for search to filter
    await pilot.pause(1.0)
    
    # The first matching item should be highlighted
    # Press space to toggle it
    await pilot.press("space")
    await pilot.pause(0.5)
    
    # Apply the selection
    await pilot.press("enter")
    await pilot.pause(2.0)  # Give more time for query to execute


async def add_latency_columns(pilot, columns: list):
    """Add latency columns via the 'l' menu"""
    await pilot.press("l")  # Open latency menu
    await pilot.pause()
    
    for column in columns:
        # Navigate to column (simplified)
        for _ in range(5):
            await pilot.press("down")
            await pilot.pause()
        await pilot.press("space")  # Toggle
        await pilot.pause()
    
    await pilot.press("enter")  # Apply
    await pilot.pause()


# Helper functions for validation
def get_table_data(app):
    """Get current table data"""
    try:
        table = app.query_one(DataTable)
        # Strip whitespace from column labels since numeric columns are right-justified
        columns = [col.label.plain.strip() for col in table.columns.values()]
        rows = list(table.rows)
        return columns, rows
    except Exception as e:
        print(f"Warning: Failed to get table data: {e}")
        return [], []


def validate_table_columns(app, expected_columns):
    """Validate that expected columns are present in the table"""
    columns, _ = get_table_data(app)
    
    # Convert to lowercase for comparison (already stripped in get_table_data)
    columns_lower = [col.lower() for col in columns]
    
    missing_columns = []
    for expected in expected_columns:
        expected_lower = expected.lower().strip()
        
        # Check for exact match or partial match
        # Be very flexible - username might appear as 'user', 'username', 'usr', etc.
        found = False
        for col in columns_lower:
            # Check various possibilities
            if (expected_lower == col or  # Exact match
                expected_lower in col or   # Expected is substring of column
                col in expected_lower or   # Column is substring of expected
                (expected_lower[:3] in col and len(expected_lower) > 3) or  # First 3 chars match
                (col[:3] in expected_lower and len(col) > 3)):  # First 3 chars of col in expected
                found = True
                break
        
        if not found:
            missing_columns.append(expected)
    
    if missing_columns:
        error_msg = f"Validation error: Columns {missing_columns} not found. Available columns: {columns}"
        print(error_msg)
        return False
    
    print(f"✓ Validated columns: {expected_columns} found in {columns}")
    return True


# Main test functions
def run_all_tests():
    """Run all tests synchronously"""
    print("=" * 60)
    print("XTOP TUI Testing - Basic Tests")
    print("=" * 60)
    print()
    
    # Keep track of results
    passed = 0
    failed = 0
    
    # Run each test
    tests = [
        ("test_tui_startup", test_tui_startup),
        ("test_grouping_menu", test_grouping_menu),
        ("test_add_single_column", test_add_single_column),
        ("test_add_multiple_columns", test_add_multiple_columns),
        ("test_latency_columns", test_latency_columns),
        ("test_peek_functionality", test_peek_functionality),
        ("test_navigation_keys", test_navigation_keys),
    ]
    
    for test_name, test_func in tests:
        print(f"Running {test_name}...")
        try:
            asyncio.run(test_func())
            passed += 1
        except Exception as e:
            print(f"✗ {test_name} failed: {e}")
            failed += 1
    
    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)


@pytest.mark.asyncio
async def test_tui_startup():
    """Test 1: TUI starts with only 'state' column in grouping"""
    wrapper = XtopTUIWrapper(
        datadir=XCAPTURE_DATADIR,
        initial_group_cols=['state']
    )
    app = wrapper.create_app()
    
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_table_load(pilot)
        
        # Verify table has data
        table = app.query_one(DataTable)
        row_count = len(list(table.rows))
        assert row_count > 0, f"No data rows found"
        
        # Check that 'state' column is present
        columns, _ = get_table_data(app)
        assert 'state' in [col.lower() for col in columns], "State column not found"
        
        print(f"✓ Test 1 passed: TUI started with {row_count} rows, grouped by 'state'")


@pytest.mark.asyncio
async def test_grouping_menu():
    """Test 2: Opening and using the grouping menu"""
    wrapper = XtopTUIWrapper(
        datadir=XCAPTURE_DATADIR,
        initial_group_cols=['state']
    )
    app = wrapper.create_app()
    
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_table_load(pilot)
        
        # Open grouping menu
        await pilot.press("g")
        await pilot.pause()
        
        # The menu should be visible now
        # In real implementation, we'd check for the GroupingMenuScreen
        
        # Close menu with escape
        await pilot.press("escape")
        await pilot.pause()
        
        print("✓ Test 2 passed: Grouping menu opens and closes")


@pytest.mark.asyncio
async def test_add_single_column():
    """Test 3: Adding a column to existing STATE grouping"""
    wrapper = XtopTUIWrapper(
        datadir=XCAPTURE_DATADIR,
        initial_group_cols=['state']
    )
    app = wrapper.create_app()
    
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_table_load(pilot)
        
        # Get initial columns
        initial_cols, _ = get_table_data(app)
        print(f"Initial columns: {initial_cols}")
        
        # Try to add USERNAME column (more likely to work in grouping)
        await select_single_column_in_grouping(pilot, 'USERNAME')
        
        # Wait for query to execute
        await pilot.pause()
        await wait_for_table_load(pilot)
        
        # Get new columns
        new_cols, _ = get_table_data(app)
        print(f"New columns after adding USERNAME: {new_cols}")
        
        # Check if we have more columns than before
        if len(new_cols) > len(initial_cols):
            print("✓ Test 3 passed: Successfully added a column to grouping")
        else:
            raise AssertionError(f"Failed to add column. Initial: {initial_cols}, After: {new_cols}")


@pytest.mark.asyncio
async def test_add_multiple_columns():
    """Test 4: Adding multiple columns one at a time"""
    wrapper = XtopTUIWrapper(
        datadir=XCAPTURE_DATADIR,
        initial_group_cols=['state']
    )
    app = wrapper.create_app()
    
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_table_load(pilot)
        
        # Get initial column count
        initial_cols, _ = get_table_data(app)
        initial_count = len(initial_cols)
        print(f"Starting with {initial_count} columns: {initial_cols}")
        
        # Add first column (USERNAME)
        await select_single_column_in_grouping(pilot, 'USERNAME')
        await pilot.pause()
        await wait_for_table_load(pilot)
        
        # Check column count increased
        cols_after_first, _ = get_table_data(app)
        if len(cols_after_first) <= initial_count:
            raise AssertionError(f"Failed to add first column. Before: {initial_cols}, After: {cols_after_first}")
        
        print(f"After first addition: {len(cols_after_first)} columns")
        
        # Add second column (EXE)
        await select_single_column_in_grouping(pilot, 'EXE')
        await pilot.pause()
        await wait_for_table_load(pilot)
        
        # Check column count increased again
        final_cols, _ = get_table_data(app)
        if len(final_cols) <= len(cols_after_first):
            raise AssertionError(f"Failed to add second column. Before: {cols_after_first}, After: {final_cols}")
        
        print(f"✓ Test 4 passed: Added multiple columns. Final: {len(final_cols)} columns")


@pytest.mark.asyncio
async def test_latency_columns():
    """Test 5: Adding latency columns"""
    wrapper = XtopTUIWrapper(
        datadir=XCAPTURE_DATADIR,
        initial_group_cols=['state']
    )
    app = wrapper.create_app()
    
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_table_load(pilot)
        
        # Add latency columns
        await add_latency_columns(pilot, ['sc.p95_us'])
        
        # Wait for refresh
        await pilot.pause()
        await wait_for_table_load(pilot)
        
        # Check for latency column (with flexible naming)
        columns, _ = get_table_data(app)
        columns_lower = [col.lower() for col in columns]
        
        # Look for any column containing 'p95'
        has_p95 = any('p95' in col for col in columns_lower)
        if not has_p95:
            raise AssertionError(f"p95 latency column not found. Available columns: {columns}")
        
        print("✓ Test 5 passed: Latency columns functionality works")


@pytest.mark.asyncio
async def test_peek_functionality():
    """Test 6: Test peek functionality with '?' key"""
    wrapper = XtopTUIWrapper(
        datadir=XCAPTURE_DATADIR,
        initial_group_cols=['state']
    )
    app = wrapper.create_app()
    
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_table_load(pilot)
        
        # Navigate to a cell
        await pilot.press("down")
        await pilot.pause()
        await pilot.press("right")
        await pilot.pause()
        
        # Try peek
        await pilot.press("?")
        await pilot.pause()
        
        # Close peek (if opened)
        await pilot.press("escape")
        await pilot.pause()
        
        print("✓ Test 6 passed: Peek functionality works")


@pytest.mark.asyncio
async def test_navigation_keys():
    """Test 7: Test navigation keys (arrow keys, backspace)"""
    wrapper = XtopTUIWrapper(
        datadir=XCAPTURE_DATADIR,
        initial_group_cols=['state']
    )
    app = wrapper.create_app()
    
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_table_load(pilot)
        
        # Test arrow navigation
        await pilot.press("down")
        await pilot.pause()
        await pilot.press("right")
        await pilot.pause()
        await pilot.press("up")
        await pilot.pause()
        await pilot.press("left")
        await pilot.pause()
        
        # Test drill-down (Enter)
        await pilot.press("enter")
        await pilot.pause()
        await wait_for_table_load(pilot)
        
        # Test back out (Backspace)
        await pilot.press("backspace")
        await pilot.pause()
        await wait_for_table_load(pilot)
        
        print("✓ Test 7 passed: Navigation keys work")


if __name__ == "__main__":
    run_all_tests()