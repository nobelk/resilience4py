"""Tests for RateLimiterConfig."""

import pytest
from datetime import timedelta

from resilience4py.ratelimiter.config import RateLimiterConfig


class TestRateLimiterConfig:
    """Test cases for RateLimiterConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = RateLimiterConfig()
        
        assert config.limit_for_period == 50
        assert config.limit_refresh_period == timedelta(microseconds=500)
        assert config.timeout_duration == timedelta(seconds=5)
        assert config.tags == {}
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = RateLimiterConfig(
            limit_for_period=100,
            limit_refresh_period=timedelta(seconds=1),
            timeout_duration=timedelta(seconds=10),
            tags={"service": "api", "env": "prod"}
        )
        
        assert config.limit_for_period == 100
        assert config.limit_refresh_period == timedelta(seconds=1)
        assert config.timeout_duration == timedelta(seconds=10)
        assert config.tags == {"service": "api", "env": "prod"}
    
    def test_validation_limit_for_period(self):
        """Test validation of limit_for_period."""
        # Valid values
        RateLimiterConfig(limit_for_period=1)
        RateLimiterConfig(limit_for_period=1000000)
        
        # Invalid values
        with pytest.raises(AssertionError, match="limit_for_period must be greater than 0"):
            RateLimiterConfig(limit_for_period=0)
        
        with pytest.raises(AssertionError, match="limit_for_period must be greater than 0"):
            RateLimiterConfig(limit_for_period=-1)
    
    def test_validation_limit_refresh_period(self):
        """Test validation of limit_refresh_period."""
        # Valid values
        RateLimiterConfig(limit_refresh_period=timedelta(microseconds=1))
        RateLimiterConfig(limit_refresh_period=timedelta(seconds=60))
        
        # Invalid values
        with pytest.raises(AssertionError, match="limit_refresh_period must be greater than 0"):
            RateLimiterConfig(limit_refresh_period=timedelta(seconds=0))
        
        with pytest.raises(AssertionError, match="limit_refresh_period must be greater than 0"):
            RateLimiterConfig(limit_refresh_period=timedelta(seconds=-1))
    
    def test_validation_timeout_duration(self):
        """Test validation of timeout_duration."""
        # Valid values
        RateLimiterConfig(timeout_duration=timedelta(seconds=0))
        RateLimiterConfig(timeout_duration=timedelta(seconds=60))
        
        # Invalid values
        with pytest.raises(AssertionError, match="timeout_duration must be non-negative"):
            RateLimiterConfig(timeout_duration=timedelta(seconds=-1))
    
    def test_config_immutability(self):
        """Test that configuration is immutable."""
        config = RateLimiterConfig(limit_for_period=50)
        
        # Try to modify attributes
        with pytest.raises(AttributeError):
            config.limit_for_period = 100
        
        with pytest.raises(AttributeError):
            config.limit_refresh_period = timedelta(seconds=2)
        
        with pytest.raises(AttributeError):
            config.timeout_duration = timedelta(seconds=10)
    
    def test_microsecond_precision(self):
        """Test that microsecond precision is preserved."""
        config = RateLimiterConfig(
            limit_refresh_period=timedelta(microseconds=123456)
        )
        
        assert config.limit_refresh_period.total_seconds() == 0.123456
        assert config.limit_refresh_period.microseconds == 123456
    
    def test_nanosecond_conversion(self):
        """Test conversion to nanoseconds for precision."""
        config = RateLimiterConfig(
            limit_refresh_period=timedelta(microseconds=1),
            timeout_duration=timedelta(milliseconds=1)
        )
        
        # 1 microsecond = 1000 nanoseconds
        refresh_nanos = int(config.limit_refresh_period.total_seconds() * 1_000_000_000)
        assert refresh_nanos == 1000
        
        # 1 millisecond = 1,000,000 nanoseconds
        timeout_nanos = int(config.timeout_duration.total_seconds() * 1_000_000_000)
        assert timeout_nanos == 1_000_000
    
    def test_validate_method(self):
        """Test the validate method directly."""
        config = RateLimiterConfig()
        
        # Should not raise
        config.validate()
        
        # Test with invalid config using object.__setattr__ to bypass frozen
        invalid_config = RateLimiterConfig()
        object.__setattr__(invalid_config, 'limit_for_period', 0)
        
        with pytest.raises(AssertionError):
            invalid_config.validate()