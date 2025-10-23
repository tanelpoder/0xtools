#!/usr/bin/env python3
"""
Test that column selection modals show all columns initially when opened.
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
from textual.widgets import OptionList
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


async def test_grouping_modal_initial_display():
    """Test that GroupingMenuScreen shows all columns initially"""
    print("Testing GroupingMenuScreen initial display...")
    
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
        
        # Check that columns are displayed initially
        try:
            option_list = modal.query_one(OptionList)
            option_count = option_list.option_count
            
            # Should have many columns initially (samples has many fields)
            assert option_count > 10, f"Should show many columns initially, got {option_count}"
            print(f"✓ Shows {option_count} columns initially (all columns visible)")
            
            # Check that search pattern is empty
            assert modal.search_pattern == "", "Search pattern should be empty initially"
            print("✓ Search pattern is empty initially")
            
            # Get search display label
            search_label = modal.query_one("#search-display")
            label_text = search_label.renderable
            assert "Type to search" in str(label_text), f"Should show search instructions, got: {label_text}"
            print("✓ Shows search instructions initially")
            
        except Exception as e:
            print(f"✗ Error checking initial display: {e}")
            return False
        
        # Press escape to close
        await pilot.press("escape")
        await pilot.pause(0.5)
        
        return True


async def test_latency_modal_initial_display():
    """Test that LatencyColumnsScreen shows all columns initially"""
    print("\nTesting LatencyColumnsScreen initial display...")
    
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
        
        # Check that columns are displayed initially
        try:
            option_list = modal.query_one(OptionList)
            option_count = option_list.option_count
            
            # Should have multiple latency columns initially
            assert option_count > 0, f"Should show latency columns initially, got {option_count}"
            print(f"✓ Shows {option_count} latency columns initially")
            
            # Check that search pattern is empty
            assert modal.search_pattern == "", "Search pattern should be empty initially"
            print("✓ Search pattern is empty initially")
            
        except Exception as e:
            print(f"✗ Error checking initial display: {e}")
            return False
        
        # Press escape to close
        await pilot.press("escape")
        await pilot.pause(0.5)
        
        return True


async def main():
    """Run all initial display tests"""
    print("=" * 60)
    print("Column Modal Initial Display Tests")
    print("=" * 60)
    
    try:
        # Test GroupingMenuScreen initial display
        result1 = await test_grouping_modal_initial_display()
        
        # Test LatencyColumnsScreen initial display
        result2 = await test_latency_modal_initial_display()
        
        if result1 and result2:
            print("\n" + "=" * 60)
            print("✅ All initial display tests passed!")
            print("Modals correctly show all columns when first opened.")
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