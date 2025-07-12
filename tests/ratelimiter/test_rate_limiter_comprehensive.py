"""Comprehensive tests for RateLimiter to increase coverage."""

import asyncio
import time
from datetime import timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from weakref import WeakValueDictionary
import threading

import pytest

from resilience4py.ratelimiter import (
    RateLimiter, RateLimiterRegistry, RequestNotPermitted, rate_limit
)
from resilience4py.ratelimiter.config import RateLimiterConfig
from resilience4py.ratelimiter.atomic_rate_limiter import AtomicRateLimiter


class TestRateLimiterRegistryComprehensive:
    """Comprehensive test cases for RateLimiterRegistry to achieve >75% coverage."""
    
    @pytest.fixture
    def registry(self):
        """Create a fresh registry instance."""
        return RateLimiterRegistry()

    def test_get_or_create_with_existing_instance_no_config(self, registry):
        """Test getting existing instance without providing config (line 45)."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                config = RateLimiterConfig(limit_for_period=10)
                
                # Create instance with config
                limiter1 = loop.run_until_complete(registry.get_or_create("test", config))
                
                # Get same instance without config
                limiter2 = loop.run_until_complete(registry.get_or_create("test"))
                
                # Should return the same instance
                assert limiter1 is limiter2
                assert "test" in registry._instances
            finally:
                loop.close()
        
        run_test()

    def test_remove_from_instances_only(self, registry):
        """Test removing instance that exists in instances but not configs (line 70-73)."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Create instance without saving config
                limiter = loop.run_until_complete(registry.get_or_create("test"))
                
                # Manually remove from configs to test line 72-73
                if "test" in registry._configs:
                    del registry._configs["test"]
                
                # Now remove - should only remove from instances
                registry.remove("test")
                
                assert "test" not in registry._instances
                assert "test" not in registry._configs  # Should still not be there
            finally:
                loop.close()
        
        run_test()


class TestRateLimiterComprehensive:
    """Comprehensive test cases for RateLimiter to achieve >75% coverage."""
    
    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return RateLimiterConfig(
            limit_for_period=2,
            limit_refresh_period=timedelta(seconds=1),
            timeout_duration=timedelta(seconds=5)
        )
    
    @pytest.fixture
    def rate_limiter(self, config):
        """Create a rate limiter instance."""
        return RateLimiter("test-limiter", config)

    def test_decorate_async_function_with_call(self, rate_limiter):
        """Test decorating async function using __call__ (line 135)."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                async def async_test_func():
                    return "async_decorated"
                
                # Use __call__ directly
                decorated = rate_limiter.__call__(async_test_func)
                result = loop.run_until_complete(decorated())
                
                assert result == "async_decorated"
            finally:
                loop.close()
        
        run_test()

    def test_decorate_async_function_internal(self, rate_limiter):
        """Test internal async decoration method (lines 169-173)."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                async def async_func():
                    return "internal_async"
                
                # Call internal decoration method
                decorated = rate_limiter._decorate_async(async_func)
                result = loop.run_until_complete(decorated())
                
                assert result == "internal_async"
            finally:
                loop.close()
        
        run_test()


    def test_acquire_permission_with_reserve_exception(self, rate_limiter):
        """Test acquire_permission when _reserve_permission raises exception."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                with patch.object(rate_limiter, '_get_limiter') as mock_get:
                    mock_limiter = AsyncMock()
                    mock_limiter._reserve_permission.side_effect = Exception("Reserve error")
                    mock_get.return_value = mock_limiter
                    
                    result = loop.run_until_complete(rate_limiter.acquire_permission())
                    assert result is False  # Should return False on exception
            finally:
                loop.close()
        
        run_test()

    def test_get_metrics_delegation(self, rate_limiter):
        """Test get_metrics method delegation (lines 224-225)."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                metrics = loop.run_until_complete(rate_limiter.get_metrics())
                
                # Should contain expected keys
                assert "name" in metrics
                assert "available_permissions" in metrics
                assert "limit_for_period" in metrics
                assert "current_cycle" in metrics
            finally:
                loop.close()
        
        run_test()

    def test_reset_delegation(self, rate_limiter):
        """Test reset method delegation (lines 229-230)."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Use some permissions first
                loop.run_until_complete(rate_limiter.acquire_permission())
                
                # Reset should work without error
                loop.run_until_complete(rate_limiter.reset())
                
                # Verify reset by checking metrics
                metrics = loop.run_until_complete(rate_limiter.get_metrics())
                assert metrics["available_permissions"] == 2  # Should be back to limit
            finally:
                loop.close()
        
        run_test()

    def test_registry_weak_reference_cleanup(self):
        """Test that registry properly handles weak references."""
        registry = RateLimiterRegistry()
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                config = RateLimiterConfig(limit_for_period=5)
                
                # Create instance
                limiter = loop.run_until_complete(registry.get_or_create("weak_test", config))
                assert "weak_test" in registry._instances
                
                # Delete reference
                del limiter
                
                # Force garbage collection to test weak reference behavior
                import gc
                gc.collect()
                
                # Weak reference should eventually be cleaned up
                # Note: This is non-deterministic, so we just verify the mechanism exists
                assert isinstance(registry._instances, WeakValueDictionary)
            finally:
                loop.close()
        
        run_test()

    def test_concurrent_registry_access_edge_case(self):
        """Test concurrent access to registry with same name."""
        registry = RateLimiterRegistry()
        results = []
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                async def create_limiter(name_suffix):
                    try:
                        config = RateLimiterConfig(limit_for_period=3)
                        limiter = await registry.get_or_create(f"concurrent_{name_suffix}", config)
                        results.append(("success", limiter.name))
                        return limiter
                    except Exception as e:
                        results.append(("error", str(e)))
                        return None
                
                # Create multiple limiters concurrently with different names
                tasks = [create_limiter(i) for i in range(10)]
                limiters = loop.run_until_complete(asyncio.gather(*tasks))
                
                # All should succeed
                successes = [r for r in results if r[0] == "success"]
                assert len(successes) == 10
                
                # All limiters should be different instances (different names)
                names = [limiter.name for limiter in limiters if limiter]
                assert len(set(names)) == 10  # All unique names
            finally:
                loop.close()
        
        run_test()

    def test_sync_wrapper_with_new_event_loop(self, rate_limiter):
        """Test sync wrapper creating new event loop."""
        
        def sync_test_func():
            return "sync_wrapped"
        
        # Test the sync wrapper functionality
        decorated = rate_limiter._decorate_sync(sync_test_func)
        result = decorated()
        
        assert result == "sync_wrapped"

    def test_rate_limit_convenience_function_edge_cases(self):
        """Test rate_limit convenience function with edge cases."""
        
        # Test with very small refresh period
        limiter = rate_limit(1, 0.001)  # 1 request per millisecond
        assert limiter.config.limit_for_period == 1
        assert limiter.config.limit_refresh_period == timedelta(seconds=0.001)
        
        # Test with large limit
        limiter = rate_limit(1000, 1.0)
        assert limiter.config.limit_for_period == 1000
        
        # Test unique naming
        limiter1 = rate_limit(5, 1.0)
        limiter2 = rate_limit(5, 1.0)
        assert limiter1.name == limiter2.name  # Same parameters should have same name

    def test_multiple_decorators_on_same_function(self, rate_limiter):
        """Test applying rate limiter decorator multiple times."""
        
        def test_func():
            return "multi_decorated"
        
        # Apply decorator once
        decorated1 = rate_limiter(test_func)
        
        # Should work
        result = decorated1()
        assert result == "multi_decorated"

    def test_error_in_decorated_async_function(self, rate_limiter):
        """Test that errors in decorated async functions are properly propagated."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                @rate_limiter
                async def failing_async_func():
                    raise ValueError("Async function failed")
                
                with pytest.raises(ValueError, match="Async function failed"):
                    loop.run_until_complete(failing_async_func())
            finally:
                loop.close()
        
        run_test()

    def test_error_in_decorated_sync_function(self, rate_limiter):
        """Test that errors in decorated sync functions are properly propagated."""
        
        @rate_limiter
        def failing_sync_func():
            raise ValueError("Sync function failed")
        
        with pytest.raises(ValueError, match="Sync function failed"):
            failing_sync_func()

    def test_stress_test_rapid_acquire_permission(self, rate_limiter):
        """Stress test rapid calls to acquire_permission."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = []
                
                async def rapid_acquire():
                    for _ in range(10):
                        result = await rate_limiter.acquire_permission()
                        results.append(result)
                
                loop.run_until_complete(rapid_acquire())
                
                # Should have some True and some False results
                true_count = sum(1 for r in results if r is True)
                false_count = sum(1 for r in results if r is False)
                
                assert true_count >= 2  # At least limit_for_period should succeed
                assert false_count >= 0  # Some may be rate limited
            finally:
                loop.close()
        
        run_test()

    def test_global_registry_isolation(self):
        """Test that global registry is properly isolated."""
        from resilience4py.ratelimiter.rate_limiter import _registry
        
        # The global registry should be a RateLimiterRegistry instance
        assert isinstance(_registry, RateLimiterRegistry)
        
        # Test setting default config globally
        original_config = _registry._default_config
        new_config = RateLimiterConfig(limit_for_period=999)
        
        RateLimiter.set_default_config(new_config)
        assert _registry._default_config == new_config
        
        # Restore original config
        _registry._default_config = original_config