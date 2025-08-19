#!/usr/bin/env python3
"""
Standardized test runner for XTOP
Single entry point for all test suites

Usage:
    python3 run_all_tests.py           # Run all tests
    python3 run_all_tests.py basic     # Run only basic tests
    python3 run_all_tests.py extended  # Run only extended tests
    python3 run_all_tests.py tui       # Run only TUI tests
    python3 run_all_tests.py before-after  # Run before/after comparison tests
"""

import sys
import subprocess
import os
from pathlib import Path
import time
import argparse
from typing import List, Tuple

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

class TestRunner:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results = []
        self.start_time = time.time()
        
    def print_header(self, title: str):
        """Print a formatted section header"""
        print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
        print(f"{BOLD}{BLUE}{title:^60}{RESET}")
        print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")
    
    def print_subheader(self, title: str):
        """Print a formatted subsection header"""
        print(f"\n{BOLD}{'-'*50}{RESET}")
        print(f"{BOLD}{title}{RESET}")
        print(f"{BOLD}{'-'*50}{RESET}")
    
    def run_command(self, cmd: List[str], description: str, timeout: int = 60) -> Tuple[bool, str]:
        """Run a command and return success status and output"""
        try:
            if self.verbose:
                print(f"Running: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=Path(__file__).parent
            )
            
            output = result.stdout + result.stderr
            success = result.returncode == 0
            
            if self.verbose or not success:
                print(output)
            
            return success, output
            
        except subprocess.TimeoutExpired:
            return False, f"Command timed out after {timeout} seconds"
        except Exception as e:
            return False, str(e)
    
    def run_basic_tests(self) -> bool:
        """Run basic test suite"""
        self.print_subheader("Running Basic Tests (run_tests.sh)")
        success, output = self.run_command(
            ["bash", "run_tests.sh"],
            "Basic test suite",
            timeout=60
        )
        
        if success:
            # Count passed tests from output
            passed = output.count("✓ Test passed")
            print(f"{GREEN}✓ Basic tests completed: {passed} tests passed{RESET}")
        else:
            print(f"{RED}✗ Basic tests failed{RESET}")
            
        self.results.append(("Basic Tests", success))
        return success
    
    def run_extended_tests(self) -> bool:
        """Run extended test suite"""
        self.print_subheader("Running Extended Tests (run_extended_tests.sh)")
        success, output = self.run_command(
            ["bash", "run_extended_tests.sh"],
            "Extended test suite",
            timeout=60
        )
        
        if success:
            passed = output.count("✓ Test passed")
            print(f"{GREEN}✓ Extended tests completed: {passed} tests passed{RESET}")
        else:
            print(f"{RED}✗ Extended tests failed{RESET}")
            
        self.results.append(("Extended Tests", success))
        return success
    
    def run_tui_tests(self) -> bool:
        """Run TUI headless tests using pytest"""
        self.print_subheader("Running TUI Tests (pytest)")
        
        # Check if pytest is installed
        check_cmd = ["python3", "-c", "import pytest"]
        success, _ = self.run_command(check_cmd, "Check pytest", timeout=5)
        
        if not success:
            print(f"{YELLOW}⚠ pytest not installed. Install with: pip install pytest pytest-asyncio{RESET}")
            self.results.append(("TUI Tests", False))
            return False
        
        # Run pytest for TUI tests
        success, output = self.run_command(
            ["python3", "-m", "pytest", "test_tui_basic.py", "-v", "--tb=short"],
            "TUI basic tests",
            timeout=30
        )
        
        if success:
            print(f"{GREEN}✓ TUI tests completed{RESET}")
        else:
            print(f"{YELLOW}⚠ TUI tests had issues (may need Textual installed){RESET}")
            
        self.results.append(("TUI Tests", success))
        return success
    
    def run_before_after_tests(self) -> bool:
        """Run comprehensive before/after comparison tests"""
        self.print_subheader("Running Before/After Tests")
        success, output = self.run_command(
            ["python3", "run_before_after_tests.py"],
            "Before/after comparison tests",
            timeout=120
        )
        
        if success:
            print(f"{GREEN}✓ Before/after tests completed{RESET}")
        else:
            print(f"{RED}✗ Before/after tests failed{RESET}")
            
        self.results.append(("Before/After Tests", success))
        return success
    
    def run_single_test(self) -> bool:
        """Run a single quick test to verify setup"""
        self.print_subheader("Running Quick Verification Test")
        success, output = self.run_command(
            ["python3", "../xtop-test.py", "-d", "../out", "-q", "dynamic", 
             "--limit", "1", "--format", "simple"],
            "Quick verification",
            timeout=10
        )
        
        if success and "samples" in output:
            print(f"{GREEN}✓ Quick test passed - setup is working{RESET}")
        else:
            print(f"{RED}✗ Quick test failed - check your setup{RESET}")
            
        return success
    
    def print_summary(self):
        """Print test results summary"""
        self.print_header("TEST RESULTS SUMMARY")
        
        total = len(self.results)
        passed = sum(1 for _, success in self.results if success)
        failed = total - passed
        
        print(f"{'Test Suite':<20} {'Result':<10}")
        print("-" * 30)
        
        for name, success in self.results:
            status = f"{GREEN}PASSED{RESET}" if success else f"{RED}FAILED{RESET}"
            print(f"{name:<20} {status}")
        
        print("\n" + "=" * 40)
        print(f"Total: {total} suites")
        print(f"{GREEN}Passed: {passed}{RESET}")
        if failed > 0:
            print(f"{RED}Failed: {failed}{RESET}")
        
        elapsed = time.time() - self.start_time
        print(f"\nTotal time: {elapsed:.2f} seconds")
        
        if failed == 0:
            print(f"\n{GREEN}{BOLD}ALL TESTS PASSED! 🎉{RESET}")
            return 0
        else:
            print(f"\n{RED}{BOLD}SOME TESTS FAILED{RESET}")
            return 1


def main():
    parser = argparse.ArgumentParser(
        description="XTOP Standardized Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 run_all_tests.py              # Run all test suites
  python3 run_all_tests.py basic        # Run only basic tests
  python3 run_all_tests.py extended     # Run only extended tests
  python3 run_all_tests.py tui          # Run only TUI tests
  python3 run_all_tests.py quick        # Run a quick verification test
  python3 run_all_tests.py -v           # Run all tests with verbose output
        """
    )
    
    parser.add_argument(
        'suite',
        nargs='?',
        default='all',
        choices=['all', 'basic', 'extended', 'tui', 'before-after', 'quick'],
        help='Test suite to run (default: all)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show detailed output from tests'
    )
    
    args = parser.parse_args()
    
    # Change to tests directory
    os.chdir(Path(__file__).parent)
    
    runner = TestRunner(verbose=args.verbose)
    
    runner.print_header(f"XTOP TEST RUNNER - {args.suite.upper()}")
    
    # Run selected test suites
    if args.suite == 'quick':
        runner.run_single_test()
        return 0
    elif args.suite == 'all':
        runner.run_single_test()  # Quick verification first
        runner.run_basic_tests()
        runner.run_extended_tests()
        runner.run_tui_tests()
        runner.run_before_after_tests()
    elif args.suite == 'basic':
        runner.run_basic_tests()
    elif args.suite == 'extended':
        runner.run_extended_tests()
    elif args.suite == 'tui':
        runner.run_tui_tests()
    elif args.suite == 'before-after':
        runner.run_before_after_tests()
    
    # Print summary and return exit code
    return runner.print_summary()


if __name__ == "__main__":
    sys.exit(main())