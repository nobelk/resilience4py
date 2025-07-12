"""Tests for bulkhead configuration classes."""

import pytest
from datetime import timedelta

from resilience4py.bulkhead.config import BulkheadConfig, ThreadPoolBulkheadConfig


class TestBulkheadConfig:
    """Test cases for BulkheadConfig."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = BulkheadConfig()
        
        assert config.max_concurrent_calls == 25
        assert config.max_wait_duration == timedelta(seconds=0)
        assert config.tags == {}
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = BulkheadConfig(
            max_concurrent_calls=10,
            max_wait_duration=timedelta(seconds=5),
            tags={"env": "prod", "service": "api"}
        )
        
        assert config.max_concurrent_calls == 10
        assert config.max_wait_duration == timedelta(seconds=5)
        assert config.tags == {"env": "prod", "service": "api"}
    
    def test_immutability(self):
        """Test that configuration is immutable."""
        config = BulkheadConfig()
        
        with pytest.raises(AttributeError):
            config.max_concurrent_calls = 50
    
    def test_validation_positive_concurrent_calls(self):
        """Test validation of max_concurrent_calls."""
        # Valid values
        BulkheadConfig(max_concurrent_calls=1)
        BulkheadConfig(max_concurrent_calls=100)
        
        # Invalid values
        with pytest.raises(ValueError, match="max_concurrent_calls must be positive"):
            BulkheadConfig(max_concurrent_calls=0)
        
        with pytest.raises(ValueError, match="max_concurrent_calls must be positive"):
            BulkheadConfig(max_concurrent_calls=-1)
    
    def test_validation_wait_duration(self):
        """Test validation of max_wait_duration."""
        # Valid values
        BulkheadConfig(max_wait_duration=timedelta(seconds=0))
        BulkheadConfig(max_wait_duration=timedelta(seconds=10))
        BulkheadConfig(max_wait_duration=timedelta(milliseconds=500))
        
        # Invalid values
        with pytest.raises(ValueError, match="max_wait_duration cannot be negative"):
            BulkheadConfig(max_wait_duration=timedelta(seconds=-1))
    
    def test_timedelta_precision(self):
        """Test that timedelta preserves precision."""
        config = BulkheadConfig(max_wait_duration=timedelta(milliseconds=100))
        assert config.max_wait_duration.total_seconds() == 0.1


class TestThreadPoolBulkheadConfig:
    """Test cases for ThreadPoolBulkheadConfig."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = ThreadPoolBulkheadConfig()
        
        assert config.max_thread_pool_size == 4
        assert config.core_thread_pool_size == 2
        assert config.queue_capacity == 100
        assert config.keep_alive_duration == timedelta(milliseconds=20)
        assert config.tags == {}
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = ThreadPoolBulkheadConfig(
            max_thread_pool_size=10,
            core_thread_pool_size=5,
            queue_capacity=50,
            keep_alive_duration=timedelta(seconds=1),
            tags={"pool": "main"}
        )
        
        assert config.max_thread_pool_size == 10
        assert config.core_thread_pool_size == 5
        assert config.queue_capacity == 50
        assert config.keep_alive_duration == timedelta(seconds=1)
        assert config.tags == {"pool": "main"}
    
    def test_immutability(self):
        """Test that configuration is immutable."""
        config = ThreadPoolBulkheadConfig()
        
        with pytest.raises(AttributeError):
            config.max_thread_pool_size = 10
        
        with pytest.raises(AttributeError):
            config.queue_capacity = 200
    
    def test_validation_max_thread_pool_size(self):
        """Test validation of max_thread_pool_size."""
        # Valid values
        ThreadPoolBulkheadConfig(max_thread_pool_size=1, core_thread_pool_size=1)
        ThreadPoolBulkheadConfig(max_thread_pool_size=100, core_thread_pool_size=50)
        
        # Invalid values
        with pytest.raises(ValueError, match="max_thread_pool_size must be positive"):
            ThreadPoolBulkheadConfig(max_thread_pool_size=0)
        
        with pytest.raises(ValueError, match="max_thread_pool_size must be positive"):
            ThreadPoolBulkheadConfig(max_thread_pool_size=-1)
    
    def test_validation_core_thread_pool_size(self):
        """Test validation of core_thread_pool_size."""
        # Valid values
        ThreadPoolBulkheadConfig(core_thread_pool_size=1, max_thread_pool_size=10)
        
        # Invalid values
        with pytest.raises(ValueError, match="core_thread_pool_size must be positive"):
            ThreadPoolBulkheadConfig(core_thread_pool_size=0)
        
        with pytest.raises(ValueError, match="core_thread_pool_size must be positive"):
            ThreadPoolBulkheadConfig(core_thread_pool_size=-1)
    
    def test_validation_core_vs_max_pool_size(self):
        """Test validation of core vs max thread pool size."""
        # Valid: core <= max
        ThreadPoolBulkheadConfig(core_thread_pool_size=5, max_thread_pool_size=5)
        ThreadPoolBulkheadConfig(core_thread_pool_size=2, max_thread_pool_size=10)
        
        # Invalid: core > max
        with pytest.raises(ValueError, match="core_thread_pool_size cannot exceed max_thread_pool_size"):
            ThreadPoolBulkheadConfig(core_thread_pool_size=10, max_thread_pool_size=5)
    
    def test_validation_queue_capacity(self):
        """Test validation of queue_capacity."""
        # Valid values
        ThreadPoolBulkheadConfig(queue_capacity=0)
        ThreadPoolBulkheadConfig(queue_capacity=1000)
        
        # Invalid values
        with pytest.raises(ValueError, match="queue_capacity cannot be negative"):
            ThreadPoolBulkheadConfig(queue_capacity=-1)
    
    def test_validation_keep_alive_duration(self):
        """Test validation of keep_alive_duration."""
        # Valid values
        ThreadPoolBulkheadConfig(keep_alive_duration=timedelta(seconds=0))
        ThreadPoolBulkheadConfig(keep_alive_duration=timedelta(minutes=1))
        
        # Invalid values
        with pytest.raises(ValueError, match="keep_alive_duration cannot be negative"):
            ThreadPoolBulkheadConfig(keep_alive_duration=timedelta(seconds=-1))
    
    def test_edge_cases(self):
        """Test edge case configurations."""
        # Minimum viable configuration
        config = ThreadPoolBulkheadConfig(
            max_thread_pool_size=1,
            core_thread_pool_size=1,
            queue_capacity=0,
            keep_alive_duration=timedelta(seconds=0)
        )
        
        assert config.max_thread_pool_size == 1
        assert config.core_thread_pool_size == 1
        assert config.queue_capacity == 0
        assert config.keep_alive_duration == timedelta(seconds=0)