#!/usr/bin/env python
"""Quick test runner script."""

import subprocess
import sys

def main():
    """Run the circuit breaker tests."""
    print("Running Circuit Breaker tests...")
    print("-" * 60)
    
    # Run pytest with the circuit breaker tests
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/circuitbreaker/",
        "-v",
        "--tb=short"
    ]
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed!")
    
    return result.returncode

if __name__ == "__main__":
    sys.exit(main())