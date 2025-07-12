"""Integration tests for the retry pattern.

These tests demonstrate real-world usage scenarios and ensure all components
work together correctly.
"""

import pytest
import asyncio
import time
import random
from unittest.mock import Mock, AsyncMock, patch
from datetime import timedelta

from resilience4py.retry import (
    Retry, RetryConfig, MaxRetriesExceeded,
    FixedInterval, ExponentialBackoff, LinearBackoff,
    RandomInterval, ExponentialRandomBackoff, FibonacciBackoff,
    RetryOnRetryEvent, RetryOnSuccessEvent,
    RetryOnErrorEvent, RetryOnIgnoredErrorEvent
)


class TestRetryIntegration:
    """Integration tests for retry pattern."""

    @pytest.mark.asyncio
    async def test_async_api_retry_scenario(self):
        """Test realistic async API retry scenario."""
        # Simulate an API that fails intermittently
        call_count = 0
        
        async def flaky_api_call():
            nonlocal call_count
            call_count += 1
            
            if call_count < 3:
                raise ConnectionError(f"Connection failed (attempt {call_count})")
            
            return {"status": "success", "data": "important data"}
        
        # Configure retry with exponential backoff
        retry = Retry("api-retry", RetryConfig(
            max_attempts=5,
            interval_function=ExponentialBackoff(
                initial_interval=0.1,
                multiplier=2.0,
                max_interval=2.0
            ),
            retry_exceptions=[ConnectionError, TimeoutError],
            abort_exceptions=[ValueError]  # Don't retry on bad input
        ))
        
        # Track events
        events = []
        
        @retry.on_retry
        def log_retry(event: RetryOnRetryEvent):
            events.append(('retry', event.attempt, event.wait_interval))
        
        @retry.on_success
        def log_success(event: RetryOnSuccessEvent):
            events.append(('success', event.attempt, event.total_duration))
        
        # Apply retry decorator
        @retry
        async def make_api_call():
            return await flaky_api_call()
        
        # Execute
        start = time.time()
        result = await make_api_call()
        duration = time.time() - start
        
        # Verify results
        assert result == {"status": "success", "data": "important data"}
        assert call_count == 3
        
        # Verify events
        assert len(events) == 3  # 2 retries + 1 success
        assert events[0][0] == 'retry'
        assert events[0][1] == 1  # First attempt failed
        assert events[0][2] == 0.1  # Initial interval
        
        assert events[1][0] == 'retry'
        assert events[1][1] == 2  # Second attempt failed
        assert events[1][2] == 0.2  # Doubled interval
        
        assert events[2][0] == 'success'
        assert events[2][1] == 3  # Third attempt succeeded
        
        # Total duration should include wait times
        assert duration >= 0.3  # At least 0.1 + 0.2 seconds of waiting

    def test_sync_database_retry_scenario(self):
        """Test realistic sync database retry scenario."""
        # Simulate a database that has temporary locks
        class DatabaseLockError(Exception):
            pass
        
        class DatabaseConnection:
            def __init__(self):
                self.attempt = 0
            
            def execute(self, query):
                self.attempt += 1
                if self.attempt < 3:
                    raise DatabaseLockError("Table is locked")
                return [{"id": 1, "name": "Test"}]
        
        db = DatabaseConnection()
        
        # Configure retry with linear backoff
        retry = Retry("db-retry", RetryConfig(
            max_attempts=5,
            interval_function=LinearBackoff(
                initial_interval=0.05,
                increment=0.05
            ),
            retry_exceptions=[DatabaseLockError]
        ))
        
        @retry
        def query_database(query):
            return db.execute(query)
        
        # Execute
        result = query_database("SELECT * FROM users")
        
        # Verify
        assert result == [{"id": 1, "name": "Test"}]
        assert db.attempt == 3

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self):
        """Test retry pattern working with circuit breaker concept."""
        # Simulate a service that goes down and recovers
        service_down_until = time.time() + 0.2  # Down for 200ms
        
        async def unreliable_service():
            if time.time() < service_down_until:
                raise ConnectionError("Service unavailable")
            return "Service response"
        
        # Configure retry to handle temporary outages
        retry = Retry("service-retry", RetryConfig(
            max_attempts=10,
            interval_function=FixedInterval(0.05),  # Check every 50ms
            retry_exceptions=[ConnectionError]
        ))
        
        retry_count = 0
        
        @retry.on_retry
        def count_retries(event):
            nonlocal retry_count
            retry_count += 1
        
        @retry
        async def call_service():
            return await unreliable_service()
        
        # Execute
        start = time.time()
        result = await call_service()
        duration = time.time() - start
        
        # Verify
        assert result == "Service response"
        assert retry_count >= 3  # Should have retried several times
        assert duration >= 0.2  # Service was down for 200ms

    def test_retry_with_validation(self):
        """Test retry with result validation."""
        # Simulate an API that returns partial results
        attempt_results = [
            {"status": "partial", "data": []},
            {"status": "partial", "data": [1, 2]},
            {"status": "complete", "data": [1, 2, 3, 4, 5]}
        ]
        
        call_count = 0
        
        def api_call():
            nonlocal call_count
            result = attempt_results[min(call_count, len(attempt_results) - 1)]
            call_count += 1
            return result
        
        # Retry until we get complete results
        retry = Retry("validation-retry", RetryConfig(
            max_attempts=5,
            interval_function=FixedInterval(0.01),
            retry_on_result=lambda r: r["status"] != "complete"
        ))
        
        @retry
        def get_complete_data():
            return api_call()
        
        # Execute
        result = get_complete_data()
        
        # Verify
        assert result["status"] == "complete"
        assert len(result["data"]) == 5
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_with_jitter(self):
        """Test retry with random jitter to avoid thundering herd."""
        # Track actual wait times
        wait_times = []
        
        original_sleep = asyncio.sleep
        
        async def track_sleep(duration):
            wait_times.append(duration)
            # Use very short sleep for testing
            await original_sleep(min(duration, 0.01))
        
        with patch('asyncio.sleep', track_sleep):
            retry = Retry("jitter-retry", RetryConfig(
                max_attempts=5,
                interval_function=ExponentialRandomBackoff(
                    initial_interval=0.1,
                    multiplier=2.0,
                    max_interval=1.0
                )
            ))
            
            attempt = 0
            
            @retry
            async def flaky_operation():
                nonlocal attempt
                attempt += 1
                if attempt < 4:
                    raise ValueError("Random failure")
                return "success"
            
            result = await flaky_operation()
            
            assert result == "success"
            assert len(wait_times) == 3
            
            # Verify jitter - wait times should be random but within bounds
            assert 0 <= wait_times[0] <= 0.1  # First retry
            assert 0 <= wait_times[1] <= 0.2  # Second retry
            assert 0 <= wait_times[2] <= 0.4  # Third retry
            
            # Wait times should be different (with high probability)
            assert len(set(wait_times)) > 1

    def test_retry_with_multiple_handlers(self):
        """Test retry with multiple event handlers for monitoring."""
        metrics = {
            "attempts": 0,
            "failures": 0,
            "success": False,
            "total_duration": 0,
            "wait_times": []
        }
        
        retry = Retry("monitored-retry", RetryConfig(
            max_attempts=3,
            interval_function=FixedInterval(0.01)
        ))
        
        @retry.on_retry
        def track_retry(event: RetryOnRetryEvent):
            metrics["failures"] += 1
            metrics["wait_times"].append(event.wait_interval)
        
        @retry.on_success
        def track_success(event: RetryOnSuccessEvent):
            metrics["attempts"] = event.attempt
            metrics["success"] = True
            metrics["total_duration"] = event.total_duration
        
        @retry.on_error
        def track_error(event: RetryOnErrorEvent):
            metrics["attempts"] = event.attempt
            metrics["total_duration"] = event.total_duration
        
        # Test successful retry
        attempt = 0
        
        @retry
        def operation():
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise ValueError("Fail")
            return "Success"
        
        result = operation()
        
        assert result == "Success"
        assert metrics["attempts"] == 3
        assert metrics["failures"] == 2
        assert metrics["success"] is True
        assert len(metrics["wait_times"]) == 2
        assert all(w == 0.01 for w in metrics["wait_times"])


    def test_fibonacci_backoff_scenario(self):
        """Test Fibonacci backoff for gradually increasing delays."""
        retry = Retry("fibonacci-retry", RetryConfig(
            max_attempts=7,
            interval_function=FibonacciBackoff(
                initial_interval=0.01,
                max_interval=0.1
            )
        ))
        
        actual_intervals = []
        original_sleep = time.sleep
        original_async_sleep = asyncio.sleep
        
        def track_sleep(duration):
            actual_intervals.append(duration)
            original_sleep(min(duration, 0.01))  # Speed up test
        
        async def track_async_sleep(duration):
            actual_intervals.append(duration)
            await original_async_sleep(min(duration, 0.01))  # Speed up test
        
        with patch('time.sleep', track_sleep), patch('asyncio.sleep', track_async_sleep):
            attempt = 0
            
            @retry
            def fibonacci_operation():
                nonlocal attempt
                attempt += 1
                if attempt < 6:
                    raise ValueError("Not ready")
                return "Ready"
            
            result = fibonacci_operation()
            
            assert result == "Ready"
            assert len(actual_intervals) == 5
            
            # Verify Fibonacci sequence (scaled by 0.01)
            expected = [0.01, 0.01, 0.02, 0.03, 0.05]
            for actual, expected_val in zip(actual_intervals, expected):
                assert abs(actual - expected_val) < 0.001

    @pytest.mark.asyncio
    async def test_abort_on_specific_errors(self):
        """Test that certain errors abort retry immediately."""
        retry = Retry("abort-retry", RetryConfig(
            max_attempts=5,
            retry_exceptions=[ConnectionError, TimeoutError],
            abort_exceptions=[ValueError, TypeError]
        ))
        
        events = []
        
        @retry.on_ignored_error
        def track_ignored(event: RetryOnIgnoredErrorEvent):
            events.append(event)
        
        # Test abort exception
        @retry
        async def bad_input_operation():
            raise ValueError("Invalid input - should not retry")
        
        with pytest.raises(ValueError, match="Invalid input"):
            await bad_input_operation()
        
        assert len(events) == 1
        assert events[0].exception_type == ValueError
        assert events[0].attempt == 1
        
        # Test retry exception
        events.clear()
        attempt = 0
        
        @retry
        async def network_operation():
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise ConnectionError("Network issue - should retry")
            return "Success"
        
        result = await network_operation()
        assert result == "Success"
        assert attempt == 3
        assert len(events) == 0  # No ignored errors

    def test_complex_retry_predicate(self):
        """Test complex retry logic with custom predicates."""
        def should_retry_error(error):
            # Retry on specific error codes
            if hasattr(error, 'code'):
                return error.code in [500, 502, 503]
            return False
        
        def should_retry_result(result):
            # Retry if result indicates temporary failure
            if isinstance(result, dict):
                return result.get('status') in ['pending', 'processing']
            return False
        
        retry = Retry("complex-retry", RetryConfig(
            max_attempts=5,
            interval_function=LinearBackoff(0.01, 0.01),
            retry_on_exception=should_retry_error,
            retry_on_result=should_retry_result
        ))
        
        # Test error-based retry
        class ApiError(Exception):
            def __init__(self, code):
                self.code = code
                super().__init__(f"API Error {code}")
        
        attempt = 0
        
        @retry
        def api_call():
            nonlocal attempt
            attempt += 1
            
            if attempt == 1:
                raise ApiError(503)  # Should retry
            elif attempt == 2:
                raise ApiError(404)  # Should not retry
            
            return {"status": "success"}
        
        with pytest.raises(ApiError) as exc:
            api_call()
        
        assert exc.value.code == 404
        assert attempt == 2
        
        # Test result-based retry
        attempt = 0
        results = [
            {"status": "pending"},
            {"status": "processing"},
            {"status": "completed", "data": "result"}
        ]
        
        @retry
        def polling_operation():
            nonlocal attempt
            result = results[attempt]
            attempt += 1
            return result
        
        final_result = polling_operation()
        assert final_result["status"] == "completed"
        assert attempt == 3