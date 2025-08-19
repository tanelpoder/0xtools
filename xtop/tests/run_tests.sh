#!/bin/bash
# Automated test cases for XTOP
# Run various queries to ensure they work correctly

set -e  # Exit on error

DATADIR="../out"
FROM_TIME="2025-08-03T03:40:00"
TO_TIME="2025-08-03T04:07:00"

echo "========================================="
echo "XTOP Automated Test Suite"
echo "========================================="
echo "Data directory: $DATADIR"
echo "Time range: $FROM_TIME to $TO_TIME"
echo ""

# Function to run a test
run_test() {
    local test_name="$1"
    local cmd="$2"
    
    echo "----------------------------------------"
    echo "TEST: $test_name"
    echo "CMD: $cmd"
    echo ""
    
    if eval "$cmd"; then
        echo "✓ Test passed"
    else
        echo "✗ Test failed with exit code $?"
        exit 1
    fi
    echo ""
}

# Test 1: Basic dynamic query
run_test "Basic dynamic query" \
    "python3 ../xtop-test.py -d $DATADIR  --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 2: Dynamic query with custom group columns
run_test "Dynamic with custom GROUP BY" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'STATE,USERNAME,COMM' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 3: Dynamic query with computed columns
run_test "Dynamic with computed columns" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'STATE,FILENAMESUM,COMM2' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 4: Dynamic query with syscall latency
run_test "Dynamic with syscall latency percentiles" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'STATE,SYSCALL' -l 'sc.min_lat_us,sc.avg_lat_us,sc.max_lat_us,sc.p95_us,sc.p99_us' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 5: Dynamic query with I/O latency
run_test "Dynamic with I/O latency percentiles" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'STATE,EXE' -l 'io.min_lat_us,io.avg_lat_us,io.max_lat_us' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 6: Dynamic query with histogram
run_test "Dynamic with syscall latency histogram" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'STATE,SYSCALL' -l 'SCLAT_HISTOGRAM' --from '$FROM_TIME' --to '$TO_TIME' --limit 3 --format simple"

# Test 7: Stack traces
run_test "Dynamic with kernel stack traces" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'STATE,KSTACK_CURRENT_FUNC,KSTACK_HASH' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 8: Mixed stack traces
run_test "Dynamic with both kernel and user stacks" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'STATE,KSTACK_CURRENT_FUNC,USTACK_CURRENT_FUNC' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 9: WHERE clause filtering
run_test "Dynamic with WHERE clause" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'STATE,COMM' -w \"STATE = 'Running'\" --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 10: Peek functionality for histograms
run_test "Dynamic with histogram peek" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'STATE,SYSCALL' -l 'SCLAT_HISTOGRAM' --peek --from '$FROM_TIME' --to '$TO_TIME' --limit 2 --format simple"

# Test 11: Complex query with multiple features
run_test "Complex query with multiple features" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'STATE,USERNAME,COMM2,SYSCALL' -l 'sc.p95_us,sc.p99_us,SCLAT_HISTOGRAM' -w \"STATE IN ('Running', 'Disk (Uninterruptible)')\" --from '$FROM_TIME' --to '$TO_TIME' --limit 3 --format simple"

# Test 12: I/O focused query with device names
run_test "I/O query with device names" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'STATE,devname' -l 'io.avg_lat_us,IOLAT_HISTOGRAM' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

echo "========================================="
echo "All tests passed successfully!"
echo "========================================="