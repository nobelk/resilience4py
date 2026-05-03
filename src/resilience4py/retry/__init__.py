"""Retry pattern module for resilience4py.

This module provides a retry pattern implementation that automatically retries
failed operations according to configurable policies. It supports various
backoff strategies, custom retry conditions, and comprehensive event handling.

Key Features:
    - Configurable retry attempts and intervals
    - Multiple backoff strategies (fixed, exponential, linear, etc.)
    - Exception-based and result-based retry conditions
    - Support for both synchronous and asynchronous functions
    - Comprehensive event system for monitoring
    - Thread-safe implementation

Basic Usage:
    >>> from resilience4py.retry import Retry, RetryConfig
    >>> 
    >>> # Create a simple retry decorator
    >>> retry = Retry("my-retry", RetryConfig(max_attempts=3))
    >>> 
    >>> @retry
    >>> async def flaky_operation():
    ...     # This will be retried up to 3 times on failure
    ...     return await external_api_call()

Advanced Usage:
    >>> from resilience4py.retry import (
    ...     Retry, RetryConfig, ExponentialBackoff,
    ...     RetryOnRetryEvent
    ... )
    >>> 
    >>> # Configure with exponential backoff
    >>> config = RetryConfig(
    ...     max_attempts=5,
    ...     interval_function=ExponentialBackoff(
    ...         initial_interval=0.1,
    ...         multiplier=2.0,
    ...         max_interval=10.0
    ...     ),
    ...     retry_exceptions=[ConnectionError, TimeoutError],
    ...     abort_exceptions=[ValueError]
    ... )
    >>> 
    >>> retry = Retry("api-retry", config)
    >>> 
    >>> # Add event handlers
    >>> @retry.on_retry
    >>> def log_retry(event: RetryOnRetryEvent):
    ...     print(f"Retry attempt {event.attempt} after {event.wait_interval}s")
"""

from .retry import Retry, MaxRetriesExceeded
from .config import RetryConfig
from .interval_functions import (
    IntervalFunction,
    FixedInterval,
    ExponentialBackoff,
    LinearBackoff,
    RandomInterval,
    ExponentialRandomBackoff,
    FibonacciBackoff
)
from .events import (
    RetryEvent,
    RetryEventType,
    RetryOnRetryEvent,
    RetryOnSuccessEvent,
    RetryOnErrorEvent,
    RetryOnIgnoredErrorEvent
)

__all__ = [
    # Main classes
    'Retry',
    'RetryConfig',
    
    # Exceptions
    'MaxRetriesExceeded',
    
    # Interval functions
    'IntervalFunction',
    'FixedInterval',
    'ExponentialBackoff',
    'LinearBackoff',
    'RandomInterval',
    'ExponentialRandomBackoff',
    'FibonacciBackoff',
    
    # Events
    'RetryEvent',
    'RetryEventType',
    'RetryOnRetryEvent',
    'RetryOnSuccessEvent',
    'RetryOnErrorEvent',
    'RetryOnIgnoredErrorEvent',
]

# Version info — keep aligned with the top-level package
from resilience4py import __version__  # noqa: E402

__author__ = 'resilience4py'