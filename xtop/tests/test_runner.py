#!/usr/bin/env python3
"""
Streamlined test runner for XTOP
Consolidates all test types into a single, maintainable runner
"""

import sys
import subprocess
import os
from pathlib import Path
import time
import json
from datetime import datetime
from typing import List, Tuple, Dict, Any
import argparse

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'


class TestCase:
    """Represents a single test case"""
    def __init__(self, name: str, description: str, command: str):
        self.name = name
        self.description = description
        self.command = command
        self.passed = False
        self.output = ""
        self.error = ""
        self.duration = 0.0


class TestSuite:
    """Collection of related test cases"""
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.test_cases: List[TestCase] = []
        self.passed = 0
        self.failed = 0
        self.duration = 0.0
    
    def add_test(self, test: TestCase):
        """Add a test case to the suite"""
        self.test_cases.append(test)
    
    def run(self, verbose: bool = False) -> bool:
        """Run all tests in the suite"""
        print(f"\n{BOLD}Running {self.name}{RESET}")
        print("-" * 60)
        
        start_time = time.time()
        self.passed = 0
        self.failed = 0
        
        for test in self.test_cases:
            test_start = time.time()
            
            if verbose:
                print(f"  {test.name}: ", end="", flush=True)
            
            try:
                result = subprocess.run(
                    test.command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=Path(__file__).parent
                )
                
                test.output = result.stdout
                test.error = result.stderr
                test.passed = result.returncode == 0
                
                # Check for specific error patterns that indicate failure
                if "ERROR:" in test.output or "ERROR:" in test.error:
                    if "No files found" not in test.error:  # Ignore missing file errors in test data
                        test.passed = False
                
            except subprocess.TimeoutExpired:
                test.passed = False
                test.error = "Test timed out after 30 seconds"
            except Exception as e:
                test.passed = False
                test.error = str(e)
            
            test.duration = time.time() - test_start
            
            if test.passed:
                self.passed += 1
                if verbose:
                    print(f"{GREEN}✓{RESET} ({test.duration:.2f}s)")
            else:
                self.failed += 1
                if verbose:
                    print(f"{RED}✗{RESET} ({test.duration:.2f}s)")
                    if test.error:
                        print(f"    Error: {test.error[:200]}")
        
        self.duration = time.time() - start_time
        
        # Summary for this suite
        print(f"\n  Results: {GREEN}{self.passed} passed{RESET}, ", end="")
        if self.failed > 0:
            print(f"{RED}{self.failed} failed{RESET}", end="")
        else:
            print(f"0 failed", end="")
        print(f" in {self.duration:.2f}s")
        
        return self.failed == 0


class XtopTestRunner:
    """Main test runner for XTOP"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.suites: List[TestSuite] = []
        self.datadir = os.environ.get('XCAPTURE_DATADIR', '/home/tanel/dev/0xtools-next/xcapture/out')
        self.from_time = "2025-08-11T16:25:00"
        self.to_time = "2025-08-11T17:05:00"
        
        # Check if data directory exists
        if not Path(self.datadir).exists():
            print(f"{YELLOW}Warning: Data directory not found: {self.datadir}{RESET}")
            print(f"Set XCAPTURE_DATADIR environment variable to point to xcapture output")
    
    def create_basic_suite(self) -> TestSuite:
        """Create basic functionality test suite"""
        suite = TestSuite("Basic Tests", "Core functionality tests")
        
        # Base command template
        base_cmd = f"python3 ../xtop-test.py -d {self.datadir} --from '{self.from_time}' --to '{self.to_time}'"
        
        tests = [
            ("basic_query", "Basic dynamic query", 
             f"{base_cmd} --limit 5 --format simple"),
            
            ("group_by", "GROUP BY columns",
             f"{base_cmd} -g 'state,username,comm' --limit 5 --format simple"),
            
            ("computed_cols", "Computed columns",
             f"{base_cmd} -g 'state,filenamesum,comm2' --limit 5 --format simple"),
            
            ("where_clause", "WHERE clause filtering",
             f"{base_cmd} -g 'state,comm' -w \"state IN ('SLEEP', 'RUN')\" --limit 5 --format simple"),
            
            ("time_columns", "Time bucket columns",
             f"{base_cmd} -g 'HH,MI,state' --limit 5 --format simple"),
        ]
        
        for name, desc, cmd in tests:
            suite.add_test(TestCase(name, desc, cmd))
        
        return suite
    
    def create_latency_suite(self) -> TestSuite:
        """Create latency analysis test suite"""
        suite = TestSuite("Latency Tests", "Latency analysis functionality")
        
        base_cmd = f"python3 ../xtop-test.py -d {self.datadir} --from '{self.from_time}' --to '{self.to_time}'"
        
        tests = [
            ("syscall_latency", "System call latency percentiles",
             f"{base_cmd} -g 'state,syscall' -l 'sc.p50_us,sc.p95_us,sc.p99_us' --limit 5 --format simple"),
            
            ("io_latency", "I/O latency percentiles",
             f"{base_cmd} -g 'state,exe' -l 'io.min_lat_us,io.avg_lat_us,io.max_lat_us' --limit 5 --format simple"),
            
            ("syscall_histogram", "System call histogram",
             f"{base_cmd} -g 'state,syscall' -l 'sclat_histogram' --limit 3 --format simple"),
            
            ("io_histogram", "I/O histogram",
             f"{base_cmd} -g 'state' -l 'iolat_histogram' --limit 3 --format simple"),
        ]
        
        for name, desc, cmd in tests:
            suite.add_test(TestCase(name, desc, cmd))
        
        return suite
    
    def create_stack_suite(self) -> TestSuite:
        """Create stack trace test suite"""
        suite = TestSuite("Stack Tests", "Stack trace functionality")
        
        base_cmd = f"python3 ../xtop-test.py -d {self.datadir} --from '{self.from_time}' --to '{self.to_time}'"
        
        tests = [
            ("kernel_stacks", "Kernel stack traces",
             f"{base_cmd} -g 'state,kstack_current_func' --limit 5 --format simple"),
            
            ("user_stacks", "User stack traces",
             f"{base_cmd} -g 'state,ustack_current_func' --limit 5 --format simple"),
            
            ("stack_hashes", "Stack hashes",
             f"{base_cmd} -g 'kstack_hash,state' --limit 5 --format simple"),
        ]
        
        for name, desc, cmd in tests:
            suite.add_test(TestCase(name, desc, cmd))
        
        return suite
    
    def create_advanced_suite(self) -> TestSuite:
        """Create advanced functionality test suite"""
        suite = TestSuite("Advanced Tests", "Complex queries and edge cases")
        
        base_cmd = f"python3 ../xtop-test.py -d {self.datadir} --from '{self.from_time}' --to '{self.to_time}'"
        
        tests = [
            ("complex_grouping", "Complex multi-dimensional grouping",
             f"{base_cmd} -g 'state,username,comm2,syscall' -l 'sc.p95_us' --limit 5 --format simple"),
            
            ("device_names", "Device name resolution",
             f"{base_cmd} -g 'devname,state' -l 'io.avg_lat_us' --limit 5 --format simple"),
            
            ("connection_info", "Connection info from extra_info",
             f"{base_cmd} -g 'connection,state' --limit 5 --format simple"),
            
            ("file_extensions", "File extension analysis",
             f"{base_cmd} -g 'fext,state' --limit 5 --format simple"),
        ]
        
        for name, desc, cmd in tests:
            suite.add_test(TestCase(name, desc, cmd))
        
        return suite

    def create_format_suite(self) -> TestSuite:
        """Create formatting-focused test suite."""
        suite = TestSuite("Format Tests", "Formatting, display, and CLI output checks")

        tests = [
            ("display_utils", "Display formatting helpers",
             "python3 -m pytest test_display_utils.py"),
            ("filter_display", "Navigation filter summaries",
             "python3 -m pytest test_filter_display.py"),
            ("cli_histogram_format", "CLI histogram formatting",
             "python3 -m pytest test_cli_peek.py"),
        ]

        for name, desc, cmd in tests:
            suite.add_test(TestCase(name, desc, cmd))

        return suite

    def create_schema_suite(self) -> TestSuite:
        """Create schema-resilience suite."""
        suite = TestSuite("Schema Tests", "DuckDB schema compatibility checks")

        tests = [
            ("query_builder_schema", "QueryBuilder schema fallbacks",
             "python3 -m pytest test_query_builder_schema.py"),
            ("schema_resilience", "Schema resilience with missing columns",
             "python3 -m pytest test_schema_resilience.py"),
        ]

        for name, desc, cmd in tests:
            suite.add_test(TestCase(name, desc, cmd))

        return suite

    def create_ui_suite(self) -> TestSuite:
        """Create UI/headless Textual suite."""
        suite = TestSuite("UI Tests", "Focused Textual headless checks")

        tests = [
            ("tui_help_panel", "Help panel toggle",
             "python3 -m pytest test_tui_simple.py -k help_panel_toggle -vv"),
            ("tui_peek_flow", "Peek modal smoke test",
             "python3 -m pytest test_tui_basic.py -k peek_functionality -vv"),
        ]

        for name, desc, cmd in tests:
            suite.add_test(TestCase(name, desc, cmd))

        return suite
    
    def run_all(self) -> bool:
        """Run all test suites"""
        print(f"\n{BOLD}{BLUE}{'=' * 60}{RESET}")
        print(f"{BOLD}{BLUE}XTOP Test Runner{RESET}")
        print(f"{BOLD}{BLUE}{'=' * 60}{RESET}")
        print(f"\nData directory: {self.datadir}")
        print(f"Time range: {self.from_time} to {self.to_time}")
        
        # Create test suites
        self.suites = [
            self.create_basic_suite(),
            self.create_latency_suite(),
            self.create_stack_suite(),
            self.create_advanced_suite(),
            self.create_format_suite(),
            self.create_schema_suite(),
            self.create_ui_suite(),
        ]
        
        # Run all suites
        total_passed = 0
        total_failed = 0
        total_duration = 0.0
        
        for suite in self.suites:
            success = suite.run(self.verbose)
            total_passed += suite.passed
            total_failed += suite.failed
            total_duration += suite.duration
        
        # Print summary
        self.print_summary(total_passed, total_failed, total_duration)
        
        return total_failed == 0
    
    def run_suite(self, suite_name: str) -> bool:
        """Run a specific test suite"""
        suite_map = {
            'basic': self.create_basic_suite,
            'latency': self.create_latency_suite,
            'stack': self.create_stack_suite,
            'advanced': self.create_advanced_suite,
            'format': self.create_format_suite,
            'schema': self.create_schema_suite,
            'ui': self.create_ui_suite,
        }
        
        if suite_name not in suite_map:
            print(f"{RED}Unknown suite: {suite_name}{RESET}")
            print(f"Available suites: {', '.join(suite_map.keys())}")
            return False
        
        suite = suite_map[suite_name]()
        return suite.run(self.verbose)
    
    def print_summary(self, passed: int, failed: int, duration: float):
        """Print test results summary"""
        print(f"\n{BOLD}{BLUE}{'=' * 60}{RESET}")
        print(f"{BOLD}Test Summary{RESET}")
        print(f"{BOLD}{BLUE}{'=' * 60}{RESET}")
        
        print(f"\nTotal tests: {passed + failed}")
        print(f"{GREEN}Passed: {passed}{RESET}")
        if failed > 0:
            print(f"{RED}Failed: {failed}{RESET}")
        else:
            print(f"Failed: 0")
        print(f"\nTotal time: {duration:.2f} seconds")
        
        if failed == 0:
            print(f"\n{GREEN}{BOLD}ALL TESTS PASSED! ✅{RESET}")
        else:
            print(f"\n{RED}{BOLD}SOME TESTS FAILED ❌{RESET}")
    
    def save_results(self, filename: str = "test_results.json"):
        """Save test results to JSON file"""
        results = {
            'timestamp': datetime.now().isoformat(),
            'datadir': self.datadir,
            'time_range': f"{self.from_time} to {self.to_time}",
            'suites': {}
        }
        
        for suite in self.suites:
            suite_data = {
                'passed': suite.passed,
                'failed': suite.failed,
                'duration': suite.duration,
                'tests': []
            }
            
            for test in suite.test_cases:
                suite_data['tests'].append({
                    'name': test.name,
                    'passed': test.passed,
                    'duration': test.duration,
                    'error': test.error[:500] if test.error else None
                })
            
            results['suites'][suite.name] = suite_data
        
        output_path = Path(__file__).parent / filename
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\nResults saved to: {output_path}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Streamlined test runner for XTOP',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 test_runner.py              # Run all tests
  python3 test_runner.py basic        # Run basic tests only
  python3 test_runner.py -v           # Verbose output
  python3 test_runner.py --save       # Save results to JSON
        """
    )
    
    parser.add_argument(
        'suite',
        nargs='?',
        choices=['all', 'basic', 'latency', 'stack', 'advanced', 'format', 'schema', 'ui'],
        default='all',
        help='Test suite to run (default: all)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show detailed output'
    )
    
    parser.add_argument(
        '--save',
        action='store_true',
        help='Save results to JSON file'
    )
    
    args = parser.parse_args()
    
    # Create runner
    runner = XtopTestRunner(verbose=args.verbose)
    
    # Run tests
    if args.suite == 'all':
        success = runner.run_all()
    else:
        success = runner.run_suite(args.suite)
    
    # Save results if requested
    if args.save and runner.suites:
        runner.save_results()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
