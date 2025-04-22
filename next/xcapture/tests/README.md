# MD5 Implementation Test Suite

This project provides a comprehensive test suite for verifying an MD5 hash implementation against Python's built-in hashlib implementation.

## Components

- **md5.h / md5.c**: The MD5 implementation to be tested (your existing files)
- **md5_test.c**: C program that reads strings and calculates their MD5 hashes
- **test_md5.py**: Python script that generates test strings and compares results

## Building the C Test Program

```bash
make
```

This will compile the `md5_test` executable using your existing md5.c and md5.h files.

## Running the Tests

```bash
# Run with default settings (100 test strings)
python3 test_md5.py

# Run with more test strings and larger sizes
python3 test_md5.py -n 1000 --min-length 10 --max-length 5000

# Keep temporary test files for inspection
python3 test_md5.py --keep-files
```

### Command-line Options

- `-n, --count`: Number of test strings to generate (default: 100)
- `--min-length`: Minimum string length (default: 0)
- `--max-length`: Maximum string length (default: 1000)
- `--keep-files`: Keep temporary test files after running
- `--exe`: Path to the C MD5 test executable (default: ./md5_test)

## Testing Process

The test script does the following:

1. Generates random test strings of varying lengths, including edge cases
2. Calculates MD5 hashes using the C implementation
3. Calculates MD5 hashes using Python's hashlib.md5
4. Compares the results to ensure they match

## Manual Testing

If you want to run the tests manually:

1. Generate test strings:
   ```bash
   python3 -c "import random, string; print('\n'.join(''.join(random.choice(string.printable) for _ in range(random.randint(0, 100))) for _ in range(20)))" > test_strings.txt
   ```

2. Run the C implementation:
   ```bash
   ./md5_test test_strings.txt > c_output.txt
   ```

3. Run the Python implementation:
   ```bash
   python3 -c "import sys, hashlib; [print(f'{hashlib.md5(line.strip().encode()).hexdigest()} {line.strip()}') for line in open(sys.argv[1])]" test_strings.txt > py_output.txt
   ```

4. Compare the results:
   ```bash
   diff c_output.txt py_output.txt
   ```
