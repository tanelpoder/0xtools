#!/bin/bash
# Test script for xtop functionality

echo "=== Testing xtop functionality ==="
echo

echo "1. Basic top view (showing active threads)"
python3 ../xtop.py -d ../out -l 5 --from "2025-07-29T21:47:00" --to "2025-07-29T21:55:00"
echo

echo "2. Summary view"
python3 ../xtop.py -d ../out -q summary -l 5 --from "2025-07-29T21:47:00" --to "2025-07-29T21:55:00" 
echo

echo "3. Filtering by state (showing only running threads)"
python3 ../xtop.py -d ../out -w "STATE='RUN'" -l 5 --from "2025-07-29T21:47:00" --to "2025-07-29T21:55:00"
echo

echo "4. System call latency analysis"
python3 ../xtop.py -d ../out -q sclat -l 10 --from "2025-07-29T21:47:00" --to "2025-07-29T21:55:00"
echo

echo "5. CSV output format"
python3 ../xtop.py -d ../out -o csv -l 3 --from "2025-07-29T21:47:00" --to "2025-07-29T21:55:00"
echo

echo "6. System call latency histogram"
python3 ../xtop.py -d ../out -q sclathist -l 10 --from "2025-07-29T21:47:00" --to "2025-07-29T21:55:00"
echo

echo "=== All tests completed ==="
