#!/usr/bin/env python3
"""
TUI tests that map directly to existing CLI tests.
Each test replicates a CLI test using TUI interactions.
"""

import pytest
import asyncio
from pathlib import Path
import sys
import os
from typing import List, Dict, Any
from datetime import datetime

# Set up data directory from environment variable or use default
XCAPTURE_DATADIR = os.environ.get('XCAPTURE_DATADIR', '/home/tanel/dev/0xtools-next/xcapture/out')
print(f"Using XCAPTURE_DATADIR: {XCAPTURE_DATADIR}")

sys.path.insert(0, str(Path(__file__).parent.parent))

from test_tui_basic import (
    XtopTUIWrapper,
    wait_for_table_load,
    validate_table_columns,
    get_table_data
)


class TUITestMapper:
    """Maps CLI test parameters to TUI interactions"""
    
    def __init__(self, pilot):
        self.pilot = pilot
        self.column_positions = {}  # Cache column positions in menus
    
    async def apply_group_columns(self, columns: List[str]):
        """Apply GROUP BY columns via TUI"""
        if not columns:
            return
        
        await self.pilot.press("g")  # Open grouping menu
        await self.pilot.pause()
        
        # In a real implementation, we would:
        # 1. Parse the current menu items
        # 2. Navigate to each column
        # 3. Select it with space/enter
        
        # For now, simplified selection
        for column in columns:
            # This would need real navigation logic
            for _ in range(5):  # Assume column is within 5 moves
                await self.pilot.press("down")
            await self.pilot.press("space")  # Toggle
            await self.pilot.pause(0.1)
        
        await self.pilot.press("enter")  # Apply
        await self.pilot.pause()
    
    async def apply_latency_columns(self, columns: List[str]):
        """Apply latency columns via TUI"""
        if not columns:
            return
        
        await self.pilot.press("l")  # Open latency menu
        await self.pilot.pause()
        
        for column in columns:
            # Navigate to column (simplified)
            for _ in range(3):
                await self.pilot.press("down")
            await self.pilot.press("space")  # Toggle
            await self.pilot.pause(0.1)
        
        await self.pilot.press("enter")  # Apply
        await self.pilot.pause()
    
    async def apply_filter(self, where_clause: str):
        """Apply WHERE clause filter via TUI"""
        if not where_clause or where_clause == "1=1":
            return
        
        await self.pilot.press("space")  # Open filter menu
        await self.pilot.pause()
        
        # In real implementation, would type the filter
        # For now, just close
        await self.pilot.press("escape")
        await self.pilot.pause()
    
    async def peek_column(self, column: str):
        """Peek at a specific column"""
        # Navigate to the column in the table
        # This would need real navigation to the correct cell
        await self.pilot.press("?")
        await self.pilot.pause(0.5)
        
        # Capture peek content (in real test)
        
        await self.pilot.press("escape")  # Close peek
        await self.pilot.pause()


class CLITestCase:
    """Represents a CLI test case to be replicated in TUI"""
    
    def __init__(self, name: str, group_cols: List[str] = None,
                 latency_cols: List[str] = None, where_clause: str = "1=1",
                 peek: bool = False):
        self.name = name
        self.group_cols = group_cols or []
        self.latency_cols = latency_cols or []
        self.where_clause = where_clause
        self.peek = peek
    
    async def execute_in_tui(self, pilot, mapper: TUITestMapper):
        """Execute this test case in the TUI"""
        # Apply group columns
        await mapper.apply_group_columns(self.group_cols)
        
        # Apply latency columns
        await mapper.apply_latency_columns(self.latency_cols)
        
        # Apply filter
        await mapper.apply_filter(self.where_clause)
        
        # Peek if requested
        if self.peek and self.latency_cols:
            # Peek at first histogram column
            for col in self.latency_cols:
                if 'HISTOGRAM' in col:
                    await mapper.peek_column(col)
                    break
    
    def validate_result(self, app) -> bool:
        """Validate that the TUI shows expected columns"""
        expected_cols = []
        
        # Add group columns
        expected_cols.extend(self.group_cols)
        
        # Add latency columns (with name transformation)
        for col in self.latency_cols:
            # Transform sc.p95_us -> sc_p95_us
            transformed = col.replace('.', '_')
            expected_cols.append(transformed)
        
        # Always expect these base columns
        expected_cols.extend(['samples', 'avg_threads'])
        
        try:
            validate_table_columns(app, expected_cols)
            return True
        except AssertionError as e:
            print(f"Validation failed: {e}")
            return False


# Define test cases that map to CLI tests
TEST_CASES = [
    # Test 1: Basic dynamic query (default, no special columns)
    CLITestCase(
        name="Basic dynamic query",
        group_cols=[],
        latency_cols=[]
    ),
    
    # Test 2: Custom GROUP BY
    CLITestCase(
        name="Dynamic with custom GROUP BY",
        group_cols=['STATE', 'USERNAME', 'COMM'],
        latency_cols=[]
    ),
    
    # Test 3: Computed columns
    CLITestCase(
        name="Dynamic with computed columns",
        group_cols=['STATE', 'FILENAMESUM', 'COMM2'],
        latency_cols=[]
    ),
    
    # Test 4: Syscall latency percentiles
    CLITestCase(
        name="Dynamic with syscall latency",
        group_cols=['STATE', 'SYSCALL'],
        latency_cols=['sc.min_lat_us', 'sc.avg_lat_us', 'sc.p95_us']
    ),
    
    # Test 5: I/O latency
    CLITestCase(
        name="Dynamic with I/O latency",
        group_cols=['STATE', 'EXE'],
        latency_cols=['io.min_lat_us', 'io.avg_lat_us', 'io.max_lat_us']
    ),
    
    # Test 6: Histogram
    CLITestCase(
        name="Dynamic with histogram",
        group_cols=['STATE', 'SYSCALL'],
        latency_cols=['SCLAT_HISTOGRAM']
    ),
    
    # Test 7: Stack traces
    CLITestCase(
        name="Dynamic with kernel stacks",
        group_cols=['STATE', 'KSTACK_CURRENT_FUNC', 'KSTACK_HASH'],
        latency_cols=[]
    ),
    
    # Test 8: WHERE clause
    CLITestCase(
        name="Dynamic with WHERE clause",
        group_cols=['STATE', 'COMM'],
        where_clause="STATE = 'Running'"
    ),
    
    # Test 9: Peek functionality
    CLITestCase(
        name="Dynamic with peek",
        group_cols=['STATE', 'SYSCALL'],
        latency_cols=['SCLAT_HISTOGRAM'],
        peek=True
    ),
    
    # Test 10: Complex multi-feature
    CLITestCase(
        name="Complex multi-feature",
        group_cols=['STATE', 'USERNAME', 'COMM2'],
        latency_cols=['sc.p95_us', 'SCLAT_HISTOGRAM'],
        where_clause="STATE IN ('Running', 'Disk (Uninterruptible)')"
    )
]


@pytest.mark.asyncio
async def test_cli_mapping(test_case: CLITestCase):
    """Generic test function that executes a CLI test case in TUI"""
    wrapper = XtopTUIWrapper(
        datadir=XCAPTURE_DATADIR,
        low_time=datetime.fromisoformat("2025-08-03T03:40:00"),
        high_time=datetime.fromisoformat("2025-08-03T04:07:00")
    )
    app = wrapper.create_app()
    
    async with app.run_test(size=(140, 50)) as pilot:
        # Wait for initial load
        await pilot.pause()
        await wait_for_table_load(pilot)
        
        # Create mapper
        mapper = TUITestMapper(pilot)
        
        # Execute test case
        await test_case.execute_in_tui(pilot, mapper)
        
        # Wait for results
        await pilot.pause()
        await wait_for_table_load(pilot)
        
        # Validate
        success = test_case.validate_result(app)
        
        if success:
            print(f"✓ {test_case.name} passed")
        else:
            # Get actual columns for debugging
            cols, _ = get_table_data(app)
            print(f"✗ {test_case.name} failed - columns: {cols}")
            raise AssertionError(f"Test {test_case.name} validation failed")


# Generate individual test functions for pytest
def generate_test_functions():
    """Generate test functions dynamically for each test case"""
    for i, test_case in enumerate(TEST_CASES):
        # Create a test function for this case
        async def test_func():
            await test_cli_mapping(test_case)
        
        # Set function name and docstring
        test_func.__name__ = f"test_cli_case_{i+1}_{test_case.name.replace(' ', '_').lower()}"
        test_func.__doc__ = f"Test {i+1}: {test_case.name}"
        
        # Add to module globals so pytest can find it
        globals()[test_func.__name__] = pytest.mark.asyncio(test_func)


# Generate the test functions
generate_test_functions()


# Manual test runner for debugging
async def run_single_test(test_index: int):
    """Run a single test case by index"""
    if test_index < 0 or test_index >= len(TEST_CASES):
        print(f"Invalid test index: {test_index}")
        return
    
    test_case = TEST_CASES[test_index]
    print(f"Running test {test_index + 1}: {test_case.name}")
    
    try:
        await test_cli_mapping(test_case)
        print(f"✓ Test passed")
    except Exception as e:
        print(f"✗ Test failed: {e}")


# Main runner for standalone execution
if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("XTOP TUI Testing - CLI Test Mapping")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        # Run specific test
        test_index = int(sys.argv[1]) - 1
        asyncio.run(run_single_test(test_index))
    else:
        # Run all tests
        passed = 0
        failed = 0
        
        for i, test_case in enumerate(TEST_CASES):
            print(f"\nTest {i+1}: {test_case.name}")
            print("-" * 40)
            
            try:
                asyncio.run(test_cli_mapping(test_case))
                passed += 1
            except Exception as e:
                print(f"Failed: {e}")
                failed += 1
        
        print("\n" + "=" * 60)
        print(f"Results: {passed} passed, {failed} failed")
        print("=" * 60)
        
        sys.exit(0 if failed == 0 else 1)