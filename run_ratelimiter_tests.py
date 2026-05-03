#!/usr/bin/env python
"""Run rate limiter tests.

Equivalent to::

    python -m pytest tests/ratelimiter/ -v --tb=short -k "not test_thread_safety"

Kept as a convenience entry point. Resolves the repo root from this file's
location, so it works on any machine without local edits.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def run_tests() -> int:
    """Run the rate limiter tests with pytest."""
    print("Running rate limiter tests...")
    print("-" * 50)

    cmd = [
        sys.executable, "-m", "pytest",
        "tests/ratelimiter/",
        "-v",
        "--tb=short",
        "-k", "not test_thread_safety",  # Skip thread safety test for quick run
    ]

    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


if __name__ == "__main__":
    sys.exit(run_tests())