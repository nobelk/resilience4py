"""Tests for CircuitBreakerConfig."""

import pytest
from datetime import timedelta

from resilience4py.circuitbreaker.config import CircuitBreakerConfig, SlidingWindowType


class TestCircuitBreakerConfig:
    """Test CircuitBreakerConfig validation and behavior."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = CircuitBreakerConfig()
        
        assert config.failure_rate_threshold == 50.0
        assert config.slow_call_rate_threshold == 100.0
        assert config.slow_call_duration_threshold == timedelta(seconds=60)
        assert config.permitted_calls_in_half_open == 10
        assert config.sliding_window_size == 100
        assert config.sliding_window_type == SlidingWindowType.COUNT_BASED
        assert config.minimum_number_of_calls == 100
        assert config.wait_duration_in_open_state == timedelta(seconds=60)
        assert config.max_wait_duration_in_half_open == timedelta(seconds=0)
        assert config.automatic_transition_from_open_to_half_open is True
        assert config.record_exceptions == []
        assert config.ignore_exceptions == []
        assert config.record_failure_predicate is None
        assert config.ignore_failure_predicate is None
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = CircuitBreakerConfig(
            failure_rate_threshold=75.0,
            slow_call_rate_threshold=50.0,
            slow_call_duration_threshold=timedelta(milliseconds=500),
            permitted_calls_in_half_open=5,
            sliding_window_size=50,
            sliding_window_type=SlidingWindowType.TIME_BASED,
            minimum_number_of_calls=10,
            wait_duration_in_open_state=timedelta(seconds=30),
            max_wait_duration_in_half_open=timedelta(seconds=120),
            automatic_transition_from_open_to_half_open=False
        )
        
        assert config.failure_rate_threshold == 75.0
        assert config.slow_call_rate_threshold == 50.0
        assert config.slow_call_duration_threshold == timedelta(milliseconds=500)
        assert config.permitted_calls_in_half_open == 5
        assert config.sliding_window_size == 50
        assert config.sliding_window_type == SlidingWindowType.TIME_BASED
        assert config.minimum_number_of_calls == 10
        assert config.wait_duration_in_open_state == timedelta(seconds=30)
        assert config.max_wait_duration_in_half_open == timedelta(seconds=120)
        assert config.automatic_transition_from_open_to_half_open is False
    
    def test_failure_rate_threshold_validation(self):
        """Test failure rate threshold validation."""
        # Valid threshold
        config = CircuitBreakerConfig(failure_rate_threshold=1.0)
        assert config.failure_rate_threshold == 1.0
        
        config = CircuitBreakerConfig(failure_rate_threshold=100.0)
        assert config.failure_rate_threshold == 100.0
        
        # Invalid thresholds
        with pytest.raises(ValueError, match="failure_rate_threshold must be between 0 and 100"):
            CircuitBreakerConfig(failure_rate_threshold=0.0)
        
        with pytest.raises(ValueError, match="failure_rate_threshold must be between 0 and 100"):
            CircuitBreakerConfig(failure_rate_threshold=-1.0)
        
        with pytest.raises(ValueError, match="failure_rate_threshold must be between 0 and 100"):
            CircuitBreakerConfig(failure_rate_threshold=101.0)
    
    def test_slow_call_rate_threshold_validation(self):
        """Test slow call rate threshold validation."""
        # Valid threshold
        config = CircuitBreakerConfig(slow_call_rate_threshold=1.0)
        assert config.slow_call_rate_threshold == 1.0
        
        config = CircuitBreakerConfig(slow_call_rate_threshold=100.0)
        assert config.slow_call_rate_threshold == 100.0
        
        # Invalid thresholds
        with pytest.raises(ValueError, match="slow_call_rate_threshold must be between 0 and 100"):
            CircuitBreakerConfig(slow_call_rate_threshold=0.0)
        
        with pytest.raises(ValueError, match="slow_call_rate_threshold must be between 0 and 100"):
            CircuitBreakerConfig(slow_call_rate_threshold=-1.0)
        
        with pytest.raises(ValueError, match="slow_call_rate_threshold must be between 0 and 100"):
            CircuitBreakerConfig(slow_call_rate_threshold=101.0)
    
    def test_sliding_window_size_validation(self):
        """Test sliding window size validation."""
        # Valid size
        config = CircuitBreakerConfig(sliding_window_size=1)
        assert config.sliding_window_size == 1
        
        # Invalid size
        with pytest.raises(ValueError, match="sliding_window_size must be greater than 0"):
            CircuitBreakerConfig(sliding_window_size=0)
        
        with pytest.raises(ValueError, match="sliding_window_size must be greater than 0"):
            CircuitBreakerConfig(sliding_window_size=-1)
    
    def test_minimum_number_of_calls_validation(self):
        """Test minimum number of calls validation."""
        # Valid value
        config = CircuitBreakerConfig(minimum_number_of_calls=1)
        assert config.minimum_number_of_calls == 1
        
        # Invalid value
        with pytest.raises(ValueError, match="minimum_number_of_calls must be greater than 0"):
            CircuitBreakerConfig(minimum_number_of_calls=0)
        
        with pytest.raises(ValueError, match="minimum_number_of_calls must be greater than 0"):
            CircuitBreakerConfig(minimum_number_of_calls=-1)
    
    def test_permitted_calls_in_half_open_validation(self):
        """Test permitted calls in half open validation."""
        # Valid value
        config = CircuitBreakerConfig(permitted_calls_in_half_open=1)
        assert config.permitted_calls_in_half_open == 1
        
        # Invalid value
        with pytest.raises(ValueError, match="permitted_calls_in_half_open must be greater than 0"):
            CircuitBreakerConfig(permitted_calls_in_half_open=0)
        
        with pytest.raises(ValueError, match="permitted_calls_in_half_open must be greater than 0"):
            CircuitBreakerConfig(permitted_calls_in_half_open=-1)
    
    def test_wait_duration_in_open_state_validation(self):
        """Test wait duration in open state validation."""
        # Valid duration
        config = CircuitBreakerConfig(wait_duration_in_open_state=timedelta(milliseconds=1))
        assert config.wait_duration_in_open_state == timedelta(milliseconds=1)
        
        # Invalid duration
        with pytest.raises(ValueError, match="wait_duration_in_open_state must be positive"):
            CircuitBreakerConfig(wait_duration_in_open_state=timedelta(seconds=0))
        
        with pytest.raises(ValueError, match="wait_duration_in_open_state must be positive"):
            CircuitBreakerConfig(wait_duration_in_open_state=timedelta(seconds=-1))
    
    def test_max_wait_duration_in_half_open_validation(self):
        """Test max wait duration in half open validation."""
        # Valid duration (0 means no limit)
        config = CircuitBreakerConfig(max_wait_duration_in_half_open=timedelta(seconds=0))
        assert config.max_wait_duration_in_half_open == timedelta(seconds=0)
        
        config = CircuitBreakerConfig(max_wait_duration_in_half_open=timedelta(seconds=10))
        assert config.max_wait_duration_in_half_open == timedelta(seconds=10)
        
        # Invalid duration
        with pytest.raises(ValueError, match="max_wait_duration_in_half_open must be non-negative"):
            CircuitBreakerConfig(max_wait_duration_in_half_open=timedelta(seconds=-1))
    
    def test_slow_call_duration_threshold_validation(self):
        """Test slow call duration threshold validation."""
        # Valid duration
        config = CircuitBreakerConfig(slow_call_duration_threshold=timedelta(milliseconds=1))
        assert config.slow_call_duration_threshold == timedelta(milliseconds=1)
        
        # Invalid duration
        with pytest.raises(ValueError, match="slow_call_duration_threshold must be positive"):
            CircuitBreakerConfig(slow_call_duration_threshold=timedelta(seconds=0))
        
        with pytest.raises(ValueError, match="slow_call_duration_threshold must be positive"):
            CircuitBreakerConfig(slow_call_duration_threshold=timedelta(seconds=-1))
    
    def test_should_record_exception_with_record_list(self):
        """Test exception recording with record_exceptions list."""
        config = CircuitBreakerConfig(
            record_exceptions=[ValueError, RuntimeError]
        )
        
        # Should record listed exceptions
        assert config.should_record_exception(ValueError("test")) is True
        assert config.should_record_exception(RuntimeError("test")) is True
        
        # Should not record unlisted exceptions
        assert config.should_record_exception(TypeError("test")) is False
        assert config.should_record_exception(Exception("test")) is False
    
    def test_should_record_exception_with_ignore_list(self):
        """Test exception recording with ignore_exceptions list."""
        config = CircuitBreakerConfig(
            ignore_exceptions=[ValueError, RuntimeError]
        )
        
        # Should ignore listed exceptions
        assert config.should_record_exception(ValueError("test")) is False
        assert config.should_record_exception(RuntimeError("test")) is False
        
        # Should record unlisted exceptions
        assert config.should_record_exception(TypeError("test")) is True
        assert config.should_record_exception(Exception("test")) is True
    
    def test_should_record_exception_with_both_lists(self):
        """Test exception recording with both record and ignore lists."""
        config = CircuitBreakerConfig(
            record_exceptions=[Exception],  # Record all exceptions
            ignore_exceptions=[ValueError]  # But ignore ValueError
        )
        
        # Ignore list takes precedence
        assert config.should_record_exception(ValueError("test")) is False
        
        # Other exceptions in record list should be recorded
        assert config.should_record_exception(RuntimeError("test")) is True
        assert config.should_record_exception(TypeError("test")) is True
    
    def test_should_record_exception_with_predicates(self):
        """Test exception recording with predicates."""
        def record_predicate(exc):
            return "important" in str(exc)
        
        def ignore_predicate(exc):
            return "ignore" in str(exc)
        
        config = CircuitBreakerConfig(
            record_failure_predicate=record_predicate,
            ignore_failure_predicate=ignore_predicate
        )
        
        # Ignore predicate takes precedence
        assert config.should_record_exception(Exception("important but ignore")) is False
        
        # Record based on predicate
        assert config.should_record_exception(Exception("important error")) is True
        assert config.should_record_exception(Exception("normal error")) is False
    
    def test_should_record_exception_inheritance(self):
        """Test exception recording with inheritance."""
        class CustomError(ValueError):
            pass
        
        config = CircuitBreakerConfig(
            record_exceptions=[ValueError]
        )
        
        # Should record subclasses
        assert config.should_record_exception(CustomError("test")) is True
        assert config.should_record_exception(ValueError("test")) is True
        
        # Should not record unrelated exceptions
        assert config.should_record_exception(TypeError("test")) is False
    
    def test_should_record_exception_default_behavior(self):
        """Test default exception recording behavior."""
        config = CircuitBreakerConfig()
        
        # By default, all exceptions should be recorded
        assert config.should_record_exception(Exception("test")) is True
        assert config.should_record_exception(ValueError("test")) is True
        assert config.should_record_exception(RuntimeError("test")) is True
    
    def test_config_immutability(self):
        """Test that config is immutable (frozen dataclass)."""
        config = CircuitBreakerConfig()
        
        with pytest.raises(AttributeError):
            config.failure_rate_threshold = 75.0
        
        with pytest.raises(AttributeError):
            config.sliding_window_size = 200