#!/bin/bash
# Test the fixed Textual TUI

echo "Testing the fixed Textual TUI with breadcrumb display..."
echo ""
echo "Running: ../xtop-tui.py -d ../out -q sclathist --from '2025-07-29T21:47:00' --to '2025-07-29T21:55:00' --debuglog debug.sql"
echo ""
echo "What to test:"
echo "1. The breadcrumb should show at the top in a cyan-bordered box"
echo "2. Initial: 'Filters: No filters applied' and 'Path: ...'"
echo "3. Use arrow keys to navigate the data table"
echo "4. Press Enter on a cell to add a filter"
echo "5. The breadcrumb should update to show the filter"
echo "6. Press Backspace to remove the filter"
echo "7. Press Ctrl+T to create a new tab"
echo "8. Press q to quit"
echo ""
echo "Press Enter to start the TUI..."
read

../xtop-tui.py -d ../out -q sclathist --from '2025-07-29T21:47:00' --to '2025-07-29T21:55:00' --debuglog debug.sql