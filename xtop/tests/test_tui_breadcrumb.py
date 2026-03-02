#!/usr/bin/env python3
"""
Test the Textual TUI breadcrumb display
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='/tmp/test_breadcrumb.log'
)

# Import after logging is configured
# from xtop_tui import XTopTUI  # Import would need to be updated for new structure

def test_breadcrumb():
    """Test breadcrumb display"""
    print("Testing Textual TUI breadcrumb display...")
    print("Check /tmp/test_breadcrumb.log for debug output")
    print("")
    print("To test:")
    print("1. The breadcrumb should show at the top in a bordered box")
    print("2. Initial: 'Filters: No filters applied' and 'Path: ...'")
    print("3. Press Enter on a cell to add a filter")
    print("4. The breadcrumb should update to show the filter")
    print("5. Press Backspace to remove the filter")
    print("")
    print("Running: python3 ../xtop-tui.py -d ../out --debuglog /tmp/test_breadcrumb.log")
    
    # You can run the app directly here if needed
    # app = XTopTUI("out", debug_log="/tmp/test_breadcrumb.log")
    # app.run()

if __name__ == "__main__":
    test_breadcrumb()
