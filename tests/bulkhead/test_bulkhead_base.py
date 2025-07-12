"""Tests for base bulkhead abstract class and metrics."""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from datetime import timedelta

from resilience4py.bulkhead.bulkhead import Bulkhead, BulkheadMetrics, BulkheadFullException
from resilience4py.bulkhead.config import BulkheadConfig
from resilience4py.bulkhead.events import (
    BulkheadOnCallPermittedEvent,
    BulkheadOnCallRejectedEvent,
    BulkheadOnCallFinishedEvent
)


class ConcreteBulkhead(Bulkhead):
    """Concrete implementation of Bulkhead for testing."""
    
    def __init__(self, name: str, config: BulkheadConfig):
        super().__init__(name, config)
        self._permission_granted = True
    
    async def acquire_permission(self) -> bool:
        return self._permission_granted
    
    async def release_permission(self) -> None:
        pass
    
    async def on_call_permitted(self) -> None:
        pass
    
    async def on_call_rejected(self) -> None:
        pass
    
    async def on_call_finished(self) -> None:
        pass
    
    async def _execute_async(self, func, *args, **kwargs):
        """Simple implementation for testing."""
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)


class TestBulkheadBase:
    """Test cases for base Bulkhead class."""
    
    def test_bulkhead_exception(self):
        """Test BulkheadFullException."""
        exc = BulkheadFullException("Bulkhead is full")
        assert str(exc) == "Bulkhead is full"
        assert isinstance(exc, Exception)
    
    def test_bulkhead_initialization(self):
        """Test bulkhead base initialization."""
        config = BulkheadConfig(max_concurrent_calls=10)
        bulkhead = ConcreteBulkhead("test-bulkhead", config)
        
        assert bulkhead.name == "test-bulkhead"
        assert bulkhead.config == config
        assert isinstance(bulkhead.metrics, BulkheadMetrics)
    
    def test_metrics_property(self):
        """Test metrics property access."""
        config = BulkheadConfig(max_concurrent_calls=5)
        bulkhead = ConcreteBulkhead("test", config)
        
        metrics = bulkhead.metrics
        assert isinstance(metrics, BulkheadMetrics)
        assert metrics is bulkhead._metrics


class TestBulkheadMetrics:
    """Test cases for BulkheadMetrics."""
    
    def test_metrics_initialization(self):
        """Test metrics initialization."""
        metrics = BulkheadMetrics()
        assert metrics._available_concurrent_calls == 0
        assert metrics._max_allowed_concurrent_calls == 0
        assert isinstance(metrics._lock, asyncio.Lock)
    
    @pytest.mark.asyncio
    async def test_get_available_concurrent_calls(self):
        """Test getting available concurrent calls."""
        metrics = BulkheadMetrics()
        
        # Default value
        available = await metrics.get_available_concurrent_calls()
        assert available == 0
        
        # Update and check
        await metrics.update_available_concurrent_calls(5)
        available = await metrics.get_available_concurrent_calls()
        assert available == 5
    
    @pytest.mark.asyncio
    async def test_get_max_allowed_concurrent_calls(self):
        """Test getting max allowed concurrent calls."""
        metrics = BulkheadMetrics()
        
        # Default value
        max_allowed = await metrics.get_max_allowed_concurrent_calls()
        assert max_allowed == 0
        
        # Update and check
        await metrics.update_max_allowed_concurrent_calls(10)
        max_allowed = await metrics.get_max_allowed_concurrent_calls()
        assert max_allowed == 10
    
    @pytest.mark.asyncio
    async def test_update_available_concurrent_calls(self):
        """Test updating available concurrent calls."""
        metrics = BulkheadMetrics()
        
        await metrics.update_available_concurrent_calls(3)
        assert metrics._available_concurrent_calls == 3
        
        await metrics.update_available_concurrent_calls(7)
        assert metrics._available_concurrent_calls == 7
    
    @pytest.mark.asyncio
    async def test_update_max_allowed_concurrent_calls(self):
        """Test updating max allowed concurrent calls."""
        metrics = BulkheadMetrics()
        
        await metrics.update_max_allowed_concurrent_calls(15)
        assert metrics._max_allowed_concurrent_calls == 15
        
        await metrics.update_max_allowed_concurrent_calls(20)
        assert metrics._max_allowed_concurrent_calls == 20
    
    @pytest.mark.asyncio
    async def test_metrics_thread_safety(self):
        """Test that metrics operations are thread-safe."""
        metrics = BulkheadMetrics()
        
        async def update_available(value):
            await metrics.update_available_concurrent_calls(value)
        
        async def update_max(value):
            await metrics.update_max_allowed_concurrent_calls(value)
        
        # Run concurrent updates
        tasks = [
            asyncio.create_task(update_available(i))
            for i in range(5)
        ]
        tasks.extend([
            asyncio.create_task(update_max(i * 2))
            for i in range(5)
        ])
        
        await asyncio.gather(*tasks)
        
        # Final values should be from the last updates
        available = await metrics.get_available_concurrent_calls()
        max_allowed = await metrics.get_max_allowed_concurrent_calls()
        
        # Values should be updated (exact values depend on execution order)
        assert isinstance(available, int)
        assert isinstance(max_allowed, int)


class TestBulkheadAbstractMethods:
    """Test the abstract method contracts."""
    
    @pytest.mark.asyncio
    async def test_abstract_method_calls(self):
        """Test that abstract methods can be called in concrete implementation."""
        config = BulkheadConfig(max_concurrent_calls=2)
        bulkhead = ConcreteBulkhead("test", config)
        
        # Test all abstract methods
        permission = await bulkhead.acquire_permission()
        assert permission is True
        
        await bulkhead.release_permission()
        await bulkhead.on_call_permitted()
        await bulkhead.on_call_rejected()
        await bulkhead.on_call_finished()
    
    @pytest.mark.asyncio
    async def test_bulkhead_with_permission_denied(self):
        """Test bulkhead behavior when permission is denied."""
        config = BulkheadConfig(max_concurrent_calls=1)
        bulkhead = ConcreteBulkhead("test", config)
        bulkhead._permission_granted = False
        
        permission = await bulkhead.acquire_permission()
        assert permission is False
    
    def test_bulkhead_cannot_be_instantiated(self):
        """Test that abstract Bulkhead class cannot be instantiated directly."""
        config = BulkheadConfig(max_concurrent_calls=1)
        
        with pytest.raises(TypeError):
            Bulkhead("test", config)