#!/usr/bin/env python3
"""
Test to verify that modal key events don't propagate to parent screens.
This specifically tests the fix for the ENTER key propagation issue.
"""

import sys
import os
import asyncio
from pathlib import Path
import importlib.util

# Add parent directory to path BEFORE any imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Set data directory from environment variable or use default
XCAPTURE_DATADIR = os.environ.get('XCAPTURE_DATADIR', '/home/tanel/dev/0xtools-next/xcapture/out')
os.environ['XTOP_DATADIR'] = XCAPTURE_DATADIR

from textual.pilot import Pilot
from textual.keys import Keys
from core.query_engine import QueryParams
from datetime import datetime

# Import the main TUI app using importlib (standard pattern for test code)
spec = importlib.util.spec_from_file_location(
    "xtop_tui", 
    Path(__file__).parent.parent / "xtop-tui.py"
)
module = importlib.util.module_from_spec(spec)
module.__file__ = str(Path(__file__).parent.parent / "xtop-tui.py")
spec.loader.exec_module(module)
XTopApp = module.XTopTUI


async def test_grouping_modal_enter_key():
    """Test that ENTER in GroupingMenuScreen doesn't propagate to parent"""
    print("Testing GroupingMenuScreen ENTER key event propagation...")
    
    # Create app instance with test parameters
    app = XTopApp(
        datadir=XCAPTURE_DATADIR,
        low_time=datetime.fromisoformat("2025-08-03T03:40:00"),
        high_time=datetime.fromisoformat("2025-08-03T04:07:00")
    )
    
    async with app.run_test() as pilot:
        # Wait for app to fully initialize
        await pilot.pause(2)
        
        # Get the initial navigation state
        initial_history = len(app.navigation.history)
        print(f"Initial navigation history: {initial_history}")
        
        # Press 'g' to open the grouping menu
        await pilot.press("g")
        await pilot.pause(0.5)
        
        # Verify modal is open
        assert app.screen_stack[-1].__class__.__name__ == "GroupingMenuScreen", "GroupingMenuScreen should be open"
        print("✓ GroupingMenuScreen opened")
        
        # Press ENTER to apply selection (with default columns)
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        # Verify modal is closed
        assert app.screen_stack[-1].__class__.__name__ != "GroupingMenuScreen", "GroupingMenuScreen should be closed"
        print("✓ GroupingMenuScreen closed after ENTER")
        
        # Check that navigation didn't drill down (history should be same)
        final_history = len(app.navigation.history)
        print(f"Final navigation history: {final_history}")
        
        # The number of history items should remain the same
        # If ENTER propagated, it would have added to history
        assert final_history == initial_history, f"Navigation should not have changed (expected {initial_history}, got {final_history})"
        print("✓ ENTER key did not propagate to parent - no drill down occurred")
        
        return True


async def test_filter_modal_enter_key():
    """Test that option selection in FilterMenuScreen doesn't propagate"""
    print("\nTesting FilterMenuScreen event propagation...")
    
    app = XTopApp(
        datadir=XCAPTURE_DATADIR,
        low_time=datetime.fromisoformat("2025-08-03T03:40:00"),
        high_time=datetime.fromisoformat("2025-08-03T04:07:00")
    )
    
    async with app.run_test() as pilot:
        # Wait for app to fully initialize
        await pilot.pause(2)
        
        # Get initial state
        initial_history = len(app.navigation.history)
        print(f"Initial navigation history: {initial_history}")
        
        # Press SPACE to open filter menu (on first cell)
        await pilot.press("space")
        await pilot.pause(0.5)
        
        # Verify modal is open
        assert app.screen_stack[-1].__class__.__name__ == "FilterMenuScreen", "FilterMenuScreen should be open"
        print("✓ FilterMenuScreen opened")
        
        # Press ENTER to select the include option
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        # Verify modal is closed
        assert app.screen_stack[-1].__class__.__name__ != "FilterMenuScreen", "FilterMenuScreen should be closed"
        print("✓ FilterMenuScreen closed after selection")
        
        # Check navigation - filter adds to history
        final_history = len(app.navigation.history)
        print(f"Final navigation history: {final_history}")
        
        # Filter action should add exactly one history item
        assert final_history == initial_history + 1, f"Filter should add one history item (expected {initial_history + 1}, got {final_history})"
        print("✓ Filter applied correctly - one history item added as expected")
        
        return True


async def test_latency_columns_modal():
    """Test that ENTER in LatencyColumnsScreen doesn't propagate"""
    print("\nTesting LatencyColumnsScreen ENTER key event propagation...")
    
    app = XTopApp(
        datadir=XCAPTURE_DATADIR,
        low_time=datetime.fromisoformat("2025-08-03T03:40:00"),
        high_time=datetime.fromisoformat("2025-08-03T04:07:00")
    )
    
    async with app.run_test() as pilot:
        # Wait for app to fully initialize
        await pilot.pause(2)
        
        # Get initial state
        initial_history = len(app.navigation.history)
        print(f"Initial navigation history: {initial_history}")
        
        # Press 'l' to open latency columns menu
        await pilot.press("l")
        await pilot.pause(0.5)
        
        # Verify modal is open
        assert app.screen_stack[-1].__class__.__name__ == "LatencyColumnsScreen", "LatencyColumnsScreen should be open"
        print("✓ LatencyColumnsScreen opened")
        
        # Press ENTER to apply selection
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        # Verify modal is closed
        assert app.screen_stack[-1].__class__.__name__ != "LatencyColumnsScreen", "LatencyColumnsScreen should be closed"
        print("✓ LatencyColumnsScreen closed after ENTER")
        
        # Check that navigation didn't change
        final_history = len(app.navigation.history)
        print(f"Final navigation history: {final_history}")
        
        assert final_history == initial_history, f"Navigation should not have changed (expected {initial_history}, got {final_history})"
        print("✓ ENTER key did not propagate to parent - no drill down occurred")
        
        return True


async def main():
    """Run all modal event propagation tests"""
    print("=" * 60)
    print("Modal Event Propagation Tests")
    print("=" * 60)
    
    try:
        # Test GroupingMenuScreen
        result1 = await test_grouping_modal_enter_key()
        
        # Test FilterMenuScreen
        result2 = await test_filter_modal_enter_key()
        
        # Test LatencyColumnsScreen
        result3 = await test_latency_columns_modal()
        
        if result1 and result2 and result3:
            print("\n" + "=" * 60)
            print("✅ All modal event propagation tests passed!")
            print("=" * 60)
            return 0
        else:
            print("\n❌ Some tests failed")
            return 1
            
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)