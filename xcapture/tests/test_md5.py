#!/usr/bin/env python3
"""
Test MD5 hash implementation by:
1. Generating random test strings
2. Computing MD5 hashes using both C and Python implementations
3. Comparing the results
"""
import argparse
import hashlib
import os
import random
import string
import subprocess
import sys
import tempfile
from pathlib import Path

def generate_random_string(min_length, max_length):
    """Generate a random string with length between min_length and max_length"""
    length = random.randint(min_length, max_length)
    chars = string.ascii_letters + string.digits + string.punctuation + " "
    return ''.join(random.choice(chars) for _ in range(length))

def generate_test_strings(count, min_length, max_length, output_file):
    """Generate 'count' test strings with varying lengths and write to file"""
    test_cases = []
    
    # Generate completely random strings
    for _ in range(count - 5):
        test_cases.append(generate_random_string(min_length, max_length))
    
    # Add some edge cases
    test_cases.extend([
        "",                                     # Empty string
        "a" * min_length if min_length > 0 else "a",  # Minimum length with same character
        "a" * max_length,                       # Maximum length with same character
        string.ascii_letters + string.digits,    # Alphanumeric
        "".join(chr(i) for i in range(32, 127)) # ASCII printable characters
    ])
    
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        for test_case in test_cases:
            f.write(f"{test_case}\n")
    
    return len(test_cases)

def compute_python_md5(input_file, output_file):
    """Compute MD5 hashes using Python's hashlib and write to file"""
    with open(input_file, 'r', encoding='utf-8') as infile, \
         open(output_file, 'w', encoding='utf-8') as outfile:
        for line in infile:
            line = line.rstrip('\n')
            md5_hash = hashlib.md5(line.encode('utf-8')).hexdigest()
            outfile.write(f"{md5_hash} {line}\n")

def run_c_md5(input_file, output_file, executable="./md5_test"):
    """Run the C implementation of MD5 hash and capture output"""
    try:
        with open(output_file, 'w', encoding='utf-8') as out:
            subprocess.run(
                [executable, input_file],
                stdout=out,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
    except subprocess.CalledProcessError as e:
        print(f"Error running C MD5 implementation: {e.stderr}", file=sys.stderr)
        sys.exit(1)

def compare_results(file1, file2):
    """Compare two files with MD5 hashes and return differences"""
    with open(file1, 'r', encoding='utf-8') as f1, \
         open(file2, 'r', encoding='utf-8') as f2:
        lines1 = f1.readlines()
        lines2 = f2.readlines()
    
    if len(lines1) != len(lines2):
        return False, f"Files have different number of lines: {len(lines1)} vs {len(lines2)}"
    
    differences = []
    for i, (line1, line2) in enumerate(zip(lines1, lines2), 1):
        if line1.strip() != line2.strip():
            differences.append(f"Line {i}:\n  C:      {line1.strip()}\n  Python: {line2.strip()}")
    
    return len(differences) == 0, differences

def main():
    parser = argparse.ArgumentParser(description='Test MD5 hash implementation')
    parser.add_argument('-n', '--count', type=int, default=100,
                        help='Number of test strings to generate (default: 100)')
    parser.add_argument('--min-length', type=int, default=0,
                        help='Minimum string length (default: 0)')
    parser.add_argument('--max-length', type=int, default=1000,
                        help='Maximum string length (default: 1000)')
    parser.add_argument('--keep-files', action='store_true',
                        help='Keep temporary test files after running')
    parser.add_argument('--exe', type=str, default='./md5_test',
                        help='Path to the C MD5 test executable (default: ./md5_test)')
    
    args = parser.parse_args()
    
    # Ensure the C executable exists
    if not os.path.isfile(args.exe):
        print(f"Error: C executable '{args.exe}' not found. Make sure to compile it first.", file=sys.stderr)
        return 1
    
    # Create temporary directory for test files
    temp_dir = tempfile.mkdtemp()
    input_file = os.path.join(temp_dir, "test_strings.txt")
    c_output = os.path.join(temp_dir, "c_md5_output.txt")
    py_output = os.path.join(temp_dir, "python_md5_output.txt")
    
    try:
        # Step 1: Generate test strings
        print(f"Generating {args.count} test strings...")
        num_strings = generate_test_strings(args.count, args.min_length, args.max_length, input_file)
        print(f"Generated {num_strings} test strings in {input_file}")
        
        # Step 2: Run both implementations
        print("Computing MD5 hashes using Python implementation...")
        compute_python_md5(input_file, py_output)
        
        print("Computing MD5 hashes using C implementation...")
        run_c_md5(input_file, c_output, args.exe)
        
        # Step 3: Compare results
        print("Comparing results...")
        match, differences = compare_results(c_output, py_output)
        
        if match:
            print("SUCCESS: All MD5 hashes match!")
            return 0
        else:
            print("FAILURE: MD5 hash differences found:")
            for diff in differences[:10]:  # Show only first 10 differences
                print(diff)
                print()
                
            if len(differences) > 10:
                print(f"... and {len(differences) - 10} more differences.")
                
            return 1
            
    finally:
        if not args.keep_files:
            # Clean up temporary files
            for file in [input_file, c_output, py_output]:
                if os.path.exists(file):
                    os.unlink(file)
            try:
                os.rmdir(temp_dir)
            except:
                pass
        else:
            print(f"Test files kept in {temp_dir}")

if __name__ == "__main__":
    sys.exit(main())
