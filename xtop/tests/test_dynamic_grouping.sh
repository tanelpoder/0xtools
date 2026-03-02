#!/bin/bash

# Test script for dynamic grouping feature in xtop-tui

# Use XCAPTURE_DATADIR environment variable or default
DATADIR="${XCAPTURE_DATADIR:-/home/tanel/dev/0xtools-next/xcapture/out}"

echo "=== Testing Dynamic Grouping Feature ==="
echo "Data directory: $DATADIR"
echo ""
echo "This test will launch xtop-tui with sclathist query type."
echo "To test dynamic grouping:"
echo "1. Press 'g' to open the grouping menu"
echo "2. Use arrow keys to navigate columns"
echo "3. Press SPACE to toggle column selection"
echo "4. Press ENTER to apply new grouping"
echo "5. Press BACKSPACE to revert grouping changes"
echo ""
echo "Starting in 3 seconds..."
sleep 3

# Launch xtop-tui with test parameters
python3 ../xtop -d "$DATADIR" --from "2025-08-11T16:25:00" --to "2025-08-11T17:05:00" --debuglog test_grouping.log