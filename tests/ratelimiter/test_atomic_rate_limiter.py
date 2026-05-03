"""Tests for AtomicRateLimiter."""

import asyncio
import time
from datetime import timedelta
from unittest.mock import Mock, AsyncMock, patch

import pytest

from resilience4py.ratelimiter.atomic_rate_limiter import (
    AtomicRateLimiter, RateLimiterState, RequestNotPermitted
)
from resilience4py.ratelimiter.config import RateLimiterConfig
from resilience4py.ratelimiter.events import RateLimiterOnSuccessEvent, RateLimiterOnFailureEvent


class TestAtomicRateLimiter:
    """Test cases for AtomicRateLimiter."""
    
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
        return AtomicRateLimiter("test-limiter", config)
    
    def test_initialization(self, rate_limiter, config):
        """Test rate limiter initialization."""
        assert rate_limiter.name == "test-limiter"
        assert rate_limiter.config == config
        assert rate_limiter._state.active_permissions == config.limit_for_period
        assert rate_limiter._state.active_cycle == 0
        assert rate_limiter._state.nanoseconds_to_wait == 0
        assert rate_limiter._event_publishers == []
    
    @pytest.mark.asyncio
    async def test_reserve_permission_success(self, rate_limiter):
        """Test successful permission reservation."""
        # First permission should succeed immediately
        wait_time = await rate_limiter._reserve_permission()
        assert wait_time == 0
        assert rate_limiter._state.active_permissions == 1
        
        # Second permission should also succeed
        wait_time = await rate_limiter._reserve_permission()
        assert wait_time == 0
        assert rate_limiter._state.active_permissions == 0
    
    @pytest.mark.asyncio
    async def test_reserve_permission_wait(self, rate_limiter):
        """Test permission reservation when need to wait."""
        # Use up all permissions
        await rate_limiter._reserve_permission()
        await rate_limiter._reserve_permission()
        
        # Third permission should require waiting
        wait_time = await rate_limiter._reserve_permission()
        assert wait_time > 0
        assert wait_time <= 1_000_000_000  # Should be less than 1 second
    
    @pytest.mark.asyncio
    async def test_reserve_permission_timeout(self):
        """Test permission reservation timeout.

        Mocked time keeps this test deterministic — without it, the test
        would be flaky because the position within the 10s cycle depends on
        when the test happens to run.
        """
        config = RateLimiterConfig(
            limit_for_period=1,
            limit_refresh_period=timedelta(seconds=10),
            timeout_duration=timedelta(seconds=1)
        )

        # Pin the clock to the very start of a cycle so the wait until the
        # next cycle is always the full 10 seconds, well past the 1s timeout.
        cycle_nanos = 10_000_000_000
        with patch('time.monotonic_ns', return_value=cycle_nanos):
            rate_limiter = AtomicRateLimiter("timeout-test", config)
            # Use up the permission
            await rate_limiter._reserve_permission()
            # Next permission should timeout (10s wait > 1s timeout)
            wait_time = await rate_limiter._reserve_permission()
        assert wait_time < 0  # Negative indicates timeout
    
    @pytest.mark.asyncio
    async def test_cycle_refresh(self, rate_limiter):
        """Test permission refresh on new cycle."""
        # Use up all permissions
        await rate_limiter._reserve_permission()
        await rate_limiter._reserve_permission()
        assert rate_limiter._state.active_permissions == 0
        
        # Get current time before mocking
        current_time = time.monotonic_ns()

        # Mock time to simulate next cycle
        with patch('time.monotonic_ns') as mock_time:
            # Move to next cycle (1 second later)
            mock_time.return_value = int(current_time + 1_000_000_000)
            
            # Permissions should be refreshed
            wait_time = await rate_limiter._reserve_permission()
            assert wait_time == 0
            assert rate_limiter._state.active_permissions == 1
            assert rate_limiter._state.active_cycle > 0
    
    @pytest.mark.asyncio
    async def test_decorate_async_function(self, rate_limiter):
        """Test decorating an async function."""
        call_count = 0
        
        @rate_limiter
        async def test_func(value):
            nonlocal call_count
            call_count += 1
            return value * 2
        
        # Should succeed for limit_for_period calls
        result = await test_func(5)
        assert result == 10
        assert call_count == 1
        
        result = await test_func(10)
        assert result == 20
        assert call_count == 2
    
    def test_decorate_sync_function(self, rate_limiter):
        """Test decorating a sync function."""
        call_count = 0
        
        @rate_limiter
        def test_func(value):
            nonlocal call_count
            call_count += 1
            return value * 2
        
        # Should succeed for limit_for_period calls
        result = test_func(5)
        assert result == 10
        assert call_count == 1
        
        result = test_func(10)
        assert result == 20
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_rate_limiting_enforcement(self, rate_limiter):
        """Test that rate limiting is enforced."""
        @rate_limiter
        async def test_func():
            return "success"
        
        # First two calls should succeed
        assert await test_func() == "success"
        assert await test_func() == "success"
        
        # Third call should be rate limited (with short timeout)
        rate_limiter.config = RateLimiterConfig(
            limit_for_period=2,
            limit_refresh_period=timedelta(seconds=1),
            timeout_duration=timedelta(microseconds=1)
        )
        
        with pytest.raises(RequestNotPermitted):
            await test_func()
    
    @pytest.mark.asyncio
    async def test_event_publishing_success(self, rate_limiter):
        """Test event publishing on success."""
        publisher = AsyncMock()
        rate_limiter.add_event_publisher(publisher)
        
        @rate_limiter
        async def test_func():
            return "success"
        
        await test_func()
        
        # Verify success event was published
        publisher.publish.assert_called_once()
        event = publisher.publish.call_args[0][0]
        assert isinstance(event, RateLimiterOnSuccessEvent)
        assert event.name == "test-limiter"
    
    @pytest.mark.asyncio
    async def test_event_publishing_failure(self):
        """Test event publishing on failure."""
        config = RateLimiterConfig(
            limit_for_period=1,
            limit_refresh_period=timedelta(seconds=1),
            timeout_duration=timedelta(microseconds=1)
        )
        rate_limiter = AtomicRateLimiter("test", config)
        
        publisher = AsyncMock()
        rate_limiter.add_event_publisher(publisher)
        
        @rate_limiter
        async def test_func():
            return "success"
        
        # First call succeeds
        await test_func()
        
        # Second call should fail
        with pytest.raises(RequestNotPermitted):
            await test_func()
        
        # Verify both events were published
        assert publisher.publish.call_count == 2
        success_event = publisher.publish.call_args_list[0][0][0]
        failure_event = publisher.publish.call_args_list[1][0][0]
        
        assert isinstance(success_event, RateLimiterOnSuccessEvent)
        assert isinstance(failure_event, RateLimiterOnFailureEvent)
        assert failure_event.wait_time_nanos > 0
    
    @pytest.mark.asyncio
    async def test_event_publisher_management(self, rate_limiter):
        """Test adding and removing event publishers."""
        publisher1 = Mock()
        publisher2 = Mock()
        
        rate_limiter.add_event_publisher(publisher1)
        rate_limiter.add_event_publisher(publisher2)
        assert len(rate_limiter._event_publishers) == 2
        
        rate_limiter.remove_event_publisher(publisher1)
        assert len(rate_limiter._event_publishers) == 1
        assert rate_limiter._event_publishers[0] == publisher2
        
        # Removing non-existent publisher should not raise
        rate_limiter.remove_event_publisher(publisher1)
        assert len(rate_limiter._event_publishers) == 1
    
    @pytest.mark.asyncio
    async def test_get_metrics(self, rate_limiter):
        """Test getting rate limiter metrics."""
        # Initial state
        metrics = await rate_limiter.get_metrics()
        assert metrics["name"] == "test-limiter"
        assert metrics["available_permissions"] == 2
        assert metrics["limit_for_period"] == 2
        assert metrics["current_cycle"] == 0
        
        # After using a permission
        await rate_limiter._reserve_permission()
        metrics = await rate_limiter.get_metrics()
        assert metrics["available_permissions"] == 1
    
    @pytest.mark.asyncio
    async def test_reset(self, rate_limiter):
        """Test resetting the rate limiter."""
        # Use up permissions
        await rate_limiter._reserve_permission()
        await rate_limiter._reserve_permission()
        assert rate_limiter._state.active_permissions == 0
        
        # Reset
        await rate_limiter.reset()
        assert rate_limiter._state.active_permissions == 2
        assert rate_limiter._state.active_cycle == 0
        assert rate_limiter._state.nanoseconds_to_wait == 0
    
    @pytest.mark.asyncio
    async def test_concurrent_access(self, rate_limiter):
        """Test concurrent access to rate limiter."""
        results = []
        
        async def try_access():
            try:
                wait_time = await rate_limiter._reserve_permission()
                results.append(("success", wait_time))
            except Exception as e:
                results.append(("error", str(e)))
        
        # Run multiple concurrent requests
        await asyncio.gather(*[try_access() for _ in range(5)])
        
        # Should have 2 immediate successes and 3 waiting
        success_count = sum(1 for r in results if r[0] == "success" and r[1] == 0)
        assert success_count == 2
        
        wait_count = sum(1 for r in results if r[0] == "success" and r[1] > 0)
        assert wait_count == 3
    
    @pytest.mark.asyncio
    async def test_error_handling_in_decorated_function(self, rate_limiter):
        """Test error handling when decorated function raises."""
        @rate_limiter
        async def failing_func():
            raise ValueError("Test error")
        
        # Rate limiter should not interfere with exceptions
        with pytest.raises(ValueError, match="Test error"):
            await failing_func()
        
        # Permission should still be consumed
        assert rate_limiter._state.active_permissions == 1
    
    @pytest.mark.asyncio
    async def test_event_publisher_error_handling(self, rate_limiter):
        """Test that errors in event publishers don't affect rate limiting."""
        failing_publisher = AsyncMock()
        failing_publisher.publish.side_effect = Exception("Publisher error")
        
        rate_limiter.add_event_publisher(failing_publisher)
        
        @rate_limiter
        async def test_func():
            return "success"
        
        # Should succeed despite publisher error
        result = await test_func()
        assert result == "success"
        
        # Publisher should have been called
        failing_publisher.publish.assert_called_once()