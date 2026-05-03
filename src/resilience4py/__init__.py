"""Resilience4py - Fault tolerance patterns for Python.

This package provides resilience patterns including Circuit Breaker,
Bulkhead, Rate Limiter, and Retry for building fault-tolerant Python applications.
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("resilience4py")
except PackageNotFoundError:  # editable/source checkout without metadata
    __version__ = "0.0.0+unknown"

# Import all patterns and their components
from resilience4py.circuitbreaker import CircuitBreaker, CircuitBreakerConfig
from resilience4py.bulkhead import Bulkhead, SemaphoreBulkhead, ThreadPoolBulkhead, BulkheadConfig
from resilience4py.ratelimiter import RateLimiter, AtomicRateLimiter, RateLimiterConfig
from resilience4py.retry import Retry, RetryConfig

# Import core components
from resilience4py.core import Registry, Event, EventPublisher

__all__ = [
    "__version__",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitBreakerConfig",
    # Bulkhead
    "Bulkhead",
    "SemaphoreBulkhead", 
    "ThreadPoolBulkhead",
    "BulkheadConfig",
    # Rate Limiter
    "RateLimiter",
    "AtomicRateLimiter",
    "RateLimiterConfig",
    # Retry
    "Retry",
    "RetryConfig",
    # Core
    "Registry",
    "Event",
    "EventPublisher",
]