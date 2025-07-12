"""Comprehensive tests for AtomicRateLimiter to increase coverage."""

import asyncio
import time
from datetime import timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import threading

import pytest

from resilience4py.ratelimiter.atomic_rate_limiter import (
    AtomicRateLimiter, RateLimiterState, RequestNotPermitted
)
from resilience4py.ratelimiter.config import RateLimiterConfig
from resilience4py.ratelimiter.events import RateLimiterOnSuccessEvent, RateLimiterOnFailureEvent


class TestAtomicRateLimiterComprehensive:
    """Comprehensive test cases for AtomicRateLimiter to achieve >75% coverage."""
    
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

    def test_sync_function_execution_in_new_event_loop(self, rate_limiter):
        """Test sync function execution through new event loop (line 92-98)."""
        executed = False
        
        def sync_function():
            nonlocal executed
            executed = True
            return "sync_result"
        
        # Test decorator on sync function  
        decorated = rate_limiter(sync_function)
        result = decorated()
        
        assert result == "sync_result"
        assert executed is True

    def test_async_function_decoration_and_execution(self, rate_limiter):
        """Test async function decoration and execution (lines 111-114, 146-149)."""
        
        def run_async_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                async def async_function():
                    return "async_result"
                
                # Test decorator on async function
                decorated = rate_limiter(async_function)
                result = loop.run_until_complete(decorated())
                
                assert result == "async_result"
            finally:
                loop.close()
        
        run_async_test()

    def test_execute_async_with_wait_time(self, rate_limiter):
        """Test _execute_async with positive wait time (line 140)."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                async def test_function():
                    return "waited_result"
                
                # Mock _reserve_permission to return wait time
                with patch.object(rate_limiter, '_reserve_permission') as mock_reserve:
                    with patch('asyncio.sleep') as mock_sleep:
                        mock_reserve.return_value = 100_000_000  # 100ms in nanos
                        
                        result = loop.run_until_complete(
                            rate_limiter._execute_async(test_function)
                        )
                        
                        assert result == "waited_result"
                        mock_sleep.assert_called_once_with(0.1)  # 100ms in seconds
            finally:
                loop.close()
        
        run_test()

    def test_execute_async_with_sync_function(self, rate_limiter):
        """Test _execute_async with sync function (line 147-149)."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                def sync_function():
                    return "sync_in_async"
                
                result = loop.run_until_complete(
                    rate_limiter._execute_async(sync_function)
                )
                
                assert result == "sync_in_async"
            finally:
                loop.close()
        
        run_test()

    def test_reserve_permission_negative_wait_time(self, rate_limiter):
        """Test _reserve_permission returning negative value (line 198)."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Configure for immediate timeout
                config = RateLimiterConfig(
                    limit_for_period=1,
                    limit_refresh_period=timedelta(seconds=10),  # Long period
                    timeout_duration=timedelta(microseconds=1)  # Very short timeout
                )
                limiter = AtomicRateLimiter("timeout-test", config)
                
                # Use up the single permission
                loop.run_until_complete(limiter._reserve_permission())
                
                # Next call should return negative value (timeout)
                wait_time = loop.run_until_complete(limiter._reserve_permission())
                assert wait_time < 0
            finally:
                loop.close()
        
        run_test()

    def test_event_publishing_with_exception(self, rate_limiter):
        """Test event publishing when publisher raises exception (lines 208-212)."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Add a failing publisher
                failing_publisher = AsyncMock()
                failing_publisher.publish.side_effect = Exception("Publisher failed")
                rate_limiter.add_event_publisher(failing_publisher)
                
                # Also add a working publisher to ensure others still work
                working_publisher = AsyncMock()
                rate_limiter.add_event_publisher(working_publisher)
                
                # Publish an event
                event = RateLimiterOnSuccessEvent(rate_limiter.name)
                loop.run_until_complete(rate_limiter._publish_event(event))
                
                # Both publishers should have been called despite the failure
                failing_publisher.publish.assert_called_once_with(event)
                working_publisher.publish.assert_called_once_with(event)
            finally:
                loop.close()
        
        run_test()

    def test_add_event_publisher(self, rate_limiter):
        """Test adding event publisher (line 221)."""
        publisher = Mock()
        rate_limiter.add_event_publisher(publisher)
        assert publisher in rate_limiter._event_publishers

    def test_remove_event_publisher_not_present(self, rate_limiter):
        """Test removing event publisher that doesn't exist (lines 230-231)."""
        publisher = Mock()
        # Should not raise exception when removing non-existent publisher
        rate_limiter.remove_event_publisher(publisher)
        assert len(rate_limiter._event_publishers) == 0

    def test_get_metrics_under_lock(self, rate_limiter):
        """Test get_metrics method (lines 240-246)."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Use a permission first
                loop.run_until_complete(rate_limiter._reserve_permission())
                
                # Get metrics
                metrics = loop.run_until_complete(rate_limiter.get_metrics())
                
                assert metrics["name"] == "test-limiter"
                assert metrics["available_permissions"] == 1  # One used
                assert metrics["limit_for_period"] == 2
                assert "current_cycle" in metrics
            finally:
                loop.close()
        
        run_test()

    def test_reset_under_lock(self, rate_limiter):
        """Test reset method (lines 250-255)."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Use permissions first
                loop.run_until_complete(rate_limiter._reserve_permission())
                loop.run_until_complete(rate_limiter._reserve_permission())
                
                # Verify permissions are used
                assert rate_limiter._state.active_permissions == 0
                
                # Reset
                loop.run_until_complete(rate_limiter.reset())
                
                # Verify reset state
                assert rate_limiter._state.active_permissions == 2
                assert rate_limiter._state.active_cycle == 0
                assert rate_limiter._state.nanoseconds_to_wait == 0
            finally:
                loop.close()
        
        run_test()

    def test_multiple_cycle_refresh(self, rate_limiter):
        """Test refresh with multiple cycles passed."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Use up permissions
                loop.run_until_complete(rate_limiter._reserve_permission())
                loop.run_until_complete(rate_limiter._reserve_permission())
                
                # Get current time before mocking
                current_time = time.time_ns()
                
                # Mock time to simulate multiple cycles passed
                with patch('time.time_ns') as mock_time:
                    # Move to 3 cycles later
                    mock_time.return_value = current_time + (3 * 1_000_000_000)  # 3 seconds later
                    
                    # Should refresh to limit_for_period (not 3 * limit_for_period)
                    wait_time = loop.run_until_complete(rate_limiter._reserve_permission())
                    assert wait_time == 0
                    assert rate_limiter._state.active_permissions == 1  # limit_for_period - 1
            finally:
                loop.close()
        
        run_test()

    def test_concurrent_state_access(self, rate_limiter):
        """Test concurrent access to rate limiter state."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = []
                
                async def concurrent_access():
                    try:
                        wait_time = await rate_limiter._reserve_permission()
                        results.append(("success", wait_time))
                    except Exception as e:
                        results.append(("error", str(e)))
                
                # Run many concurrent accesses
                tasks = [concurrent_access() for _ in range(10)]
                loop.run_until_complete(asyncio.gather(*tasks))
                
                # Should have 2 immediate successes and 8 waiting
                immediate_successes = [r for r in results if r[0] == "success" and r[1] == 0]
                waiting_requests = [r for r in results if r[0] == "success" and r[1] > 0]
                
                assert len(immediate_successes) == 2
                assert len(waiting_requests) == 8
            finally:
                loop.close()
        
        run_test()

    def test_edge_case_zero_wait_time(self, rate_limiter):
        """Test edge case where wait time calculation results in exactly zero."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Mock time to be exactly at cycle boundary
                with patch('time.time_ns') as mock_time:
                    cycle_length_nanos = int(rate_limiter.config.limit_refresh_period.total_seconds() * 1_000_000_000)
                    current_time = cycle_length_nanos  # Exactly at second cycle start
                    mock_time.return_value = current_time
                    
                    wait_time = loop.run_until_complete(rate_limiter._reserve_permission())
                    assert wait_time == 0  # Should be immediate since we're at cycle boundary
            finally:
                loop.close()
        
        run_test()

    def test_nanosecond_wait_time_conversion(self, rate_limiter):
        """Test precise nanosecond to second conversion in wait."""
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Use up permissions
                loop.run_until_complete(rate_limiter._reserve_permission())
                loop.run_until_complete(rate_limiter._reserve_permission())
                
                with patch('asyncio.sleep') as mock_sleep:
                    async def dummy_func():
                        return "result"
                    
                    # Execute function that should wait
                    result = loop.run_until_complete(
                        rate_limiter._execute_async(dummy_func)
                    )
                    
                    # Verify sleep was called with proper conversion
                    assert mock_sleep.called
                    sleep_time = mock_sleep.call_args[0][0]
                    assert 0 < sleep_time <= 1.0  # Should be reasonable wait time
                    assert result == "result"
            finally:
                loop.close()
        
        run_test()

    def test_state_dataclass_attributes(self):
        """Test RateLimiterState attributes."""
        state = RateLimiterState(
            active_permissions=5,
            active_cycle=1,
            nanoseconds_to_wait=1000
        )
        
        # Verify attributes
        assert state.active_permissions == 5
        assert state.active_cycle == 1
        assert state.nanoseconds_to_wait == 1000

    def test_thread_safety_with_sync_decorator(self, rate_limiter):
        """Test thread safety when using sync decorator."""
        results = []
        
        @rate_limiter
        def thread_test_func(thread_id):
            return f"result_{thread_id}"
        
        def worker(thread_id):
            try:
                result = thread_test_func(thread_id)
                results.append(("success", result))
            except RequestNotPermitted:
                results.append(("limited", thread_id))
            except Exception as e:
                results.append(("error", str(e)))
        
        # Run multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Should have some successes and some rate limited
        successes = [r for r in results if r[0] == "success"]
        limited = [r for r in results if r[0] == "limited"]
        
        assert len(successes) >= 2  # At least limit_for_period should succeed
        assert len(limited) >= 0   # Some may be rate limited
        assert len(results) == 5   # All threads should have completed