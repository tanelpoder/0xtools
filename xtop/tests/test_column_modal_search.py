#!/usr/bin/env python3
"""
Test the column selection modal search functionality in the TUI.
Verifies that typing filters columns and backspace works correctly.
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


async def test_grouping_modal_search():
    """Test search functionality in GroupingMenuScreen"""
    print("Testing GroupingMenuScreen search functionality...")
    
    # Create app instance with test parameters
    app = XTopApp(
        datadir=XCAPTURE_DATADIR,
        low_time=datetime.fromisoformat("2025-08-03T03:40:00"),
        high_time=datetime.fromisoformat("2025-08-03T04:07:00")
    )
    
    async with app.run_test() as pilot:
        # Wait for app to fully initialize
        await pilot.pause(2)
        
        # Press 'g' to open the grouping menu
        await pilot.press("g")
        await pilot.pause(0.5)
        
        # Verify modal is open
        modal = app.screen_stack[-1]
        assert modal.__class__.__name__ == "GroupingMenuScreen", "GroupingMenuScreen should be open"
        print("✓ GroupingMenuScreen opened")
        
        # Type "hash" to search for hash-related columns
        for char in "hash":
            await pilot.press(char)
            await pilot.pause(0.1)
        
        # Check that search pattern is updated
        assert modal.search_pattern == "hash", f"Search pattern should be 'hash', got '{modal.search_pattern}'"
        print("✓ Search pattern updated to 'hash'")
        
        # Type one more 'h' to make it "hashh"
        await pilot.press("h")
        await pilot.pause(0.1)
        assert modal.search_pattern == "hashh", f"Search pattern should be 'hashh', got '{modal.search_pattern}'"
        print("✓ Search pattern updated to 'hashh'")
        
        # Press backspace to remove the extra 'h'
        await pilot.press("backspace")
        await pilot.pause(0.1)
        assert modal.search_pattern == "hash", f"Search pattern should be back to 'hash', got '{modal.search_pattern}'"
        print("✓ Backspace removed last character, back to 'hash'")
        
        # Clear search with multiple backspaces
        for _ in range(4):
            await pilot.press("backspace")
            await pilot.pause(0.1)
        
        assert modal.search_pattern == "", f"Search pattern should be empty, got '{modal.search_pattern}'"
        print("✓ Search pattern cleared with backspace")
        
        # Press escape to close
        await pilot.press("escape")
        await pilot.pause(0.5)
        
        assert app.screen_stack[-1].__class__.__name__ != "GroupingMenuScreen", "Modal should be closed"
        print("✓ Modal closed with escape")
        
        return True


async def test_latency_modal_search():
    """Test search functionality in LatencyColumnsScreen"""
    print("\nTesting LatencyColumnsScreen search functionality...")
    
    app = XTopApp(
        datadir=XCAPTURE_DATADIR,
        low_time=datetime.fromisoformat("2025-08-03T03:40:00"),
        high_time=datetime.fromisoformat("2025-08-03T04:07:00")
    )
    
    async with app.run_test() as pilot:
        # Wait for app to fully initialize
        await pilot.pause(2)
        
        # Press 'l' to open the latency columns menu
        await pilot.press("l")
        await pilot.pause(0.5)
        
        # Verify modal is open
        modal = app.screen_stack[-1]
        assert modal.__class__.__name__ == "LatencyColumnsScreen", "LatencyColumnsScreen should be open"
        print("✓ LatencyColumnsScreen opened")
        
        # Type "avg" to search for average-related columns
        for char in "avg":
            await pilot.press(char)
            await pilot.pause(0.1)
        
        # Check that search pattern is updated
        assert modal.search_pattern == "avg", f"Search pattern should be 'avg', got '{modal.search_pattern}'"
        print("✓ Search pattern updated to 'avg'")
        
        # Clear one character
        await pilot.press("backspace")
        await pilot.pause(0.1)
        assert modal.search_pattern == "av", f"Search pattern should be 'av', got '{modal.search_pattern}'"
        print("✓ Backspace working correctly")
        
        # Press escape to close
        await pilot.press("escape")
        await pilot.pause(0.5)
        
        assert app.screen_stack[-1].__class__.__name__ != "LatencyColumnsScreen", "Modal should be closed"
        print("✓ Modal closed with escape")
        
        return True


async def main():
    """Run all modal search tests"""
    print("=" * 60)
    print("Column Modal Search Tests")
    print("=" * 60)
    
    try:
        # Test GroupingMenuScreen search
        result1 = await test_grouping_modal_search()
        
        # Test LatencyColumnsScreen search
        result2 = await test_latency_modal_search()
        
        if result1 and result2:
            print("\n" + "=" * 60)
            print("✅ All column modal search tests passed!")
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