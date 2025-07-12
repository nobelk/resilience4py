#!/usr/bin/env python
"""Run rate limiter tests."""

import subprocess
import sys


def run_tests():
    """Run the rate limiter tests with pytest."""
    print("Running rate limiter tests...")
    print("-" * 50)
    
    # Run pytest with verbose output
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/ratelimiter/",
        "-v",
        "--tb=short",
        "-k", "not test_thread_safety"  # Skip thread safety test for quick run
    ]
    
    result = subprocess.run(cmd, cwd="/Users/Nobel.Khandaker/sources/resilience4py")
    
    return result.returncode


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)