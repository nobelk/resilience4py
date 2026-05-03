"""Test that all main imports work correctly."""

import pytest


class TestImports:
    """Test importing resilience4py components."""
    
    def test_version_import(self):
        """Test that version can be imported and is a non-empty string.

        Version is sourced from package metadata (pyproject.toml), so this
        test only asserts shape — not a hard-coded value that would have
        to be updated on every release.
        """
        from resilience4py import __version__
        assert isinstance(__version__, str)
        assert len(__version__) > 0

    def test_version_matches_package_metadata(self):
        """Version exposed by the package matches the installed metadata."""
        from importlib.metadata import version
        from resilience4py import __version__
        assert __version__ == version("resilience4py")
    
    def test_circuit_breaker_imports(self):
        """Test that circuit breaker components can be imported."""
        from resilience4py import CircuitBreaker, CircuitBreakerConfig
        from resilience4py.circuitbreaker import CircuitBreaker as CB
        assert CircuitBreaker is CB
    
    def test_bulkhead_imports(self):
        """Test that bulkhead components can be imported."""
        from resilience4py import (
            Bulkhead,
            SemaphoreBulkhead,
            ThreadPoolBulkhead,
            BulkheadConfig
        )
        from resilience4py.bulkhead import Bulkhead as BH
        assert Bulkhead is BH
    
    def test_rate_limiter_imports(self):
        """Test that rate limiter components can be imported."""
        from resilience4py import RateLimiter, AtomicRateLimiter, RateLimiterConfig
        from resilience4py.ratelimiter import RateLimiter as RL
        assert RateLimiter is RL
    
    def test_retry_imports(self):
        """Test that retry components can be imported."""
        from resilience4py import Retry, RetryConfig
        from resilience4py.retry import Retry as R
        assert Retry is R
    
    def test_core_imports(self):
        """Test that core components can be imported."""
        from resilience4py import Registry, Event, EventPublisher
        from resilience4py.core import Registry as Reg
        assert Registry is Reg
    
    def test_all_exports(self):
        """Test that __all__ contains expected exports."""
        import resilience4py
        
        expected_exports = {
            "__version__",
            "CircuitBreaker",
            "CircuitBreakerConfig",
            "Bulkhead",
            "SemaphoreBulkhead",
            "ThreadPoolBulkhead",
            "BulkheadConfig",
            "RateLimiter",
            "AtomicRateLimiter",
            "RateLimiterConfig",
            "Retry",
            "RetryConfig",
            "Registry",
            "Event",
            "EventPublisher",
        }
        
        actual_exports = set(resilience4py.__all__)
        assert actual_exports == expected_exports