"""Edge case and stress tests for Rate Limiter implementations."""

import asyncio
import time
from datetime import timedelta
from unittest.mock import Mock, AsyncMock, patch
import threading
import concurrent.futures

import pytest

from resilience4py.ratelimiter.atomic_rate_limiter import (
    AtomicRateLimiter, RateLimiterState, RequestNotPermitted
)
from resilience4py.ratelimiter import RateLimiter, rate_limit
from resilience4py.ratelimiter.config import RateLimiterConfig


class TestRateLimiterEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_zero_timeout_duration(self):
        """Test rate limiter with zero timeout duration."""
        config = RateLimiterConfig(
            limit_for_period=1,
            limit_refresh_period=timedelta(seconds=1),
            timeout_duration=timedelta(seconds=0)
        )
        limiter = AtomicRateLimiter("zero-timeout", config)
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # First permission should work
                wait_time = loop.run_until_complete(limiter._reserve_permission())
                assert wait_time == 0
                
                # Second should immediately timeout
                wait_time = loop.run_until_complete(limiter._reserve_permission())
                assert wait_time < 0  # Negative indicates timeout
            finally:
                loop.close()
        
        run_test()

    def test_very_large_limit_for_period(self):
        """Test rate limiter with very large limit."""
        config = RateLimiterConfig(
            limit_for_period=1_000_000,
            limit_refresh_period=timedelta(seconds=1),
            timeout_duration=timedelta(seconds=1)
        )
        limiter = AtomicRateLimiter("large-limit", config)
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Should be able to acquire many permissions
                for _ in range(100):
                    wait_time = loop.run_until_complete(limiter._reserve_permission())
                    assert wait_time == 0
                
                # Should still have plenty left
                metrics = loop.run_until_complete(limiter.get_metrics())
                assert metrics["available_permissions"] == 1_000_000 - 100
            finally:
                loop.close()
        
        run_test()

    def test_microsecond_precision_timing(self):
        """Test rate limiter with microsecond precision."""
        config = RateLimiterConfig(
            limit_for_period=1,
            limit_refresh_period=timedelta(microseconds=100),  # 100 microseconds
            timeout_duration=timedelta(seconds=1)
        )
        limiter = AtomicRateLimiter("micro-precision", config)
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Mock time to ensure consistent timing
                current_time = time.monotonic_ns()
                with patch('time.monotonic_ns', return_value=current_time):
                    # Use the permission
                    wait_time = loop.run_until_complete(limiter._reserve_permission())
                    assert wait_time == 0
                    
                    # Next should require very short wait
                    wait_time = loop.run_until_complete(limiter._reserve_permission())
                    assert 0 < wait_time < 200_000  # Should be around 100,000 nanoseconds
            finally:
                loop.close()
        
        run_test()

    def test_boundary_cycle_transition(self):
        """Test rate limiter at exact cycle boundary."""
        config = RateLimiterConfig(
            limit_for_period=2,
            limit_refresh_period=timedelta(seconds=1),
            timeout_duration=timedelta(seconds=5)
        )
        limiter = AtomicRateLimiter("boundary-test", config)
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Use all permissions
                loop.run_until_complete(limiter._reserve_permission())
                loop.run_until_complete(limiter._reserve_permission())
                
                # Get current time and calculate next cycle start
                current_time = time.monotonic_ns()
                cycle_length_nanos = int(config.limit_refresh_period.total_seconds() * 1_000_000_000)
                current_cycle = current_time // cycle_length_nanos
                next_cycle_start = (current_cycle + 1) * cycle_length_nanos

                # Mock time to be exactly at next cycle start
                with patch('time.monotonic_ns') as mock_time:
                    # Set time to exactly 1 cycle later
                    mock_time.return_value = next_cycle_start
                    
                    # Should immediately get permission (no wait)
                    wait_time = loop.run_until_complete(limiter._reserve_permission())
                    assert wait_time == 0
                    assert limiter._state.active_permissions == 1  # limit - 1
                    assert limiter._state.active_cycle == current_cycle + 1
            finally:
                loop.close()
        
        run_test()

    def test_massive_cycle_jump(self):
        """Test rate limiter with massive time jump."""
        config = RateLimiterConfig(
            limit_for_period=5,
            limit_refresh_period=timedelta(seconds=1),
            timeout_duration=timedelta(seconds=1)
        )
        limiter = AtomicRateLimiter("massive-jump", config)
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Use all permissions
                for _ in range(5):
                    loop.run_until_complete(limiter._reserve_permission())
                
                # Get current time and calculate future time
                current_time = time.monotonic_ns()
                cycle_length_nanos = int(config.limit_refresh_period.total_seconds() * 1_000_000_000)
                current_cycle = current_time // cycle_length_nanos
                future_cycle = current_cycle + 1000
                future_time = future_cycle * cycle_length_nanos

                # Mock time to jump 1000 cycles into the future
                with patch('time.monotonic_ns') as mock_time:
                    # Jump 1000 cycles (1000 seconds)
                    mock_time.return_value = future_time
                    
                    # Should still only get limit_for_period permissions, not 1000 * limit_for_period
                    wait_time = loop.run_until_complete(limiter._reserve_permission())
                    assert wait_time == 0
                    assert limiter._state.active_permissions == 4  # limit - 1
                    assert limiter._state.active_cycle == future_cycle
            finally:
                loop.close()
        
        run_test()


class TestConcurrencyStress:
    """Stress tests for concurrent access."""
    
    def test_high_concurrency_async(self):
        """Test high concurrency with async functions."""
        config = RateLimiterConfig(
            limit_for_period=10,
            limit_refresh_period=timedelta(seconds=1),
            timeout_duration=timedelta(milliseconds=100)
        )
        limiter = AtomicRateLimiter("high-concurrency", config)
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = []
                
                @limiter
                async def concurrent_task(task_id):
                    return f"task_{task_id}_completed"
                
                async def run_concurrent_tasks():
                    tasks = []
                    for i in range(50):  # 50 concurrent tasks
                        task = concurrent_task(i)
                        tasks.append(task)
                    
                    # Run all tasks concurrently
                    for task in tasks:
                        try:
                            result = await task
                            results.append(("success", result))
                        except RequestNotPermitted:
                            results.append(("limited", None))
                        except Exception as e:
                            results.append(("error", str(e)))
                
                loop.run_until_complete(run_concurrent_tasks())
                
                # Should have exactly limit_for_period successes
                successes = [r for r in results if r[0] == "success"]
                limited = [r for r in results if r[0] == "limited"]
                
                assert len(successes) == 10  # Exactly the limit
                assert len(limited) == 40   # The rest should be limited
            finally:
                loop.close()
        
        run_test()

    def test_thread_pool_stress(self):
        """Test rate limiter under thread pool stress."""
        config = RateLimiterConfig(
            limit_for_period=5,
            limit_refresh_period=timedelta(seconds=1),
            timeout_duration=timedelta(milliseconds=50)
        )
        limiter = RateLimiter("thread-stress", config)
        
        results = []
        
        @limiter
        def thread_task(task_id):
            return f"thread_task_{task_id}"
        
        def worker(task_id):
            try:
                result = thread_task(task_id)
                results.append(("success", result))
            except RequestNotPermitted:
                results.append(("limited", task_id))
            except Exception as e:
                results.append(("error", str(e)))
        
        # Use ThreadPoolExecutor for true parallelism
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker, i) for i in range(30)]
            concurrent.futures.wait(futures)
        
        # Analyze results
        successes = [r for r in results if r[0] == "success"]
        limited = [r for r in results if r[0] == "limited"]
        errors = [r for r in results if r[0] == "error"]
        
        assert len(successes) >= 5    # At least the limit should succeed
        assert len(limited) >= 20     # Many should be limited
        assert len(errors) == 0       # No errors should occur
        assert len(results) == 30     # All tasks should complete

    def test_rapid_acquire_permission_stress(self):
        """Stress test rapid acquire_permission calls."""
        config = RateLimiterConfig(
            limit_for_period=3,
            limit_refresh_period=timedelta(milliseconds=100),
            timeout_duration=timedelta(milliseconds=10)
        )
        rate_limiter = RateLimiter("rapid-acquire", config)
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = []
                
                async def rapid_acquire_task():
                    for _ in range(100):  # 100 rapid calls
                        result = await rate_limiter.acquire_permission()
                        results.append(result)
                
                start_time = time.time()
                loop.run_until_complete(rapid_acquire_task())
                elapsed = time.time() - start_time
                
                # Should complete quickly despite many calls
                assert elapsed < 5.0  # Should finish within 5 seconds
                
                # Should have mix of True and False
                true_count = sum(1 for r in results if r is True)
                false_count = sum(1 for r in results if r is False)
                
                assert true_count >= 3    # At least initial limit should succeed
                assert false_count >= 90  # Most should be rate limited
            finally:
                loop.close()
        
        run_test()


class TestErrorHandlingEdgeCases:
    """Test error handling in edge cases."""
    
    def test_event_publisher_chain_failure(self):
        """Test multiple event publishers with failures."""
        config = RateLimiterConfig(limit_for_period=1)
        limiter = AtomicRateLimiter("publisher-chain", config)
        
        # Add multiple publishers, some failing
        working_publisher1 = AsyncMock()
        failing_publisher1 = AsyncMock()
        failing_publisher1.publish.side_effect = RuntimeError("Publisher 1 failed")
        working_publisher2 = AsyncMock()
        failing_publisher2 = AsyncMock()
        failing_publisher2.publish.side_effect = ValueError("Publisher 2 failed")
        
        limiter.add_event_publisher(working_publisher1)
        limiter.add_event_publisher(failing_publisher1)
        limiter.add_event_publisher(working_publisher2)
        limiter.add_event_publisher(failing_publisher2)
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                @limiter
                async def test_func():
                    return "success"
                
                # Should succeed despite publisher failures
                result = loop.run_until_complete(test_func())
                assert result == "success"
                
                # All publishers should have been called
                working_publisher1.publish.assert_called_once()
                failing_publisher1.publish.assert_called_once()
                working_publisher2.publish.assert_called_once()
                failing_publisher2.publish.assert_called_once()
            finally:
                loop.close()
        
        run_test()

    def test_decorator_on_non_callable(self):
        """Test decorator applied to non-callable object."""
        config = RateLimiterConfig(limit_for_period=1)
        limiter = AtomicRateLimiter("non-callable", config)
        
        # This should raise an error when trying to use as decorator
        try:
            result = limiter("not_a_function")
            # If no error, at least verify it didn't work as expected
            assert result is not None
        except (TypeError, AttributeError):
            # Expected behavior - decorator can't handle non-callable
            pass



class TestPerformanceEdgeCases:
    """Test performance-related edge cases."""
    
    def test_very_frequent_refresh_periods(self):
        """Test with extremely frequent refresh periods."""
        config = RateLimiterConfig(
            limit_for_period=1,
            limit_refresh_period=timedelta(microseconds=1),  # 1 microsecond!
            timeout_duration=timedelta(milliseconds=1)
        )
        limiter = AtomicRateLimiter("frequent-refresh", config)
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Should be able to get permissions very quickly
                start_time = time.time()
                
                for _ in range(10):
                    wait_time = loop.run_until_complete(limiter._reserve_permission())
                    if wait_time > 0:
                        # If we need to wait, it should be very short
                        assert wait_time < 10_000  # Less than 10 microseconds
                
                elapsed = time.time() - start_time
                assert elapsed < 0.1  # Should complete very quickly
            finally:
                loop.close()
        
        run_test()

    def test_memory_usage_with_many_cycles(self):
        """Test memory usage doesn't grow with many cycles."""
        config = RateLimiterConfig(
            limit_for_period=1,
            limit_refresh_period=timedelta(microseconds=100)
        )
        limiter = AtomicRateLimiter("memory-test", config)
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Simulate some cycles passing
                with patch('time.monotonic_ns') as mock_time:
                    base_time = 1_000_000_000  # Start at 1 second in nanos
                    
                    for i in range(10):
                        # Each iteration simulates 100 microseconds later
                        mock_time.return_value = base_time + (i * 100_000)  # 100,000 nanos = 100 microseconds
                        loop.run_until_complete(limiter._reserve_permission())
                    
                    # State should reflect the cycles
                    assert limiter._state.active_cycle >= 5
                    assert limiter._state.active_permissions <= config.limit_for_period
            finally:
                loop.close()
        
        run_test()

    def test_time_precision_edge_cases(self):
        """Test edge cases in time precision handling."""
        config = RateLimiterConfig(
            limit_for_period=1,
            limit_refresh_period=timedelta(seconds=1)
        )
        limiter = AtomicRateLimiter("time-precision", config)
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Test with time exactly at nanosecond boundaries
                with patch('time.monotonic_ns') as mock_time:
                    # Test at exactly 0 nanoseconds
                    mock_time.return_value = 0
                    wait_time = loop.run_until_complete(limiter._reserve_permission())
                    assert wait_time == 0
                    
                    # Test at maximum nanosecond value that doesn't overflow
                    mock_time.return_value = 999_999_999  # Just under 1 second
                    wait_time = loop.run_until_complete(limiter._reserve_permission())
                    assert wait_time > 0  # Should need to wait until next cycle
            finally:
                loop.close()
        
        run_test()