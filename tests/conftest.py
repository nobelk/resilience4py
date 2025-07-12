"""Pytest configuration for resilience4py tests"""

import pytest
import asyncio
import sys
import os

# Add pytest-asyncio plugin
# pytest_plugins = ("pytest_asyncio",)

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))