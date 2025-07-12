"""Tests for retry event classes."""

import pytest
from datetime import datetime
from resilience4py.retry.events import (
    RetryEvent,
    RetryEventType,
    RetryOnRetryEvent,
    RetryOnSuccessEvent,
    RetryOnErrorEvent,
    RetryOnIgnoredErrorEvent
)


class TestRetryEvent:
    """Test suite for base RetryEvent class."""

    def test_retry_event_initialization(self):
        """Test RetryEvent base class initialization."""
        event = RetryEvent("test-retry", RetryEventType.ON_RETRY)
        
        assert event.retry_name == "test-retry"
        assert event.event_type == RetryEventType.ON_RETRY
        assert isinstance(event.creation_time, datetime)
        
        # Creation time should be recent
        now = datetime.now()
        delta = now - event.creation_time
        assert delta.total_seconds() < 1.0

    def test_retry_event_types(self):
        """Test all retry event types."""
        assert RetryEventType.ON_RETRY
        assert RetryEventType.ON_SUCCESS
        assert RetryEventType.ON_ERROR
        assert RetryEventType.ON_IGNORED_ERROR


class TestRetryOnRetryEvent:
    """Test suite for RetryOnRetryEvent."""

    def test_on_retry_event_with_exception(self):
        """Test RetryOnRetryEvent with exception."""
        exception = ValueError("test error")
        event = RetryOnRetryEvent(
            retry_name="test-retry",
            attempt=2,
            last_result=exception,
            wait_interval=1.5
        )
        
        assert event.retry_name == "test-retry"
        assert event.event_type == RetryEventType.ON_RETRY
        assert event.attempt == 2
        assert event.last_result is exception
        assert event.wait_interval == 1.5
        assert event.is_exception_retry is True
        assert event.exception is exception
        assert event.result is None

    def test_on_retry_event_with_result(self):
        """Test RetryOnRetryEvent with result value."""
        result = {"status": "retry"}
        event = RetryOnRetryEvent(
            retry_name="test-retry",
            attempt=1,
            last_result=result,
            wait_interval=0.5
        )
        
        assert event.retry_name == "test-retry"
        assert event.event_type == RetryEventType.ON_RETRY
        assert event.attempt == 1
        assert event.last_result is result
        assert event.wait_interval == 0.5
        assert event.is_exception_retry is False
        assert event.exception is None
        assert event.result is result

    def test_on_retry_event_validation(self):
        """Test RetryOnRetryEvent parameter validation."""
        # Invalid attempt (not positive)
        with pytest.raises(ValueError, match="attempt must be positive"):
            RetryOnRetryEvent(
                retry_name="test",
                attempt=0,
                last_result=Exception(),
                wait_interval=1.0
            )
        
        with pytest.raises(ValueError, match="attempt must be positive"):
            RetryOnRetryEvent(
                retry_name="test",
                attempt=-1,
                last_result=Exception(),
                wait_interval=1.0
            )
        
        # Invalid wait_interval (negative)
        with pytest.raises(ValueError, match="wait_interval must be non-negative"):
            RetryOnRetryEvent(
                retry_name="test",
                attempt=1,
                last_result=Exception(),
                wait_interval=-0.5
            )

    def test_on_retry_event_zero_wait(self):
        """Test RetryOnRetryEvent with zero wait interval."""
        event = RetryOnRetryEvent(
            retry_name="test-retry",
            attempt=1,
            last_result=ValueError(),
            wait_interval=0.0
        )
        
        assert event.wait_interval == 0.0  # Zero wait is valid

    def test_on_retry_event_with_custom_exception(self):
        """Test RetryOnRetryEvent with custom exception types."""
        class CustomError(Exception):
            def __init__(self, code):
                self.code = code
                super().__init__(f"Error code: {code}")
        
        error = CustomError(500)
        event = RetryOnRetryEvent(
            retry_name="test-retry",
            attempt=3,
            last_result=error,
            wait_interval=2.0
        )
        
        assert event.is_exception_retry is True
        assert isinstance(event.exception, CustomError)
        assert event.exception.code == 500


class TestRetryOnSuccessEvent:
    """Test suite for RetryOnSuccessEvent."""

    def test_on_success_event_first_attempt(self):
        """Test RetryOnSuccessEvent for first attempt success."""
        event = RetryOnSuccessEvent(
            retry_name="test-retry",
            attempt=1,
            last_exception=None,
            total_duration=0.1
        )
        
        assert event.retry_name == "test-retry"
        assert event.event_type == RetryEventType.ON_SUCCESS
        assert event.attempt == 1
        assert event.last_exception is None
        assert event.total_duration == 0.1
        assert event.had_retries is False
        assert event.retry_count == 0

    def test_on_success_event_after_retries(self):
        """Test RetryOnSuccessEvent after retries."""
        exception = ValueError("previous error")
        event = RetryOnSuccessEvent(
            retry_name="test-retry",
            attempt=3,
            last_exception=exception,
            total_duration=5.5
        )
        
        assert event.retry_name == "test-retry"
        assert event.event_type == RetryEventType.ON_SUCCESS
        assert event.attempt == 3
        assert event.last_exception is exception
        assert event.total_duration == 5.5
        assert event.had_retries is True
        assert event.retry_count == 2

    def test_on_success_event_validation(self):
        """Test RetryOnSuccessEvent parameter validation."""
        # Invalid attempt (not positive)
        with pytest.raises(ValueError, match="attempt must be positive"):
            RetryOnSuccessEvent(
                retry_name="test",
                attempt=0,
                last_exception=None,
                total_duration=1.0
            )
        
        # Invalid total_duration (negative)
        with pytest.raises(ValueError, match="total_duration must be non-negative"):
            RetryOnSuccessEvent(
                retry_name="test",
                attempt=1,
                last_exception=None,
                total_duration=-1.0
            )

    def test_on_success_event_zero_duration(self):
        """Test RetryOnSuccessEvent with zero duration."""
        event = RetryOnSuccessEvent(
            retry_name="test-retry",
            attempt=1,
            last_exception=None,
            total_duration=0.0
        )
        
        assert event.total_duration == 0.0  # Zero duration is valid

    def test_on_success_event_large_retry_count(self):
        """Test RetryOnSuccessEvent with many retries."""
        event = RetryOnSuccessEvent(
            retry_name="test-retry",
            attempt=100,
            last_exception=Exception("many failures"),
            total_duration=300.0
        )
        
        assert event.had_retries is True
        assert event.retry_count == 99


class TestRetryOnErrorEvent:
    """Test suite for RetryOnErrorEvent."""

    def test_on_error_event(self):
        """Test RetryOnErrorEvent basic functionality."""
        exception = RuntimeError("final error")
        event = RetryOnErrorEvent(
            retry_name="test-retry",
            attempt=3,
            last_exception=exception,
            total_duration=10.5
        )
        
        assert event.retry_name == "test-retry"
        assert event.event_type == RetryEventType.ON_ERROR
        assert event.attempt == 3
        assert event.last_exception is exception
        assert event.total_duration == 10.5
        assert event.total_attempts == 3

    def test_on_error_event_validation(self):
        """Test RetryOnErrorEvent parameter validation."""
        # Invalid attempt (not positive)
        with pytest.raises(ValueError, match="attempt must be positive"):
            RetryOnErrorEvent(
                retry_name="test",
                attempt=0,
                last_exception=Exception(),
                total_duration=1.0
            )
        
        # Invalid total_duration (negative)
        with pytest.raises(ValueError, match="total_duration must be non-negative"):
            RetryOnErrorEvent(
                retry_name="test",
                attempt=1,
                last_exception=Exception(),
                total_duration=-1.0
            )
        
        # Invalid last_exception (not an Exception)
        with pytest.raises(TypeError, match="last_exception must be an Exception"):
            RetryOnErrorEvent(
                retry_name="test",
                attempt=1,
                last_exception="not an exception",
                total_duration=1.0
            )

    def test_on_error_event_single_attempt(self):
        """Test RetryOnErrorEvent with single attempt (no retries)."""
        event = RetryOnErrorEvent(
            retry_name="test-retry",
            attempt=1,
            last_exception=ValueError("immediate failure"),
            total_duration=0.01
        )
        
        assert event.total_attempts == 1

    def test_on_error_event_custom_exception_attributes(self):
        """Test RetryOnErrorEvent preserves custom exception attributes."""
        class DetailedException(Exception):
            def __init__(self, message, details):
                super().__init__(message)
                self.details = details
        
        exception = DetailedException("error", {"code": 500, "retry_after": 60})
        event = RetryOnErrorEvent(
            retry_name="test-retry",
            attempt=5,
            last_exception=exception,
            total_duration=15.0
        )
        
        assert isinstance(event.last_exception, DetailedException)
        assert event.last_exception.details == {"code": 500, "retry_after": 60}


class TestRetryOnIgnoredErrorEvent:
    """Test suite for RetryOnIgnoredErrorEvent."""

    def test_on_ignored_error_event(self):
        """Test RetryOnIgnoredErrorEvent basic functionality."""
        exception = KeyError("not found")
        event = RetryOnIgnoredErrorEvent(
            retry_name="test-retry",
            attempt=2,
            exception=exception
        )
        
        assert event.retry_name == "test-retry"
        assert event.event_type == RetryEventType.ON_IGNORED_ERROR
        assert event.attempt == 2
        assert event.exception is exception
        assert event.exception_type == KeyError
        assert event.exception_message == "not found"

    def test_on_ignored_error_event_validation(self):
        """Test RetryOnIgnoredErrorEvent parameter validation."""
        # Invalid attempt (not positive)
        with pytest.raises(ValueError, match="attempt must be positive"):
            RetryOnIgnoredErrorEvent(
                retry_name="test",
                attempt=0,
                exception=Exception()
            )
        
        # Invalid exception (not an Exception)
        with pytest.raises(TypeError, match="exception must be an Exception"):
            RetryOnIgnoredErrorEvent(
                retry_name="test",
                attempt=1,
                exception="not an exception"
            )

    def test_on_ignored_error_event_first_attempt(self):
        """Test RetryOnIgnoredErrorEvent on first attempt."""
        event = RetryOnIgnoredErrorEvent(
            retry_name="test-retry",
            attempt=1,
            exception=ValueError("abort immediately")
        )
        
        assert event.attempt == 1
        assert event.exception_type == ValueError

    def test_on_ignored_error_event_exception_hierarchy(self):
        """Test RetryOnIgnoredErrorEvent with exception hierarchy."""
        class BaseError(Exception):
            pass
        
        class SpecificError(BaseError):
            pass
        
        exception = SpecificError("specific problem")
        event = RetryOnIgnoredErrorEvent(
            retry_name="test-retry",
            attempt=1,
            exception=exception
        )
        
        assert event.exception_type == SpecificError
        assert isinstance(event.exception, BaseError)  # Also instance of parent

    def test_on_ignored_error_event_empty_message(self):
        """Test RetryOnIgnoredErrorEvent with empty exception message."""
        exception = Exception()  # No message
        event = RetryOnIgnoredErrorEvent(
            retry_name="test-retry",
            attempt=1,
            exception=exception
        )
        
        assert event.exception_message == ""

    def test_on_ignored_error_event_complex_message(self):
        """Test RetryOnIgnoredErrorEvent with complex exception message."""
        exception = ValueError("Multi\nline\nerror with special chars: @#$%")
        event = RetryOnIgnoredErrorEvent(
            retry_name="test-retry",
            attempt=3,
            exception=exception
        )
        
        assert event.exception_message == "Multi\nline\nerror with special chars: @#$%"


class TestEventComparison:
    """Test comparing different event types."""

    def test_event_type_uniqueness(self):
        """Test that event types are unique."""
        types = [
            RetryEventType.ON_RETRY,
            RetryEventType.ON_SUCCESS,
            RetryEventType.ON_ERROR,
            RetryEventType.ON_IGNORED_ERROR
        ]
        
        # All types should be unique
        assert len(types) == len(set(types))

    def test_event_creation_times(self):
        """Test that events have distinct creation times."""
        import time
        
        event1 = RetryOnRetryEvent("test", 1, Exception(), 1.0)
        time.sleep(0.001)  # Small delay
        event2 = RetryOnSuccessEvent("test", 1, None, 1.0)
        
        assert event2.creation_time > event1.creation_time

    def test_event_inheritance(self):
        """Test that all event classes inherit from RetryEvent."""
        events = [
            RetryOnRetryEvent("test", 1, Exception(), 1.0),
            RetryOnSuccessEvent("test", 1, None, 1.0),
            RetryOnErrorEvent("test", 1, Exception(), 1.0),
            RetryOnIgnoredErrorEvent("test", 1, Exception())
        ]
        
        for event in events:
            assert isinstance(event, RetryEvent)
            assert hasattr(event, 'retry_name')
            assert hasattr(event, 'event_type')
            assert hasattr(event, 'creation_time')