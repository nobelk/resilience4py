"""Tests for the main Retry decorator."""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock
from datetime import timedelta

from resilience4py.retry import (
    Retry, RetryConfig, MaxRetriesExceeded,
    FixedInterval, ExponentialBackoff,
    RetryOnRetryEvent, RetryOnSuccessEvent, 
    RetryOnErrorEvent, RetryOnIgnoredErrorEvent
)


class TestRetryInit:
    """Test suite for Retry initialization."""

    def test_retry_with_default_config(self):
        """Test creating Retry with default configuration."""
        retry = Retry("test-retry")
        
        assert retry.name == "test-retry"
        assert retry.config.max_attempts == 3
        assert retry.config.wait_duration == timedelta(milliseconds=500)

    def test_retry_with_custom_config(self):
        """Test creating Retry with custom configuration."""
        config = RetryConfig(
            max_attempts=5,
            wait_duration=timedelta(seconds=2)
        )
        retry = Retry("test-retry", config)
        
        assert retry.name == "test-retry"
        assert retry.config.max_attempts == 5
        assert retry.config.wait_duration == timedelta(seconds=2)

    def test_retry_empty_name_raises(self):
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="Retry name cannot be empty"):
            Retry("")

    def test_retry_invalid_config_raises(self):
        """Test that invalid config raises during initialization."""
        config = RetryConfig(max_attempts=0)
        
        with pytest.raises(ValueError, match="max_attempts must be greater than 0"):
            Retry("test-retry", config)


class TestRetrySyncFunctions:
    """Test suite for Retry with synchronous functions."""

    def test_sync_success_first_attempt(self):
        """Test synchronous function succeeds on first attempt."""
        retry = Retry("test-retry", RetryConfig(max_attempts=3))
        mock_func = Mock(return_value="success")
        
        @retry
        def test_func():
            return mock_func()
        
        result = test_func()
        
        assert result == "success"
        assert mock_func.call_count == 1

    def test_sync_success_after_retries(self):
        """Test synchronous function succeeds after retries."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=3,
            wait_duration=timedelta(milliseconds=10)
        ))
        mock_func = Mock(side_effect=[ValueError("fail"), ValueError("fail"), "success"])
        
        @retry
        def test_func():
            return mock_func()
        
        start_time = time.time()
        result = test_func()
        duration = time.time() - start_time
        
        assert result == "success"
        assert mock_func.call_count == 3
        # Should have waited twice (2 * 10ms)
        assert duration >= 0.02

    def test_sync_max_retries_exceeded(self):
        """Test synchronous function exceeds max retries."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=3,
            fail_after_max_attempts=True,
            wait_duration=timedelta(milliseconds=1)
        ))
        mock_func = Mock(side_effect=ValueError("always fails"))
        
        @retry
        def test_func():
            return mock_func()
        
        with pytest.raises(MaxRetriesExceeded) as exc_info:
            test_func()
        
        assert mock_func.call_count == 3
        assert exc_info.value.attempts == 3
        assert isinstance(exc_info.value.last_exception, ValueError)
        assert "exhausted after 3 attempts" in str(exc_info.value)

    def test_sync_reraise_last_exception(self):
        """Test synchronous function re-raises last exception."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=2,
            fail_after_max_attempts=False,
            wait_duration=timedelta(milliseconds=1)
        ))
        mock_func = Mock(side_effect=ValueError("custom error"))
        
        @retry
        def test_func():
            return mock_func()
        
        with pytest.raises(ValueError, match="custom error"):
            test_func()
        
        assert mock_func.call_count == 2

    def test_sync_with_arguments(self):
        """Test synchronous function with arguments."""
        retry = Retry("test-retry", RetryConfig(max_attempts=2))
        mock_func = Mock(side_effect=[ValueError(), "result"])
        
        @retry
        def test_func(a, b, c=None):
            return mock_func(a, b, c)
        
        result = test_func(1, 2, c=3)
        
        assert result == "result"
        assert mock_func.call_count == 2
        mock_func.assert_called_with(1, 2, 3)

    def test_sync_abort_exception(self):
        """Test synchronous function with abort exception."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=3,
            abort_exceptions=[KeyError]
        ))
        mock_func = Mock(side_effect=KeyError("abort"))
        
        @retry
        def test_func():
            return mock_func()
        
        with pytest.raises(KeyError, match="abort"):
            test_func()
        
        # Should not retry on abort exception
        assert mock_func.call_count == 1

    def test_sync_retry_on_specific_exceptions(self):
        """Test retry only on specific exceptions."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=3,
            retry_exceptions=[ValueError, TypeError]
        ))
        
        # Should retry on ValueError
        mock_func = Mock(side_effect=[ValueError(), "success"])
        
        @retry
        def test_func():
            return mock_func()
        
        assert test_func() == "success"
        assert mock_func.call_count == 2
        
        # Should not retry on KeyError
        mock_func = Mock(side_effect=KeyError("not retryable"))
        
        @retry
        def test_func2():
            return mock_func()
        
        with pytest.raises(KeyError):
            test_func2()
        
        assert mock_func.call_count == 1

    def test_sync_custom_exception_predicate(self):
        """Test custom exception predicate."""
        def should_retry(e):
            return "retry" in str(e)
        
        retry = Retry("test-retry", RetryConfig(
            max_attempts=3,
            retry_on_exception=should_retry
        ))
        
        # Should retry
        mock_func = Mock(side_effect=[ValueError("please retry"), "success"])
        
        @retry
        def test_func():
            return mock_func()
        
        assert test_func() == "success"
        assert mock_func.call_count == 2
        
        # Should not retry
        mock_func = Mock(side_effect=ValueError("do not"))
        
        @retry
        def test_func2():
            return mock_func()
        
        with pytest.raises(ValueError):
            test_func2()
        
        assert mock_func.call_count == 1

    def test_sync_retry_on_result(self):
        """Test retry based on result."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=3,
            retry_on_result=lambda x: x == "retry",
            wait_duration=timedelta(milliseconds=1)
        ))
        mock_func = Mock(side_effect=["retry", "retry", "success"])
        
        @retry
        def test_func():
            return mock_func()
        
        result = test_func()
        
        assert result == "success"
        assert mock_func.call_count == 3

    def test_sync_retry_on_result_max_attempts(self):
        """Test retry on result when max attempts reached."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=2,
            retry_on_result=lambda x: x == "retry"
        ))
        mock_func = Mock(return_value="retry")
        
        @retry
        def test_func():
            return mock_func()
        
        # Should return the result even though it matches retry condition
        result = test_func()
        
        assert result == "retry"
        assert mock_func.call_count == 2

    def test_sync_with_interval_function(self):
        """Test synchronous retry with custom interval function."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=3,
            interval_function=FixedInterval(0.01)  # 10ms
        ))
        mock_func = Mock(side_effect=[ValueError(), ValueError(), "success"])
        
        @retry
        def test_func():
            return mock_func()
        
        start_time = time.time()
        result = test_func()
        duration = time.time() - start_time
        
        assert result == "success"
        assert mock_func.call_count == 3
        # Should have waited twice
        assert duration >= 0.02


class TestRetryAsyncFunctions:
    """Test suite for Retry with asynchronous functions."""

    @pytest.mark.asyncio
    async def test_async_success_first_attempt(self):
        """Test asynchronous function succeeds on first attempt."""
        retry = Retry("test-retry", RetryConfig(max_attempts=3))
        mock_func = AsyncMock(return_value="success")
        
        @retry
        async def test_func():
            return await mock_func()
        
        result = await test_func()
        
        assert result == "success"
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_async_success_after_retries(self):
        """Test asynchronous function succeeds after retries."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=3,
            wait_duration=timedelta(milliseconds=10)
        ))
        mock_func = AsyncMock(side_effect=[ValueError("fail"), ValueError("fail"), "success"])
        
        @retry
        async def test_func():
            return await mock_func()
        
        start_time = time.time()
        result = await test_func()
        duration = time.time() - start_time
        
        assert result == "success"
        assert mock_func.call_count == 3
        # Should have waited twice
        assert duration >= 0.02

    @pytest.mark.asyncio
    async def test_async_max_retries_exceeded(self):
        """Test asynchronous function exceeds max retries."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=3,
            fail_after_max_attempts=True,
            wait_duration=timedelta(milliseconds=1)
        ))
        mock_func = AsyncMock(side_effect=ValueError("always fails"))
        
        @retry
        async def test_func():
            return await mock_func()
        
        with pytest.raises(MaxRetriesExceeded) as exc_info:
            await test_func()
        
        assert mock_func.call_count == 3
        assert exc_info.value.attempts == 3
        assert isinstance(exc_info.value.last_exception, ValueError)

    @pytest.mark.asyncio
    async def test_async_reraise_last_exception(self):
        """Test asynchronous function re-raises last exception."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=2,
            fail_after_max_attempts=False
        ))
        mock_func = AsyncMock(side_effect=ValueError("custom error"))
        
        @retry
        async def test_func():
            return await mock_func()
        
        with pytest.raises(ValueError, match="custom error"):
            await test_func()
        
        assert mock_func.call_count == 2

    @pytest.mark.asyncio
    async def test_async_with_arguments(self):
        """Test asynchronous function with arguments."""
        retry = Retry("test-retry", RetryConfig(max_attempts=2))
        mock_func = AsyncMock(side_effect=[ValueError(), "result"])
        
        @retry
        async def test_func(a, b, c=None):
            return await mock_func(a, b, c)
        
        result = await test_func(1, 2, c=3)
        
        assert result == "result"
        assert mock_func.call_count == 2
        mock_func.assert_called_with(1, 2, 3)

    @pytest.mark.asyncio
    async def test_async_abort_exception(self):
        """Test asynchronous function with abort exception."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=3,
            abort_exceptions=[KeyError]
        ))
        mock_func = AsyncMock(side_effect=KeyError("abort"))
        
        @retry
        async def test_func():
            return await mock_func()
        
        with pytest.raises(KeyError, match="abort"):
            await test_func()
        
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_async_retry_on_result(self):
        """Test async retry based on result."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=3,
            retry_on_result=lambda x: x == "retry",
            wait_duration=timedelta(milliseconds=1)
        ))
        mock_func = AsyncMock(side_effect=["retry", "retry", "success"])
        
        @retry
        async def test_func():
            return await mock_func()
        
        result = await test_func()
        
        assert result == "success"
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_async_with_exponential_backoff(self):
        """Test async retry with exponential backoff."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=4,
            interval_function=ExponentialBackoff(
                initial_interval=0.01,  # 10ms
                multiplier=2.0
            )
        ))
        mock_func = AsyncMock(side_effect=[ValueError(), ValueError(), ValueError(), "success"])
        
        @retry
        async def test_func():
            return await mock_func()
        
        start_time = time.time()
        result = await test_func()
        duration = time.time() - start_time
        
        assert result == "success"
        assert mock_func.call_count == 4
        # Should have waited: 10ms + 20ms + 40ms = 70ms
        assert duration >= 0.07


class TestRetryEvents:
    """Test suite for Retry events."""

    @pytest.mark.asyncio
    async def test_on_retry_event(self):
        """Test on_retry event is emitted correctly."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=3,
            wait_duration=timedelta(milliseconds=10)
        ))
        
        events = []
        
        @retry.on_retry
        def handle_retry(event: RetryOnRetryEvent):
            events.append(event)
        
        mock_func = AsyncMock(side_effect=[ValueError("fail"), "success"])
        
        @retry
        async def test_func():
            return await mock_func()
        
        await test_func()
        
        assert len(events) == 1
        assert events[0].retry_name == "test-retry"
        assert events[0].attempt == 1
        assert events[0].is_exception_retry is True
        assert isinstance(events[0].exception, ValueError)
        assert events[0].wait_interval == 0.01

    @pytest.mark.asyncio
    async def test_on_success_event_first_attempt(self):
        """Test on_success event for first attempt success."""
        retry = Retry("test-retry", RetryConfig(max_attempts=3))
        
        events = []
        
        @retry.on_success
        def handle_success(event: RetryOnSuccessEvent):
            events.append(event)
        
        mock_func = AsyncMock(return_value="success")
        
        @retry
        async def test_func():
            return await mock_func()
        
        await test_func()
        
        assert len(events) == 1
        assert events[0].retry_name == "test-retry"
        assert events[0].attempt == 1
        assert events[0].last_exception is None
        assert events[0].had_retries is False

    @pytest.mark.asyncio
    async def test_on_success_event_after_retries(self):
        """Test on_success event after retries."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=3,
            wait_duration=timedelta(milliseconds=1)
        ))
        
        events = []
        
        @retry.on_success
        def handle_success(event: RetryOnSuccessEvent):
            events.append(event)
        
        mock_func = AsyncMock(side_effect=[ValueError("fail"), "success"])
        
        @retry
        async def test_func():
            return await mock_func()
        
        await test_func()
        
        assert len(events) == 1
        assert events[0].retry_name == "test-retry"
        assert events[0].attempt == 2
        assert isinstance(events[0].last_exception, ValueError)
        assert events[0].had_retries is True
        assert events[0].retry_count == 1

    @pytest.mark.asyncio
    async def test_on_error_event(self):
        """Test on_error event when all retries exhausted."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=2,
            fail_after_max_attempts=True,
            wait_duration=timedelta(milliseconds=1)
        ))
        
        events = []
        
        @retry.on_error
        def handle_error(event: RetryOnErrorEvent):
            events.append(event)
        
        mock_func = AsyncMock(side_effect=ValueError("always fails"))
        
        @retry
        async def test_func():
            return await mock_func()
        
        with pytest.raises(MaxRetriesExceeded):
            await test_func()
        
        assert len(events) == 1
        assert events[0].retry_name == "test-retry"
        assert events[0].attempt == 2
        assert isinstance(events[0].last_exception, ValueError)
        assert events[0].total_attempts == 2

    @pytest.mark.asyncio
    async def test_on_ignored_error_event(self):
        """Test on_ignored_error event for non-retryable exceptions."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=3,
            abort_exceptions=[KeyError]
        ))
        
        events = []
        
        @retry.on_ignored_error
        def handle_ignored(event: RetryOnIgnoredErrorEvent):
            events.append(event)
        
        mock_func = AsyncMock(side_effect=KeyError("abort"))
        
        @retry
        async def test_func():
            return await mock_func()
        
        with pytest.raises(KeyError):
            await test_func()
        
        assert len(events) == 1
        assert events[0].retry_name == "test-retry"
        assert events[0].attempt == 1
        assert isinstance(events[0].exception, KeyError)
        assert events[0].exception_type == KeyError

    @pytest.mark.asyncio
    async def test_multiple_event_handlers(self):
        """Test multiple handlers for the same event."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=2,
            wait_duration=timedelta(milliseconds=1)
        ))
        
        handler1_calls = []
        handler2_calls = []
        
        @retry.on_retry
        def handler1(event):
            handler1_calls.append(event)
        
        @retry.on_retry
        def handler2(event):
            handler2_calls.append(event)
        
        mock_func = AsyncMock(side_effect=[ValueError(), "success"])
        
        @retry
        async def test_func():
            return await mock_func()
        
        await test_func()
        
        assert len(handler1_calls) == 1
        assert len(handler2_calls) == 1

    @pytest.mark.asyncio
    async def test_async_event_handler(self):
        """Test async event handlers."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=2,
            wait_duration=timedelta(milliseconds=1)
        ))
        
        events = []
        
        @retry.on_retry
        async def async_handler(event):
            await asyncio.sleep(0.001)  # Simulate async work
            events.append(event)
        
        mock_func = AsyncMock(side_effect=[ValueError(), "success"])
        
        @retry
        async def test_func():
            return await mock_func()
        
        await test_func()
        
        assert len(events) == 1


    @pytest.mark.asyncio
    async def test_retry_on_result_event(self):
        """Test events when retrying based on result."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=3,
            retry_on_result=lambda x: x == "retry",
            wait_duration=timedelta(milliseconds=1)
        ))
        
        retry_events = []
        success_events = []
        
        @retry.on_retry
        def handle_retry(event):
            retry_events.append(event)
        
        @retry.on_success
        def handle_success(event):
            success_events.append(event)
        
        mock_func = AsyncMock(side_effect=["retry", "retry", "success"])
        
        @retry
        async def test_func():
            return await mock_func()
        
        await test_func()
        
        assert len(retry_events) == 2
        assert retry_events[0].is_exception_retry is False
        assert retry_events[0].result == "retry"
        assert retry_events[1].result == "retry"
        
        assert len(success_events) == 1
        assert success_events[0].attempt == 3


class TestRetryEdgeCases:
    """Test suite for edge cases and special scenarios."""

    def test_sync_in_async_context(self):
        """Test sync function decorated with retry in async context."""
        retry = Retry("test-retry", RetryConfig(max_attempts=2))
        mock_func = Mock(side_effect=[ValueError(), "success"])
        
        @retry
        def sync_func():
            return mock_func()
        
        # When called from async context, it should still work
        async def async_caller():
            return sync_func()
        
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(async_caller())
            assert result == "success"
            assert mock_func.call_count == 2
        finally:
            loop.close()

    def test_function_metadata_preserved(self):
        """Test that decorated function preserves metadata."""
        retry = Retry("test-retry")
        
        @retry
        def test_func(a: int, b: str = "default") -> str:
            """Test function docstring."""
            return f"{a}-{b}"
        
        assert test_func.__name__ == "test_func"
        assert test_func.__doc__ == "Test function docstring."
        
        @retry
        async def async_func(x: float) -> float:
            """Async function docstring."""
            return x * 2
        
        assert async_func.__name__ == "async_func"
        assert async_func.__doc__ == "Async function docstring."

    def test_retry_with_no_attempts(self):
        """Test edge case with max_attempts=1 (no retries)."""
        retry = Retry("test-retry", RetryConfig(max_attempts=1))
        mock_func = Mock(side_effect=ValueError("fail"))
        
        @retry
        def test_func():
            return mock_func()
        
        with pytest.raises(ValueError, match="fail"):
            test_func()
        
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_concurrent_retries(self):
        """Test multiple concurrent retry operations."""
        retry = Retry("test-retry", RetryConfig(
            max_attempts=2,
            wait_duration=timedelta(milliseconds=10)
        ))
        
        call_counts = {}
        
        @retry
        async def test_func(id):
            nonlocal call_counts
            call_counts[id] = call_counts.get(id, 0) + 1
            if call_counts[id] == 1:  # Fail on first attempt
                raise ValueError(f"Fail {id}")
            return f"Success {id}"
        
        # Run multiple concurrent operations
        results = await asyncio.gather(
            test_func(1),
            test_func(2),
            test_func(3)
        )
        
        assert len(results) == 3
        assert all("Success" in r for r in results)
        assert sum(call_counts.values()) == 6  # Each function called twice

    def test_class_method_decoration(self):
        """Test retry decorator on class methods."""
        retry = Retry("test-retry", RetryConfig(max_attempts=2))
        
        class TestClass:
            def __init__(self):
                self.calls = 0
            
            @retry
            def method(self):
                self.calls += 1
                if self.calls == 1:
                    raise ValueError("First call fails")
                return "success"
            
            @retry
            async def async_method(self):
                self.calls += 1
                if self.calls == 1:
                    raise ValueError("First call fails")
                return "async success"
        
        obj = TestClass()
        assert obj.method() == "success"
        assert obj.calls == 2
        
        obj.calls = 0
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(obj.async_method())
            assert result == "async success"
            assert obj.calls == 2
        finally:
            loop.close()