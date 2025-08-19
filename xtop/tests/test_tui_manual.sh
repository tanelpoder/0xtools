#!/bin/bash
# Manual test script for TUI with debug logging

echo "Testing xtop TUI with debug logging..."
echo "Data directory: out/"
echo ""

# Test with automatic time range detection
echo "1. Testing with automatic time range detection:"
echo "   python3 ../xtop-tui-simple.py -d ../out -q top --debuglog /tmp/xtop_auto.log"
echo ""

# Test with explicit time range
echo "2. Testing with explicit time range (from data):"
echo "   python3 ../xtop-tui-simple.py -d ../out -q top --from '2025-07-29 21:46:00' --to '2025-07-29 21:56:00' --debuglog /tmp/xtop_manual.log"
echo ""

echo "3. Testing Textual-based TUI:"
echo "   python3 ../xtop-tui.py -d ../out -q top --debuglog /tmp/xtop_textual.log"
echo ""

echo "After running, check the debug logs:"
echo "   cat /tmp/xtop_auto.log"
echo "   cat /tmp/xtop_manual.log"
echo "   cat /tmp/xtop_textual.log"
echo ""
echo "Navigation:"
echo "  - Arrow keys to move around cells (no filtering)"
echo "  - Enter to add WHERE column=value filter at cursor"
echo "  - BACKSPACE to back out one step (remove last filter)"
echo "  - Ctrl+T to create new tab"
echo "  - Ctrl+Tab to switch tabs"
echo "  - q to quit"
echo ""
echo "Filter Breadcrumbs:"
echo "  - Top of screen shows current filters (e.g., USERNAME=postgres AND SYSCALL=pread64)"
echo "  - Each Enter press adds a WHERE column=value filter and refreshes data"
echo "  - Each BACKSPACE press removes the last filter"
echo "  - Data refreshes immediately to show only matching rows"
echo "  - Filtered columns remain visible in the table (showing the filtered value)"