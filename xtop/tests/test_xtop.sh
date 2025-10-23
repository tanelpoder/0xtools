#!/bin/bash
# Test script for xtop functionality

# Use XCAPTURE_DATADIR environment variable or default
DATADIR="${XCAPTURE_DATADIR:-/home/tanel/dev/0xtools-next/xcapture/out}"

echo "=== Testing xtop functionality ==="
echo "Data directory: $DATADIR"
echo

echo "1. Basic top view (showing active threads)"
python3 ../xtop.py -d "$DATADIR" -l 5 --from "2025-08-11T16:25:00" --to "2025-08-11T17:05:00"
echo

echo "2. Summary view (using GROUP BY for aggregation)"
python3 ../xtop.py -d "$DATADIR" -g "state,username" -l 5 --from "2025-08-11T16:25:00" --to "2025-08-11T17:05:00" 
echo

echo "3. Filtering by state (showing only running threads)"
python3 ../xtop.py -d "$DATADIR" -w "STATE='RUN'" -l 5 --from "2025-08-11T16:25:00" --to "2025-08-11T17:05:00"
echo

echo "4. System call latency analysis (removed - query types no longer supported)"
# python3 ../xtop.py -d "$DATADIR" -q sclat -l 10 --from "2025-08-11T16:25:00" --to "2025-08-11T17:05:00"
echo "Skipped (query types removed in refactoring)"
echo

echo "5. CSV output format"
python3 ../xtop.py -d "$DATADIR" -o csv -l 3 --from "2025-08-11T16:25:00" --to "2025-08-11T17:05:00"
echo

echo "6. System call latency histogram (removed - query types no longer supported)"
# python3 ../xtop.py -d "$DATADIR" -q sclathist -l 10 --from "2025-08-11T16:25:00" --to "2025-08-11T17:05:00"
echo "Skipped (query types removed in refactoring)"
echo

echo "=== All tests completed ==="
