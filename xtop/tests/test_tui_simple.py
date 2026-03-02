#!/usr/bin/env python3
"""
Simplified TUI tests for XTOP that focus on basic functionality.
Tests fundamental UI elements without complex interactions.
"""

import pytest

pytest.importorskip(
    "pytest_asyncio",
    reason="pytest-asyncio plugin is required for async TUI tests",
)

import asyncio
from pathlib import Path
import sys
import os
import re
from datetime import datetime, timedelta

# Set up data directory from environment variable or use default
XCAPTURE_DATADIR = os.environ.get('XCAPTURE_DATADIR', '/home/tanel/dev/0xtools-next/xcapture/out')
print(f"Using XCAPTURE_DATADIR: {XCAPTURE_DATADIR}")

# Add parent directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import core modules
from core.query_engine import QueryEngine
from core.data_source import XCaptureDataSource
from core.navigation import NavigationState
from core.formatters import TableFormatter

from textual.widgets import DataTable, HelpPanel

# Import the main TUI app using importlib
import importlib.util
from tui.value_filter_modal import ValueFilterModal

def _detect_default_time_range(datadir: str) -> tuple[datetime, datetime]:
    """Detect an available hour of data for the TUI tests."""
    path = Path(datadir)
    candidates = list(path.glob("xcapture_samples_*.csv"))
    candidates += list(path.glob("xcapture_samples_*.parquet"))

    if not candidates:
        pytest.skip(
            f"No xcapture sample files found in {datadir}; skipping TUI tests",
            allow_module_level=True,
        )

    pattern = re.compile(r"xcapture_samples_(\d{4}-\d{2}-\d{2})\.(\d{2})")
    timestamps: list[datetime] = []
    for candidate in candidates:
        match = pattern.search(candidate.name)
        if not match:
            continue
        date_part, hour_part = match.groups()
        try:
            timestamps.append(datetime.strptime(f"{date_part} {hour_part}", "%Y-%m-%d %H"))
        except ValueError:
            continue

    if not timestamps:
        pytest.skip(
            f"Could not parse timestamps from sample files in {datadir}; skipping TUI tests",
            allow_module_level=True,
        )

    hour = max(timestamps)
    return hour, hour + timedelta(hours=1)


DEFAULT_LOW_TIME, DEFAULT_HIGH_TIME = _detect_default_time_range(XCAPTURE_DATADIR)


class XtopTUIWrapper:
    """Wrapper to make xtop TUI testable"""
    def __init__(self, datadir: str, initial_group_cols=None):
        # Load the TUI module dynamically
        spec = importlib.util.spec_from_file_location(
            "xtop_tui", 
            Path(__file__).parent.parent / "xtop-tui.py"
        )
        module = importlib.util.module_from_spec(spec)
        module.__file__ = str(Path(__file__).parent.parent / "xtop-tui.py")
        spec.loader.exec_module(module)
        
        # Store the class
        self.XTopTUI = module.XTopTUI
        self.datadir = datadir
        self.initial_group_cols = initial_group_cols or ['state']
        
    def create_app(self):
        """Create an instance of the TUI app"""
        return self.XTopTUI(
            datadir=self.datadir,
            initial_group_by=self.initial_group_cols,  # Use correct parameter name
            low_time=DEFAULT_LOW_TIME,
            high_time=DEFAULT_HIGH_TIME
        )


# Test helper functions
def get_table_data(app):
    """Get current table data with cleaned column names"""
    try:
        table = app.query_one(DataTable)
        # Strip whitespace from column labels since numeric columns are right-justified
        columns = [col.label.plain.strip() for col in table.columns.values()]
        row_count = len(list(table.rows))
        return columns, row_count
    except Exception as e:
        print(f"Warning: Failed to get table data: {e}")
        return [], 0


async def wait_for_app_ready(pilot, timeout=5):
    """Wait for the app to be ready with data loaded"""
    for _ in range(timeout * 10):
        try:
            table = pilot.app.query_one(DataTable)
            if table and len(list(table.rows)) > 0:
                return True
        except:
            pass
        await pilot.pause(0.1)
    return False


# Simple tests that don't rely on complex menu interactions
@pytest.mark.asyncio
async def test_tui_startup():
    """Test 1: TUI starts successfully and loads data"""
    wrapper = XtopTUIWrapper(
        datadir=XCAPTURE_DATADIR,
        initial_group_cols=['state']
    )
    app = wrapper.create_app()
    
    async with app.run_test(size=(120, 40)) as pilot:
        # Wait for app to start
        await pilot.pause(1.0)
        
        # Check if app loaded
        if await wait_for_app_ready(pilot):
            columns, row_count = get_table_data(app)
            print(f"✓ TUI started with {len(columns)} columns and {row_count} rows")
            print(f"  Columns: {columns}")
            
            # Verify we have expected basic columns
            assert 'state' in [c.lower() for c in columns], "state column should be present"
            assert row_count > 0, "Should have some data rows"
        else:
            raise AssertionError("TUI failed to load data")


@pytest.mark.asyncio
async def test_navigation_keys():
    """Test 2: Basic keyboard navigation works"""
    wrapper = XtopTUIWrapper(
        datadir=XCAPTURE_DATADIR,
        initial_group_cols=['state', 'username']
    )
    app = wrapper.create_app()
    
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(1.0)
        await wait_for_app_ready(pilot)
        
        # Test arrow key navigation
        await pilot.press("down")
        await pilot.pause(0.5)
        await pilot.press("up")
        await pilot.pause(0.5)
        await pilot.press("right")
        await pilot.pause(0.5)
        await pilot.press("left")
        await pilot.pause(0.5)
        
        # If we get here without errors, navigation works
        print("✓ Navigation keys work without errors")


@pytest.mark.asyncio
async def test_refresh_command():
    """Test 3: Refresh command works"""
    wrapper = XtopTUIWrapper(
        datadir=XCAPTURE_DATADIR,
        initial_group_cols=['state']
    )
    app = wrapper.create_app()
    
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(1.0)
        await wait_for_app_ready(pilot)
        
        # Get initial data
        initial_cols, initial_rows = get_table_data(app)
        
        # Press 'r' to refresh
        await pilot.press("r")
        await pilot.pause(2.0)  # Wait for refresh
        
        # Get data after refresh
        new_cols, new_rows = get_table_data(app)
        
        # Data should still be present after refresh
        assert len(new_cols) > 0, "Should have columns after refresh"
        assert new_rows > 0, "Should have rows after refresh"
        
        print(f"✓ Refresh works: {initial_rows} rows → {new_rows} rows")


@pytest.mark.asyncio
async def test_different_initial_grouping():
    """Test 4: Can start with different GROUP BY columns"""
    test_cases = [
        ['state'],
        ['state', 'username'],
        ['state', 'exe'],
        ['state', 'comm']
    ]
    
    for group_cols in test_cases:
        wrapper = XtopTUIWrapper(
            datadir=XCAPTURE_DATADIR,
            initial_group_cols=group_cols
        )
        app = wrapper.create_app()
        
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(1.0)
            
            if await wait_for_app_ready(pilot):
                columns, row_count = get_table_data(app)
                
                # Check that GROUP BY columns are present
                # Note: 'username' might appear as 'user' in the display
                columns_lower = [c.lower() for c in columns]
                for col in group_cols:
                    col_lower = col.lower()
                    # Handle column name variations
                    if col_lower == 'username':
                        assert ('username' in columns_lower or 'user' in columns_lower), \
                            f"{col} (or 'user') should be in columns: {columns}"
                    else:
                        assert col_lower in columns_lower, f"{col} should be in columns: {columns}"
                
                print(f"✓ Grouping by {group_cols}: {row_count} rows")
            else:
                raise AssertionError(f"Failed to load with GROUP BY {group_cols}")


@pytest.mark.asyncio
async def test_escape_key():
    """Test 5: ESC key handling"""
    wrapper = XtopTUIWrapper(
        datadir=XCAPTURE_DATADIR,
        initial_group_cols=['state']
    )
    app = wrapper.create_app()
    
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(1.0)
        await wait_for_app_ready(pilot)
        
        # Press ESC multiple times - should not crash
        await pilot.press("escape")
        await pilot.pause(0.5)
        await pilot.press("escape")
        await pilot.pause(0.5)
        
        # Check app is still running
        columns, row_count = get_table_data(app)
        assert len(columns) > 0, "App should still be running after ESC"
        
        print("✓ ESC key handled without crashes")


@pytest.mark.asyncio
async def test_value_search_modal_includes_filters():
    """Test 6: '/' modal applies include filters in one step."""
    wrapper = XtopTUIWrapper(
        datadir=XCAPTURE_DATADIR,
        initial_group_cols=['state']
    )
    app = wrapper.create_app()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(1.0)
        assert await wait_for_app_ready(pilot)

        # Move cursor to the GROUP BY column ('state')
        await pilot.press("right")
        await pilot.press("right")
        await pilot.press("right")

        await pilot.press("/")
        await pilot.pause(0.2)
        modal = None
        for entry in app.screen_stack:
            screen = getattr(entry, "screen", None)
            if isinstance(screen, ValueFilterModal):
                modal = screen
                break
        assert modal is not None
        assert modal.column_name.lower() == 'state'

        await pilot.pause(0.1)
        if modal.option_list and modal.filtered_keys:
            if modal.option_list.highlighted is None:
                modal.option_list.highlighted = 0
            selected_key = modal.filtered_keys[modal.option_list.highlighted]
            selected_entry = modal.entries[selected_key]
        else:
            pytest.skip("Value filter modal did not contain entries")

        await pilot.press("space")
        await pilot.pause(0.1)
        assert selected_entry.state == "include"

        await pilot.press("enter")
        await pilot.pause(0.2)

        filters = app.navigation.current_frame.filters
        assert 'state' in filters
        assert filters['state'] == [selected_entry.value]


@pytest.mark.asyncio
async def test_help_panel_toggle():
    """Help panel should toggle on repeated 'h' presses."""
    wrapper = XtopTUIWrapper(datadir=XCAPTURE_DATADIR)
    app = wrapper.create_app()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(1.0)
        assert await wait_for_app_ready(pilot)

        await pilot.press("h")
        await pilot.pause(0.2)

        assert len(app.screen.query(HelpPanel)) == 1

        await pilot.press("h")
        await pilot.pause(0.2)

        assert len(app.screen.query(HelpPanel)) == 0


if __name__ == "__main__":
    # Run tests with pytest
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest", __file__, "-v", "-s"],
        capture_output=False
    )
    sys.exit(result.returncode)
