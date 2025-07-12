"""Tests for the high-level RateLimiter class."""

import asyncio
from datetime import timedelta
from unittest.mock import Mock, AsyncMock, patch

import pytest

from resilience4py.ratelimiter import (
    RateLimiter, RateLimiterRegistry, RequestNotPermitted, rate_limit
)
from resilience4py.ratelimiter.config import RateLimiterConfig
from resilience4py.ratelimiter.atomic_rate_limiter import AtomicRateLimiter


class TestRateLimiterRegistry:
    """Test cases for RateLimiterRegistry."""
    
    @pytest.fixture
    def registry(self):
        """Create a fresh registry instance."""
        return RateLimiterRegistry()
    
    def test_initialization(self, registry):
        """Test registry initialization."""
        assert isinstance(registry._default_config, RateLimiterConfig)
        assert len(registry._instances) == 0
        assert len(registry._configs) == 0
    
    @pytest.mark.asyncio
    async def test_get_or_create_new_instance(self, registry):
        """Test creating a new rate limiter instance."""
        config = RateLimiterConfig(limit_for_period=10)
        limiter = await registry.get_or_create("test", config)
        
        assert isinstance(limiter, AtomicRateLimiter)
        assert limiter.name == "test"
        assert limiter.config == config
    
    @pytest.mark.asyncio
    async def test_get_or_create_existing_instance(self, registry):
        """Test getting an existing rate limiter instance."""
        config = RateLimiterConfig(limit_for_period=10)
        limiter1 = await registry.get_or_create("test", config)
        limiter2 = await registry.get_or_create("test")
        
        # Should return the same instance
        assert limiter1 is limiter2
    
    @pytest.mark.asyncio
    async def test_get_or_create_with_default_config(self, registry):
        """Test creating instance with default config."""
        limiter = await registry.get_or_create("test")
        
        assert limiter.config == registry._default_config
    
    def test_set_default_config(self, registry):
        """Test setting default configuration."""
        new_config = RateLimiterConfig(limit_for_period=100)
        registry.set_default_config(new_config)
        
        assert registry._default_config == new_config
    
    @pytest.mark.asyncio
    async def test_remove_instance(self, registry):
        """Test removing a rate limiter instance."""
        config = RateLimiterConfig(limit_for_period=10)
        await registry.get_or_create("test", config)
        
        registry.remove("test")
        
        # Should be removed from both dicts
        assert "test" not in registry._instances
        assert "test" not in registry._configs
        
        # Removing non-existent should not raise
        registry.remove("non-existent")
    
    @pytest.mark.asyncio
    async def test_concurrent_access(self, registry):
        """Test concurrent access to registry."""
        config = RateLimiterConfig(limit_for_period=10)
        
        async def get_limiter():
            return await registry.get_or_create("test", config)
        
        # Get multiple instances concurrently
        limiters = await asyncio.gather(*[get_limiter() for _ in range(10)])
        
        # All should be the same instance
        first_limiter = limiters[0]
        assert all(limiter is first_limiter for limiter in limiters)


class TestRateLimiter:
    """Test cases for the high-level RateLimiter class."""
    
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
        return RateLimiter("test-limiter", config)
    
    def test_initialization(self, rate_limiter, config):
        """Test rate limiter initialization."""
        assert rate_limiter.name == "test-limiter"
        assert rate_limiter.config == config
        assert rate_limiter._atomic_limiter is None
    
    @pytest.mark.asyncio
    async def test_get_limiter(self, rate_limiter):
        """Test getting the underlying atomic limiter."""
        limiter = await rate_limiter._get_limiter()
        assert isinstance(limiter, AtomicRateLimiter)
        assert limiter.name == "test-limiter"
        
        # Should return same instance on subsequent calls
        limiter2 = await rate_limiter._get_limiter()
        assert limiter is limiter2
    
    @pytest.mark.asyncio
    async def test_decorate_async_function(self, rate_limiter):
        """Test decorating an async function."""
        call_count = 0
        
        @rate_limiter
        async def test_func(value):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return value * 2
        
        # Should succeed for configured limit
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
        
        # Should succeed for configured limit
        result = test_func(5)
        assert result == 10
        assert call_count == 1
        
        result = test_func(10)
        assert result == 20
        assert call_count == 2
    
    def test_of_factory_method(self, config):
        """Test the factory method."""
        limiter = RateLimiter.of("factory-test", config)
        
        assert isinstance(limiter, RateLimiter)
        assert limiter.name == "factory-test"
        assert limiter.config == config
    
    def test_set_default_config(self):
        """Test setting default configuration globally."""
        new_config = RateLimiterConfig(limit_for_period=100)
        
        with patch('resilience4py.ratelimiter.rate_limiter._registry') as mock_registry:
            RateLimiter.set_default_config(new_config)
            mock_registry.set_default_config.assert_called_once_with(new_config)
    
    @pytest.mark.asyncio
    async def test_acquire_permission(self, rate_limiter):
        """Test acquiring permission directly."""
        # First two should succeed
        assert await rate_limiter.acquire_permission() is True
        assert await rate_limiter.acquire_permission() is True
        
        # Third should fail (with mocked short timeout)
        with patch.object(rate_limiter, '_get_limiter') as mock_get:
            mock_limiter = AsyncMock()
            mock_limiter._reserve_permission.return_value = -1000  # Negative = timeout
            mock_get.return_value = mock_limiter
            
            assert await rate_limiter.acquire_permission() is False
    
    @pytest.mark.asyncio
    async def test_acquire_permission_with_wait(self, rate_limiter):
        """Test acquiring permission with wait."""
        # Use up permissions
        assert await rate_limiter.acquire_permission() is True
        assert await rate_limiter.acquire_permission() is True
        
        # Third should wait (mock short wait time)
        with patch('asyncio.sleep') as mock_sleep:
            with patch.object(rate_limiter, '_get_limiter') as mock_get:
                mock_limiter = AsyncMock()
                mock_limiter._reserve_permission.return_value = 100_000_000  # 100ms in nanos
                mock_get.return_value = mock_limiter
                
                result = await rate_limiter.acquire_permission()
                assert result is True
                mock_sleep.assert_called_once_with(0.1)
    
    @pytest.mark.asyncio
    async def test_get_metrics(self, rate_limiter):
        """Test getting metrics."""
        metrics = await rate_limiter.get_metrics()
        
        assert metrics["name"] == "test-limiter"
        assert metrics["available_permissions"] == 2
        assert metrics["limit_for_period"] == 2
        assert metrics["current_cycle"] == 0
    
    @pytest.mark.asyncio
    async def test_reset(self, rate_limiter):
        """Test resetting the rate limiter."""
        # Use some permissions
        await rate_limiter.acquire_permission()
        
        # Reset
        await rate_limiter.reset()
        
        # Check metrics to verify reset
        metrics = await rate_limiter.get_metrics()
        assert metrics["available_permissions"] == 2
    
    def test_add_event_listener(self, rate_limiter):
        """Test adding event listener (placeholder implementation)."""
        from resilience4py.ratelimiter.events import RateLimiterOnSuccessEvent
        
        def listener(event):
            pass
        
        # Should not raise
        rate_limiter.add_event_listener(RateLimiterOnSuccessEvent, listener)
    
    @pytest.mark.asyncio
    async def test_shared_instances(self):
        """Test that rate limiters with same name share state."""
        config = RateLimiterConfig(limit_for_period=2)
        
        limiter1 = RateLimiter("shared", config)
        limiter2 = RateLimiter("shared")  # Same name, no config
        
        # Use permissions through limiter1
        assert await limiter1.acquire_permission() is True
        assert await limiter1.acquire_permission() is True
        
        # limiter2 should see the same state
        metrics = await limiter2.get_metrics()
        assert metrics["available_permissions"] == 0


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_rate_limit_decorator(self):
        """Test the rate_limit convenience decorator."""
        limiter = rate_limit(10, 2.0)
        
        assert isinstance(limiter, RateLimiter)
        assert limiter.config.limit_for_period == 10
        assert limiter.config.limit_refresh_period == timedelta(seconds=2.0)
        assert limiter.name.startswith("rate-limit-10-2.0")
    
    def test_rate_limit_sync_function(self):
        """Test rate_limit decorator on sync function."""
        call_count = 0
        
        @rate_limit(2, 1.0)
        def sync_func(value):
            nonlocal call_count
            call_count += 1
            return value * 2
        
        # Should allow configured calls
        assert sync_func(5) == 10
        assert sync_func(10) == 20
        assert call_count == 2


# Import time for the convenience function tests
import time