#!/usr/bin/env python3
"""
Test script to verify TUI debug logging functionality
"""

import subprocess
import time
import os
import sys

def test_tui_debug():
    """Test TUI with debug logging enabled"""
    
    debug_log = "/tmp/xtop_debug.log"
    
    # Remove old debug log if exists
    if os.path.exists(debug_log):
        os.remove(debug_log)
    
    print("Testing xtop-tui-simple.py with debug logging...")
    
    # Run TUI with debug logging
    cmd = [
        sys.executable,
        "../xtop-tui-simple.py",
        "-d", "../out",
        "-q", "top",
        "--debuglog", debug_log
    ]
    
    print(f"Running: {' '.join(cmd)}")
    
    # Start the process
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Give it time to start
    time.sleep(2)
    
    # Send quit command
    proc.stdin.write('q')
    proc.stdin.flush()
    
    # Wait for process to end
    stdout, stderr = proc.communicate(timeout=5)
    
    print(f"Exit code: {proc.returncode}")
    
    if stderr:
        print(f"Stderr: {stderr}")
    
    # Check debug log
    if os.path.exists(debug_log):
        print(f"\nDebug log contents ({debug_log}):")
        print("-" * 80)
        with open(debug_log, 'r') as f:
            content = f.read()
            print(content)
            
            # Check for key debug information
            if "Executing query type:" in content:
                print("\n✓ Query execution logged")
            else:
                print("\n✗ Query execution not logged")
                
            if "DEBUG SQL:" in content:
                print("✓ SQL queries logged")
            else:
                print("✗ SQL queries not logged")
                
            if "Query returned" in content:
                print("✓ Query results logged")
            else:
                print("✗ Query results not logged")
    else:
        print(f"\n✗ Debug log not created: {debug_log}")

if __name__ == "__main__":
    test_tui_debug()