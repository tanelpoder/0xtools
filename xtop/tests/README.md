# XTOP Test Infrastructure

## Overview

The XTOP test infrastructure has been streamlined and simplified to provide reliable, maintainable testing with a single entry point.

## Quick Start

```bash
# Set data directory (or use environment variable)
export XCAPTURE_DATADIR=/path/to/xcapture/out

# Run all tests
./run_tests.py

# Run specific test suite
./run_tests.py basic
./run_tests.py latency
./run_tests.py stack
./run_tests.py advanced
./run_tests.py format
./run_tests.py schema
./run_tests.py ui

# Run with verbose output
./run_tests.py -v

# Save results to JSON
./run_tests.py --save
```

## Test Structure

### Main Components

1. **run_tests.py** - Main entry point (in xtop directory)
2. **tests/test_runner.py** - Core test runner implementation
3. **xtop-test.py** - CLI testing interface (no TUI)

### Test Suites

The test infrastructure is organized into seven logical test suites:

#### 1. Basic Tests
- Basic dynamic queries
- GROUP BY operations
- Computed columns (FILENAMESUM, COMM2, etc.)
- WHERE clause filtering
- Time bucket columns (HH, MI, SS, S10)

#### 2. Latency Tests
- System call latency percentiles (sc.p50_us, sc.p95_us, etc.)
- I/O latency percentiles (io.min_lat_us, io.avg_lat_us, etc.)
- System call histograms (SCLAT_HISTOGRAM)
- I/O histograms (IOLAT_HISTOGRAM)

#### 3. Stack Tests
- Kernel stack traces (KSTACK_CURRENT_FUNC)
- User stack traces (USTACK_CURRENT_FUNC)
- Stack hashes (KSTACK_HASH, USTACK_HASH)

#### 4. Advanced Tests
- Complex multi-dimensional grouping
- Device name resolution (devname)
- Connection info extraction (CONNECTION from extra_info)
- File extension analysis (FEXT)

#### 5. Format Tests
- Display formatter helpers (core.display)
- Navigation filter summaries and breadcrumbs
- CLI histogram formatting and empty-result messaging

#### 6. Schema Tests
- QueryBuilder schema fallbacks when columns are missing
- DuckDB schema discovery resilience

#### 7. UI Tests
- Textual help panel toggle in headless mode
- Peek modal smoke test using the Textual pilot

## Environment Configuration

### Required Environment Variable

```bash
export XCAPTURE_DATADIR=/path/to/xcapture/out
```

This variable points to the directory containing xcapture CSV files:
- `xcapture_samples_*.csv`
- `xcapture_syscend_*.csv`
- `xcapture_iorqend_*.csv`
- `xcapture_kstacks_*.csv`
- `xcapture_ustacks_*.csv`

### Time Range

The test runner automatically uses the appropriate time range based on available data.
Default: `2025-08-11T16:25:00` to `2025-08-11T17:05:00`

## Test Results

### Console Output

Tests show real-time progress with color-coded results:
- ✅ Green: Test passed
- ❌ Red: Test failed
- Duration for each test

### JSON Output

Use `--save` to generate `test_results.json` with detailed information:
- Test names and descriptions
- Pass/fail status
- Execution times
- Error messages (if any)

## Adding New Tests

To add new tests, edit `test_runner.py` and add test cases to the appropriate suite:

```python
def create_basic_suite(self) -> TestSuite:
    suite = TestSuite("Basic Tests", "Core functionality tests")
    
    # Add your test
    suite.add_test(TestCase(
        name="my_test",
        description="My new test",
        command=f"{base_cmd} -g 'new,columns' --limit 5"
    ))
    
    return suite
```

## Troubleshooting

### Common Issues

1. **Data directory not found**
   - Ensure XCAPTURE_DATADIR points to valid xcapture output
   - Check that CSV files exist in the directory

2. **Time range errors**
   - Verify data exists for the configured time range
   - Update `from_time` and `to_time` in test_runner.py if needed

3. **Test failures**
   - Run with `-v` for detailed error messages
   - Check test_results.json for complete error output

### Debug Mode

For debugging specific tests:

```bash
# Run single test suite with verbose output
./run_tests.py basic -v

# Check the generated commands
python3 tests/test_runner.py -v 2>&1 | grep "python3"
```

## Legacy Test Files (Deprecated)

The following test files have been replaced by the new infrastructure:
- run_tests.sh → use run_tests.py
- run_extended_tests.sh → use run_tests.py advanced
- run_all_tests.py → use run_tests.py
- run_before_after_tests.py → integrated into test_runner.py
- Various individual test scripts → consolidated into test suites

## Benefits of New Infrastructure

1. **Single Entry Point**: One command to run all tests
2. **Consistent Output**: Standardized reporting across all tests
3. **Better Error Handling**: Proper timeout and error detection
4. **JSON Export**: Machine-readable test results
5. **Maintainable**: All tests in one Python file
6. **Environment Aware**: Respects XCAPTURE_DATADIR
7. **Fast**: Parallel execution capability (future enhancement)

## Future Enhancements

- [ ] Parallel test execution
- [ ] Performance benchmarking
- [ ] Coverage reporting
- [ ] Integration with CI/CD
- [ ] Custom test configurations
- [ ] Regression test comparisons
