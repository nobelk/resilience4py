"""Integration tests for the rate limiter pattern."""

import asyncio
import time
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock

import pytest

from resilience4py.ratelimiter import (
    RateLimiter, RateLimiterConfig, RequestNotPermitted, rate_limit
)
from resilience4py.ratelimiter.events import (
    RateLimiterOnSuccessEvent, RateLimiterOnFailureEvent
)


class TestRateLimiterIntegration:
    """Integration tests for rate limiter functionality."""
    
    @pytest.mark.asyncio
    async def test_basic_rate_limiting_flow(self):
        """Test basic rate limiting flow with success and failure."""
        events = []
        
        # Event publisher to track events
        class EventCollector:
            async def publish(self, event):
                events.append(event)
        
        # Create rate limiter with small limit
        config = RateLimiterConfig(
            limit_for_period=2,
            limit_refresh_period=timedelta(seconds=1),
            timeout_duration=timedelta(milliseconds=100)
        )
        
        rate_limiter = RateLimiter("integration-test", config)
        atomic_limiter = await rate_limiter._get_limiter()
        atomic_limiter.add_event_publisher(EventCollector())
        
        @rate_limiter
        async def api_call(x):
            return x * 2
        
        # First two calls should succeed
        assert await api_call(1) == 2
        assert await api_call(2) == 4
        
        # Third call should fail due to timeout
        with pytest.raises(RequestNotPermitted):
            await api_call(3)
        
        # Check events
        assert len(events) == 3
        assert isinstance(events[0], RateLimiterOnSuccessEvent)
        assert isinstance(events[1], RateLimiterOnSuccessEvent)
        assert isinstance(events[2], RateLimiterOnFailureEvent)
        assert events[2].wait_time_nanos > 0
    
    @pytest.mark.asyncio
    async def test_rate_limiter_with_waiting(self):
        """Test rate limiting with actual waiting."""
        config = RateLimiterConfig(
            limit_for_period=2,
            limit_refresh_period=timedelta(milliseconds=200),
            timeout_duration=timedelta(seconds=1)
        )
        
        @RateLimiter("wait-test", config)
        async def rate_limited_func():
            return time.time()
        
        # First two calls succeed immediately
        time1 = await rate_limited_func()
        time2 = await rate_limited_func()
        assert (time2 - time1) < 0.1  # Should be fast
        
        # Third call should wait
        time3 = await rate_limited_func()
        assert (time3 - time2) >= 0.15  # Should have waited ~200ms
        assert (time3 - time2) < 0.3   # But not too long
    
    @pytest.mark.asyncio
    async def test_concurrent_rate_limiting(self):
        """Test rate limiting under concurrent load."""
        config = RateLimiterConfig(
            limit_for_period=5,
            limit_refresh_period=timedelta(seconds=1),
            timeout_duration=timedelta(milliseconds=100)
        )
        
        rate_limiter = RateLimiter("concurrent-test", config)
        success_count = 0
        failure_count = 0
        
        @rate_limiter
        async def concurrent_func(i):
            nonlocal success_count
            success_count += 1
            return f"success-{i}"
        
        # Launch 10 concurrent requests
        tasks = []
        for i in range(10):
            tasks.append(concurrent_func(i))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successes and failures
        actual_successes = [r for r in results if isinstance(r, str) and r.startswith("success")]
        actual_failures = [r for r in results if isinstance(r, RequestNotPermitted)]
        
        assert len(actual_successes) == 5  # limit_for_period
        assert len(actual_failures) == 5   # exceeded limit with short timeout
    
    def test_sync_function_rate_limiting(self):
        """Test rate limiting on synchronous functions."""
        config = RateLimiterConfig(
            limit_for_period=3,
            limit_refresh_period=timedelta(seconds=1),
            timeout_duration=timedelta(milliseconds=50)
        )
        
        @RateLimiter("sync-test", config)
        def sync_function(x):
            return x ** 2
        
        # Should allow 3 calls
        assert sync_function(2) == 4
        assert sync_function(3) == 9
        assert sync_function(4) == 16
        
        # Fourth should fail
        with pytest.raises(RequestNotPermitted):
            sync_function(5)
    
    @pytest.mark.asyncio
    async def test_rate_limiter_reset(self):
        """Test resetting a rate limiter."""
        config = RateLimiterConfig(
            limit_for_period=2,
            limit_refresh_period=timedelta(seconds=10),  # Long period
            timeout_duration=timedelta(milliseconds=50)
        )
        
        rate_limiter = RateLimiter("reset-test", config)
        
        @rate_limiter
        async def limited_func():
            return "ok"
        
        # Use up the limit
        assert await limited_func() == "ok"
        assert await limited_func() == "ok"
        
        # Should fail
        with pytest.raises(RequestNotPermitted):
            await limited_func()
        
        # Reset the limiter
        await rate_limiter.reset()
        
        # Should work again
        assert await limited_func() == "ok"
        assert await limited_func() == "ok"
    
    @pytest.mark.asyncio
    async def test_rate_limiter_metrics(self):
        """Test rate limiter metrics tracking."""
        config = RateLimiterConfig(
            limit_for_period=5,
            limit_refresh_period=timedelta(seconds=1)
        )
        
        rate_limiter = RateLimiter("metrics-test", config)
        
        # Check initial metrics
        metrics = await rate_limiter.get_metrics()
        assert metrics["available_permissions"] == 5
        assert metrics["limit_for_period"] == 5
        
        # Use some permissions
        await rate_limiter.acquire_permission()
        await rate_limiter.acquire_permission()
        
        # Check updated metrics
        metrics = await rate_limiter.get_metrics()
        assert metrics["available_permissions"] == 3
    
    def test_thread_safety(self):
        """Test rate limiter thread safety."""
        config = RateLimiterConfig(
            limit_for_period=10,
            limit_refresh_period=timedelta(seconds=1),
            timeout_duration=timedelta(milliseconds=100)
        )
        
        @RateLimiter("thread-test", config)
        def thread_func(i):
            time.sleep(0.01)  # Small delay
            return i
        
        # Run concurrent threads
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(thread_func, i) for i in range(20)]
            results = []
            failures = 0
            
            for future in futures:
                try:
                    results.append(future.result())
                except RequestNotPermitted:
                    failures += 1
        
        # Should have exactly 10 successes and 10 failures
        assert len(results) == 10
        assert failures == 10
    
    @pytest.mark.asyncio
    async def test_dynamic_configuration(self):
        """Test changing rate limiter configuration."""
        # Start with restrictive config
        RateLimiter.set_default_config(RateLimiterConfig(
            limit_for_period=1,
            limit_refresh_period=timedelta(seconds=1)
        ))
        
        @RateLimiter("dynamic-test")
        async def dynamic_func():
            return "ok"
        
        # Should allow one call
        assert await dynamic_func() == "ok"
        
        # Note: In the current implementation, changing default config
        # won't affect already created limiters. This test documents
        # the current behavior.
    
    @pytest.mark.asyncio 
    async def test_acquire_permission_direct_usage(self):
        """Test using acquire_permission directly without decorator."""
        rate_limiter = RateLimiter("direct-test", RateLimiterConfig(
            limit_for_period=3,
            limit_refresh_period=timedelta(seconds=1)
        ))
        
        # Acquire permissions directly
        assert await rate_limiter.acquire_permission() is True
        assert await rate_limiter.acquire_permission() is True
        assert await rate_limiter.acquire_permission() is True
        
        # Fourth should fail (assuming short timeout)
        # Note: This might wait if timeout is long, so we use a fresh limiter
        strict_limiter = RateLimiter("strict-test", RateLimiterConfig(
            limit_for_period=1,
            limit_refresh_period=timedelta(seconds=10),
            timeout_duration=timedelta(milliseconds=1)
        ))
        
        assert await strict_limiter.acquire_permission() is True
        assert await strict_limiter.acquire_permission() is False