#!/bin/bash
# Extended test cases for XTOP with complex column combinations
# Tests various grouping columns with histograms and stack traces

set -e  # Exit on error

DATADIR="../out"
FROM_TIME="2025-08-03T03:40:00"
TO_TIME="2025-08-03T04:07:00"

echo "========================================="
echo "XTOP Extended Test Suite"
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

# Test 1: Username + EXE with syscall histogram
run_test "Username + EXE with syscall histogram" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'USERNAME,EXE' -l 'SCLAT_HISTOGRAM,sc.p50_us,sc.p99_us' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 2: State + Filename patterns with I/O histogram
run_test "State + Filename patterns with I/O histogram" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'STATE,FILENAMESUM,FEXT' -l 'IOLAT_HISTOGRAM,io.p95_us' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 3: Kernel stack traces with syscall latency
run_test "Kernel stacks with syscall latency" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'KSTACK_CURRENT_FUNC,SYSCALL' -l 'sc.min_lat_us,sc.avg_lat_us,sc.max_lat_us,sc.p999_us' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 4: User stack traces with both histograms
run_test "User stacks with dual histograms" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'USTACK_CURRENT_FUNC,STATE' -l 'SCLAT_HISTOGRAM,IOLAT_HISTOGRAM' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 5: Combined kernel and user stacks
run_test "Combined kernel and user stacks" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'KSTACK_CURRENT_FUNC,USTACK_CURRENT_FUNC,COMM2' -l 'sc.p50_us,sc.p95_us' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 6: Device names with I/O percentiles and histogram
run_test "Device analysis with I/O metrics" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'devname,STATE,USERNAME' -l 'io.min_lat_us,io.avg_lat_us,io.p50_us,io.p95_us,io.p99_us,io.p999_us,IOLAT_HISTOGRAM' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 7: Extra info (connection) with syscall histogram
run_test "Connection info with syscall histogram" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'CONNECTION,SYSCALL,STATE' -l 'SCLAT_HISTOGRAM,sc.avg_lat_us' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 8: Hash-based stack grouping with percentiles
run_test "Stack hashes with percentiles" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'KSTACK_HASH,STATE' -l 'sc.p50_us,sc.p75_us,sc.p90_us,sc.p95_us,sc.p99_us' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 9: Full stack with filename patterns
run_test "Full stack with file patterns" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'KSTACK_CURRENT_FUNC,FILENAMESUM,FEXT' -l 'sc.avg_lat_us,SCLAT_HISTOGRAM' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 10: Complex multi-dimensional grouping
run_test "Complex multi-dimensional grouping" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'STATE,USERNAME,COMM2,SYSCALL,KSTACK_CURRENT_FUNC' -l 'sc.min_lat_us,sc.avg_lat_us,sc.max_lat_us,SCLAT_HISTOGRAM' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 11: BONUS - Test with WHERE clause and stacks
run_test "Filtered query with stacks" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'KSTACK_CURRENT_FUNC,USTACK_CURRENT_FUNC' -l 'sc.p99_us' -w \"STATE = 'SLEEP'\" --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

# Test 12: BONUS - Test peek functionality with histograms
run_test "Peek test with histograms" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'STATE,SYSCALL' -l 'SCLAT_HISTOGRAM,IOLAT_HISTOGRAM' --peek --from '$FROM_TIME' --to '$TO_TIME' --limit 2 --format simple"

# Test 13: BONUS - All computed columns together
run_test "All computed columns" \
    "python3 ../xtop-test.py -d $DATADIR  -g 'FILENAMESUM,FEXT,COMM2,CONNECTION' --from '$FROM_TIME' --to '$TO_TIME' --limit 5 --format simple"

echo "========================================="
echo "All extended tests passed successfully!"
echo "========================================="