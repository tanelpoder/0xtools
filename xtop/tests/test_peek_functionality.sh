#!/bin/bash
# Test script to verify cell peek functionality

echo "Testing xtop-tui cell peek functionality..."
echo ""
echo "Instructions:"
echo "1. Navigate to a sclathist or iolathist query using 'q' key"
echo "2. Use arrow keys to navigate to the HISTOGRAM_VIZ column (shows unicode blocks)"
echo "3. Press '?' to peek into the cell and see detailed histogram breakdown"
echo "4. Press ESC or Q to close the modal"
echo "5. Press Ctrl+C to exit the application"
echo ""
echo "Starting xtop-tui..."

cd "$(dirname "$0")"
python3 ../xtop-tui.py ../out/