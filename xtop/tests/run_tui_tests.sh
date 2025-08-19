#!/bin/bash
# Run TUI tests for XTOP

set -e

echo "========================================="
echo "XTOP TUI Testing Suite"
echo "========================================="
echo ""

# Check for required packages
echo "Checking dependencies..."
python3 -c "import textual" 2>/dev/null || {
    echo "Error: textual not installed. Run: pip install textual"
    exit 1
}

python3 -c "import pytest" 2>/dev/null || {
    echo "Error: pytest not installed. Run: pip install pytest pytest-asyncio"
    exit 1
}

# Run basic TUI tests
echo ""
echo "Running basic TUI tests..."
echo "----------------------------------------"
python3 test_tui_basic.py

# Run CLI mapping tests
echo ""
echo "Running CLI mapping tests..."
echo "----------------------------------------"
python3 test_tui_mapping.py

echo ""
echo "========================================="
echo "All TUI tests completed!"
echo "========================================="