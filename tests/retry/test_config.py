"""Tests for RetryConfig validation and behavior."""

import pytest
from datetime import timedelta
from resilience4py.retry.config import RetryConfig


class TestRetryConfig:
    """Test suite for RetryConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RetryConfig()
        
        assert config.max_attempts == 3
        assert config.wait_duration == timedelta(milliseconds=500)
        assert config.interval_function is None
        assert config.retry_on_exception(Exception("test")) is True
        assert config.retry_on_result is None
        assert config.fail_after_max_attempts is False
        assert config.retry_exceptions is None
        assert config.abort_exceptions is None
        assert config.tags == {}

    def test_custom_config(self):
        """Test custom configuration values."""
        def custom_retry_on_exception(e):
            return isinstance(e, ValueError)
        
        def custom_retry_on_result(result):
            return result == "retry"
        
        config = RetryConfig(
            max_attempts=5,
            wait_duration=timedelta(seconds=2),
            retry_on_exception=custom_retry_on_exception,
            retry_on_result=custom_retry_on_result,
            fail_after_max_attempts=True,
            retry_exceptions=[ValueError, TypeError],
            abort_exceptions=[KeyError],
            tags={"env": "test"}
        )
        
        assert config.max_attempts == 5
        assert config.wait_duration == timedelta(seconds=2)
        assert config.retry_on_exception is custom_retry_on_exception
        assert config.retry_on_result is custom_retry_on_result
        assert config.fail_after_max_attempts is True
        assert config.retry_exceptions == [ValueError, TypeError]
        assert config.abort_exceptions == [KeyError]
        assert config.tags == {"env": "test"}

    def test_validate_max_attempts(self):
        """Test validation of max_attempts."""
        # Valid max_attempts
        config = RetryConfig(max_attempts=1)
        config.validate()  # Should not raise
        
        # Invalid max_attempts
        with pytest.raises(ValueError, match="max_attempts must be greater than 0"):
            config = RetryConfig(max_attempts=0)
            config.validate()
        
        with pytest.raises(ValueError, match="max_attempts must be greater than 0"):
            config = RetryConfig(max_attempts=-1)
            config.validate()

    def test_validate_wait_duration(self):
        """Test validation of wait_duration."""
        # Valid wait_duration
        config = RetryConfig(wait_duration=timedelta(seconds=0))
        config.validate()  # Should not raise
        
        config = RetryConfig(wait_duration=timedelta(seconds=10))
        config.validate()  # Should not raise
        
        # Invalid wait_duration
        with pytest.raises(ValueError, match="wait_duration must be non-negative"):
            config = RetryConfig(wait_duration=timedelta(seconds=-1))
            config.validate()

    def test_validate_overlapping_exceptions(self):
        """Test validation catches overlapping exception types."""
        # No overlap - should be valid
        config = RetryConfig(
            retry_exceptions=[ValueError, TypeError],
            abort_exceptions=[KeyError, AttributeError]
        )
        config.validate()  # Should not raise
        
        # Overlap - should be invalid
        with pytest.raises(ValueError, match="Exception types cannot be in both"):
            config = RetryConfig(
                retry_exceptions=[ValueError, TypeError],
                abort_exceptions=[KeyError, ValueError]
            )
            config.validate()

    def test_should_retry_exception_default(self):
        """Test default exception retry behavior."""
        config = RetryConfig()
        
        # All exceptions should be retried by default
        assert config.should_retry_exception(ValueError("test")) is True
        assert config.should_retry_exception(TypeError("test")) is True
        assert config.should_retry_exception(Exception("test")) is True

    def test_should_retry_exception_with_abort_exceptions(self):
        """Test exception retry behavior with abort_exceptions."""
        config = RetryConfig(
            abort_exceptions=[ValueError, KeyError]
        )
        
        # Abort exceptions should not be retried
        assert config.should_retry_exception(ValueError("test")) is False
        assert config.should_retry_exception(KeyError("test")) is False
        
        # Other exceptions should be retried
        assert config.should_retry_exception(TypeError("test")) is True
        assert config.should_retry_exception(Exception("test")) is True

    def test_should_retry_exception_with_retry_exceptions(self):
        """Test exception retry behavior with retry_exceptions."""
        config = RetryConfig(
            retry_exceptions=[ValueError, TypeError]
        )
        
        # Only specified exceptions should be retried
        assert config.should_retry_exception(ValueError("test")) is True
        assert config.should_retry_exception(TypeError("test")) is True
        
        # Other exceptions should not be retried
        assert config.should_retry_exception(KeyError("test")) is False
        assert config.should_retry_exception(Exception("test")) is False

    def test_should_retry_exception_with_custom_predicate(self):
        """Test exception retry behavior with custom predicate."""
        def custom_predicate(e):
            return "retry" in str(e)
        
        config = RetryConfig(
            retry_on_exception=custom_predicate
        )
        
        # Exceptions with "retry" in message should be retried
        assert config.should_retry_exception(ValueError("should retry")) is True
        assert config.should_retry_exception(TypeError("retry this")) is True
        
        # Exceptions without "retry" should not be retried
        assert config.should_retry_exception(ValueError("should not")) is False
        assert config.should_retry_exception(Exception("nope")) is False

    def test_should_retry_exception_combined(self):
        """Test exception retry behavior with combined configuration."""
        def custom_predicate(e):
            return "retry" in str(e)
        
        config = RetryConfig(
            retry_exceptions=[ValueError, TypeError],
            abort_exceptions=[RuntimeError],
            retry_on_exception=custom_predicate
        )
        
        # Abort exceptions should never be retried
        assert config.should_retry_exception(RuntimeError("retry")) is False
        
        # Retry exceptions with matching predicate should be retried
        assert config.should_retry_exception(ValueError("retry")) is True
        assert config.should_retry_exception(TypeError("retry")) is True
        
        # Retry exceptions without matching predicate should not be retried
        assert config.should_retry_exception(ValueError("nope")) is False
        
        # Non-retry exceptions should not be retried
        assert config.should_retry_exception(KeyError("retry")) is False

    def test_should_retry_exception_inheritance(self):
        """Test exception retry behavior with inheritance."""
        class CustomError(ValueError):
            pass
        
        config = RetryConfig(
            retry_exceptions=[ValueError]
        )
        
        # Subclasses should also be retried
        assert config.should_retry_exception(CustomError("test")) is True
        assert config.should_retry_exception(ValueError("test")) is True

    def test_get_wait_duration_with_fixed_duration(self):
        """Test get_wait_duration with fixed wait_duration."""
        config = RetryConfig(wait_duration=timedelta(seconds=2))
        
        # Should return the same duration for any attempt
        assert config.get_wait_duration(1) == 2.0
        assert config.get_wait_duration(2) == 2.0
        assert config.get_wait_duration(10) == 2.0

    def test_get_wait_duration_with_interval_function(self):
        """Test get_wait_duration with interval_function."""
        def custom_interval(attempt):
            return attempt * 0.5
        
        config = RetryConfig(
            wait_duration=timedelta(seconds=2),  # Should be ignored
            interval_function=custom_interval
        )
        
        # Should use the interval function
        assert config.get_wait_duration(1) == 0.5
        assert config.get_wait_duration(2) == 1.0
        assert config.get_wait_duration(3) == 1.5

    def test_config_immutability(self):
        """Test that RetryConfig is immutable (frozen dataclass)."""
        config = RetryConfig(max_attempts=3)
        
        # Should not be able to modify attributes
        with pytest.raises(AttributeError):
            config.max_attempts = 5
        
        with pytest.raises(AttributeError):
            config.wait_duration = timedelta(seconds=10)

    def test_config_with_timedelta_variations(self):
        """Test configuration with various timedelta values."""
        # Milliseconds
        config = RetryConfig(wait_duration=timedelta(milliseconds=100))
        assert config.get_wait_duration(1) == 0.1
        
        # Seconds
        config = RetryConfig(wait_duration=timedelta(seconds=5))
        assert config.get_wait_duration(1) == 5.0
        
        # Minutes
        config = RetryConfig(wait_duration=timedelta(minutes=1))
        assert config.get_wait_duration(1) == 60.0
        
        # Combined
        config = RetryConfig(wait_duration=timedelta(seconds=1, milliseconds=500))
        assert config.get_wait_duration(1) == 1.5