#!/usr/bin/env python3
"""
Unified test runner for xtop.
Consolidates all test suites and provides consistent test execution.
"""

import sys
import os
import time
import json
import subprocess
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime


class TestSuite:
    """Represents a test suite"""
    
    def __init__(self, name: str, script: str, description: str):
        self.name = name
        self.script = script
        self.description = description
        self.passed = False
        self.duration = 0.0
        self.output = ""
        self.error = ""


class UnifiedTestRunner:
    """Unified test runner for all xtop tests"""
    
    # ANSI color codes
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    
    def __init__(self, verbose: bool = False, parallel: bool = False):
        """Initialize the test runner
        
        Args:
            verbose: Show detailed output
            parallel: Run tests in parallel
        """
        self.verbose = verbose
        self.parallel = parallel
        self.test_dir = Path(__file__).parent
        self.results = {}
        
        # Define test suites
        self.suites = [
            TestSuite("basic", "./run_tests.sh", "Basic functionality tests"),
            TestSuite("extended", "./run_extended_tests.sh", "Extended query tests"),
            TestSuite("tui", "./run_tui_tests.sh", "Terminal UI tests"),
            TestSuite("before-after", "python3 run_before_after_tests.py", "Comparison tests"),
        ]
    
    def print_header(self) -> None:
        """Print test runner header"""
        print(f"{self.BOLD}{self.BLUE}{'=' * 60}{self.RESET}")
        print(f"{self.BOLD}{self.BLUE}{'XTOP UNIFIED TEST RUNNER':^60}{self.RESET}")
        print(f"{self.BOLD}{self.BLUE}{'=' * 60}{self.RESET}")
        print()
    
    def print_suite_header(self, suite: TestSuite) -> None:
        """Print header for a test suite"""
        print(f"\n{self.BOLD}--------------------------------------------------{self.RESET}")
        print(f"{self.BOLD}Running: {suite.name} - {suite.description}{self.RESET}")
        print(f"{self.BOLD}--------------------------------------------------{self.RESET}")
    
    def run_suite(self, suite: TestSuite) -> bool:
        """Run a single test suite
        
        Args:
            suite: Test suite to run
            
        Returns:
            True if suite passed
        """
        start_time = time.time()
        
        try:
            # Change to test directory
            original_dir = os.getcwd()
            os.chdir(self.test_dir)
            
            # Run the test
            result = subprocess.run(
                suite.script,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout
            )
            
            suite.output = result.stdout
            suite.error = result.stderr
            suite.passed = result.returncode == 0
            
            os.chdir(original_dir)
            
        except subprocess.TimeoutExpired:
            suite.error = "Test suite timed out after 120 seconds"
            suite.passed = False
        except Exception as e:
            suite.error = str(e)
            suite.passed = False
        
        suite.duration = time.time() - start_time
        
        # Print result
        if suite.passed:
            print(f"{self.GREEN}✓ {suite.name} completed in {suite.duration:.2f}s{self.RESET}")
        else:
            print(f"{self.RED}✗ {suite.name} failed after {suite.duration:.2f}s{self.RESET}")
            if self.verbose and suite.error:
                print(f"{self.RED}Error: {suite.error}{self.RESET}")
        
        return suite.passed
    
    def run_all_suites(self, suites: Optional[List[str]] = None) -> bool:
        """Run all test suites
        
        Args:
            suites: Specific suites to run (None for all)
            
        Returns:
            True if all suites passed
        """
        # Filter suites if specific ones requested
        suites_to_run = self.suites
        if suites:
            suites_to_run = [s for s in self.suites if s.name in suites]
        
        all_passed = True
        
        for suite in suites_to_run:
            self.print_suite_header(suite)
            passed = self.run_suite(suite)
            all_passed = all_passed and passed
            self.results[suite.name] = suite
        
        return all_passed
    
    def run_quick_test(self) -> bool:
        """Run a quick smoke test
        
        Returns:
            True if test passed
        """
        print(f"{self.BOLD}Running quick smoke test...{self.RESET}")
        
        try:
            # Run a simple xtop command
            result = subprocess.run(
                "python3 ../xtop-test.py -d ../out --from '2025-08-03T03:40:00' "
                "--to '2025-08-03T04:07:00' --limit 5 --format simple",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
                cwd=self.test_dir
            )
            
            if result.returncode == 0:
                print(f"{self.GREEN}✓ Quick test passed{self.RESET}")
                return True
            else:
                print(f"{self.RED}✗ Quick test failed{self.RESET}")
                if self.verbose:
                    print(f"Error: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"{self.RED}✗ Quick test failed: {e}{self.RESET}")
            return False
    
    def print_summary(self) -> None:
        """Print test results summary"""
        print(f"\n{self.BOLD}{self.BLUE}{'=' * 60}{self.RESET}")
        print(f"{self.BOLD}{self.BLUE}{'TEST RESULTS SUMMARY':^60}{self.RESET}")
        print(f"{self.BOLD}{self.BLUE}{'=' * 60}{self.RESET}")
        print()
        
        # Summary table
        print(f"{'Test Suite':<20} {'Result':<10} {'Duration':<10}")
        print("-" * 40)
        
        total_duration = 0.0
        passed_count = 0
        failed_count = 0
        
        for name, suite in self.results.items():
            status = f"{self.GREEN}PASSED{self.RESET}" if suite.passed else f"{self.RED}FAILED{self.RESET}"
            print(f"{suite.name:<20} {status:<20} {suite.duration:>8.2f}s")
            total_duration += suite.duration
            
            if suite.passed:
                passed_count += 1
            else:
                failed_count += 1
        
        print("=" * 40)
        print(f"Total: {len(self.results)} suites")
        print(f"{self.GREEN}Passed: {passed_count}{self.RESET}")
        if failed_count > 0:
            print(f"{self.RED}Failed: {failed_count}{self.RESET}")
        print(f"\nTotal time: {total_duration:.2f} seconds")
        
        # Overall result
        if failed_count == 0:
            print(f"\n{self.GREEN}{self.BOLD}ALL TESTS PASSED! 🎉{self.RESET}")
        else:
            print(f"\n{self.RED}{self.BOLD}SOME TESTS FAILED{self.RESET}")
    
    def save_results(self, output_file: str = "test_results.json") -> None:
        """Save test results to JSON file
        
        Args:
            output_file: Output file path
        """
        results_data = {
            'timestamp': datetime.now().isoformat(),
            'suites': {}
        }
        
        for name, suite in self.results.items():
            results_data['suites'][name] = {
                'passed': suite.passed,
                'duration': suite.duration,
                'description': suite.description
            }
        
        output_path = self.test_dir / output_file
        with open(output_path, 'w') as f:
            json.dump(results_data, f, indent=2)
        
        print(f"\nResults saved to: {output_path}")
    
    def run_coverage_analysis(self) -> None:
        """Run code coverage analysis"""
        print(f"\n{self.BOLD}Running coverage analysis...{self.RESET}")
        
        try:
            # Run with coverage
            result = subprocess.run(
                "python3 -m coverage run --source=.. -m pytest . -q",
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.test_dir
            )
            
            # Generate report
            subprocess.run(
                "python3 -m coverage report",
                shell=True,
                cwd=self.test_dir
            )
            
            print(f"{self.GREEN}✓ Coverage analysis complete{self.RESET}")
            
        except Exception as e:
            print(f"{self.YELLOW}⚠ Coverage analysis not available: {e}{self.RESET}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Unified test runner for xtop',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'suite',
        nargs='?',
        choices=['all', 'basic', 'extended', 'tui', 'before-after', 'quick'],
        default='all',
        help='Test suite to run (default: all)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show detailed output'
    )
    
    parser.add_argument(
        '--parallel',
        action='store_true',
        help='Run tests in parallel (experimental)'
    )
    
    parser.add_argument(
        '--coverage',
        action='store_true',
        help='Run with code coverage analysis'
    )
    
    parser.add_argument(
        '--save-results',
        action='store_true',
        help='Save results to JSON file'
    )
    
    args = parser.parse_args()
    
    # Create runner
    runner = UnifiedTestRunner(verbose=args.verbose, parallel=args.parallel)
    
    # Print header
    runner.print_header()
    
    # Run tests
    if args.suite == 'quick':
        success = runner.run_quick_test()
    elif args.suite == 'all':
        success = runner.run_all_suites()
    else:
        success = runner.run_all_suites([args.suite])
    
    # Print summary
    if args.suite != 'quick':
        runner.print_summary()
    
    # Save results if requested
    if args.save_results and runner.results:
        runner.save_results()
    
    # Run coverage if requested
    if args.coverage:
        runner.run_coverage_analysis()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()