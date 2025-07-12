"""Tests for semaphore-based bulkhead implementation."""

import pytest
import asyncio
from datetime import timedelta
from unittest.mock import Mock, AsyncMock, patch
import time

from resilience4py.bulkhead.semaphore_bulkhead import SemaphoreBulkhead
from resilience4py.bulkhead.config import BulkheadConfig
from resilience4py.bulkhead.bulkhead import BulkheadFullException
from resilience4py.bulkhead.events import (
    BulkheadOnCallPermittedEvent,
    BulkheadOnCallRejectedEvent,
    BulkheadOnCallFinishedEvent
)


class TestSemaphoreBulkhead:
    """Test cases for SemaphoreBulkhead."""
    
    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test bulkhead initialization."""
        config = BulkheadConfig(max_concurrent_calls=5)
        bulkhead = SemaphoreBulkhead("test-bulkhead", config)
        
        assert bulkhead.name == "test-bulkhead"
        assert bulkhead.config == config
        assert bulkhead._semaphore._value == 5
        
        # Check metrics initialization - trigger deferred init
        await bulkhead._init_metrics_if_needed()
        assert await bulkhead.metrics.get_max_allowed_concurrent_calls() == 5
        assert await bulkhead.metrics.get_available_concurrent_calls() == 5
    
    @pytest.mark.asyncio
    async def test_acquire_permission_success(self):
        """Test successful permission acquisition."""
        config = BulkheadConfig(max_concurrent_calls=2)
        bulkhead = SemaphoreBulkhead("test", config)
        
        # First acquisition should succeed
        assert await bulkhead.acquire_permission() is True
        assert bulkhead._semaphore._value == 1
        
        # Second acquisition should succeed
        assert await bulkhead.acquire_permission() is True
        assert bulkhead._semaphore._value == 0
    
    @pytest.mark.asyncio
    async def test_acquire_permission_no_wait_rejection(self):
        """Test permission rejection when no wait is configured."""
        config = BulkheadConfig(
            max_concurrent_calls=1,
            max_wait_duration=timedelta(seconds=0)
        )
        bulkhead = SemaphoreBulkhead("test", config)
        
        # First acquisition succeeds
        assert await bulkhead.acquire_permission() is True
        
        # Second acquisition should fail immediately
        assert await bulkhead.acquire_permission() is False
    
    @pytest.mark.asyncio
    async def test_acquire_permission_with_timeout(self):
        """Test permission acquisition with timeout."""
        config = BulkheadConfig(
            max_concurrent_calls=1,
            max_wait_duration=timedelta(milliseconds=100)
        )
        bulkhead = SemaphoreBulkhead("test", config)
        
        # First acquisition succeeds
        assert await bulkhead.acquire_permission() is True
        
        # Second acquisition should timeout
        start = time.time()
        assert await bulkhead.acquire_permission() is False
        elapsed = time.time() - start
        
        # Should have waited approximately the timeout duration
        assert 0.08 < elapsed < 0.15  # Allow some tolerance
    
    @pytest.mark.asyncio
    async def test_release_permission(self):
        """Test permission release."""
        config = BulkheadConfig(max_concurrent_calls=1)
        bulkhead = SemaphoreBulkhead("test", config)
        
        # Acquire permission
        await bulkhead.acquire_permission()
        assert bulkhead._semaphore._value == 0
        
        # Release permission
        await bulkhead.release_permission()
        assert bulkhead._semaphore._value == 1
        
        # Check metrics
        assert await bulkhead.metrics.get_available_concurrent_calls() == 1
    
    @pytest.mark.asyncio
    async def test_execute_async_function_success(self):
        """Test executing an async function successfully."""
        config = BulkheadConfig(max_concurrent_calls=2)
        bulkhead = SemaphoreBulkhead("test", config)
        
        async def async_func(x, y):
            await asyncio.sleep(0.01)
            return x + y
        
        result = await bulkhead._execute_async(async_func, 5, 3)
        assert result == 8
    
    @pytest.mark.asyncio
    async def test_execute_sync_function_success(self):
        """Test executing a sync function successfully."""
        config = BulkheadConfig(max_concurrent_calls=2)
        bulkhead = SemaphoreBulkhead("test", config)
        
        def sync_func(x, y):
            return x * y
        
        result = await bulkhead._execute_async(sync_func, 4, 5)
        assert result == 20
    
    @pytest.mark.asyncio
    async def test_execute_function_bulkhead_full(self):
        """Test function execution when bulkhead is full."""
        config = BulkheadConfig(
            max_concurrent_calls=1,
            max_wait_duration=timedelta(seconds=0)
        )
        bulkhead = SemaphoreBulkhead("test", config)
        
        async def slow_func():
            await asyncio.sleep(0.1)
            return "done"
        
        # Start first execution (don't await)
        task1 = asyncio.create_task(bulkhead._execute_async(slow_func))
        
        # Give it time to acquire the semaphore
        await asyncio.sleep(0.01)
        
        # Second execution should fail
        with pytest.raises(BulkheadFullException, match="Bulkhead 'test' is full"):
            await bulkhead._execute_async(slow_func)
        
        # Clean up
        await task1
    
    @pytest.mark.asyncio
    async def test_concurrent_execution_limit(self):
        """Test that concurrent executions are properly limited."""
        config = BulkheadConfig(max_concurrent_calls=3)
        bulkhead = SemaphoreBulkhead("test", config)
        
        execution_count = 0
        max_concurrent = 0
        
        async def track_concurrent():
            nonlocal execution_count, max_concurrent
            execution_count += 1
            current = execution_count
            max_concurrent = max(max_concurrent, current)
            await asyncio.sleep(0.05)
            execution_count -= 1
        
        # Start 5 concurrent tasks
        tasks = [
            asyncio.create_task(bulkhead._execute_async(track_concurrent))
            for _ in range(5)
        ]
        
        # Wait for all to complete or fail
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check that max concurrent was limited to 3
        assert max_concurrent == 3
        
        # Check that 2 tasks were rejected
        exceptions = [r for r in results if isinstance(r, BulkheadFullException)]
        assert len(exceptions) == 2
    
    @pytest.mark.asyncio
    async def test_event_emission(self):
        """Test that events are properly emitted."""
        config = BulkheadConfig(max_concurrent_calls=1)
        bulkhead = SemaphoreBulkhead("test", config)
        
        events = []
        
        def event_handler(event):
            events.append(event)
        
        bulkhead.on_event(event_handler)
        
        # Successful execution
        async def success_func():
            return "success"
        
        await bulkhead._execute_async(success_func)
        
        # Check permitted and finished events
        assert len(events) == 2
        assert isinstance(events[0], BulkheadOnCallPermittedEvent)
        assert isinstance(events[1], BulkheadOnCallFinishedEvent)
        
        # Clear events
        events.clear()
        
        # Start a blocking task
        async def blocking_func():
            await asyncio.sleep(0.1)
        
        task = asyncio.create_task(bulkhead._execute_async(blocking_func))
        await asyncio.sleep(0.01)  # Let it acquire
        
        # Try another call (should be rejected)
        with pytest.raises(BulkheadFullException):
            await bulkhead._execute_async(success_func)
        
        # Check rejected event - we should have permitted (for blocking) and rejected events
        assert len(events) == 2  # permitted (for blocking), rejected
        assert isinstance(events[0], BulkheadOnCallPermittedEvent)  # for blocking task
        assert isinstance(events[1], BulkheadOnCallRejectedEvent)   # for rejected task
        
        # Clean up
        await task
    
    @pytest.mark.asyncio
    async def test_async_event_handler(self):
        """Test async event handler support."""
        config = BulkheadConfig(max_concurrent_calls=1)
        bulkhead = SemaphoreBulkhead("test", config)
        
        events = []
        
        async def async_handler(event):
            await asyncio.sleep(0.01)
            events.append(event)
        
        bulkhead.on_event(async_handler)
        
        async def test_func():
            return "test"
        
        await bulkhead._execute_async(test_func)
        
        # Wait for async handler
        await asyncio.sleep(0.02)
        
        assert len(events) == 2
        assert isinstance(events[0], BulkheadOnCallPermittedEvent)
        assert isinstance(events[1], BulkheadOnCallFinishedEvent)
    
    @pytest.mark.asyncio
    async def test_event_handler_exception_handling(self):
        """Test that event handler exceptions don't break execution."""
        config = BulkheadConfig(max_concurrent_calls=1)
        bulkhead = SemaphoreBulkhead("test", config)
        
        def failing_handler(event):
            raise RuntimeError("Handler error")
        
        def working_handler(event):
            working_handler.called = True
        
        working_handler.called = False
        
        bulkhead.on_event(failing_handler)
        bulkhead.on_event(working_handler)
        
        async def test_func():
            return "success"
        
        # Should complete successfully despite handler error
        result = await bulkhead._execute_async(test_func)
        assert result == "success"
        assert working_handler.called
    
    @pytest.mark.asyncio
    async def test_function_exception_propagation(self):
        """Test that function exceptions are propagated correctly."""
        config = BulkheadConfig(max_concurrent_calls=1)
        bulkhead = SemaphoreBulkhead("test", config)
        
        async def failing_func():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError, match="Test error"):
            await bulkhead._execute_async(failing_func)
        
        # Bulkhead should be released after exception
        assert bulkhead._semaphore._value == 1
    
    @pytest.mark.asyncio
    async def test_metrics_update_during_execution(self):
        """Test that metrics are updated correctly during execution."""
        config = BulkheadConfig(max_concurrent_calls=3)
        bulkhead = SemaphoreBulkhead("test", config)
        
        # Initial state - trigger deferred init
        await bulkhead._init_metrics_if_needed()
        assert await bulkhead.metrics.get_available_concurrent_calls() == 3
        
        async def slow_func():
            await asyncio.sleep(0.05)
        
        # Start 2 executions
        task1 = asyncio.create_task(bulkhead._execute_async(slow_func))
        task2 = asyncio.create_task(bulkhead._execute_async(slow_func))
        
        await asyncio.sleep(0.01)
        assert await bulkhead.metrics.get_available_concurrent_calls() == 1
        
        # Start one more
        task3 = asyncio.create_task(bulkhead._execute_async(slow_func))
        
        await asyncio.sleep(0.01)
        assert await bulkhead.metrics.get_available_concurrent_calls() == 0
        
        # Wait for all to complete
        await asyncio.gather(task1, task2, task3)
        
        # Should be back to full capacity
        assert await bulkhead.metrics.get_available_concurrent_calls() == 3
    
    @pytest.mark.asyncio
    async def test_wait_duration_with_release(self):
        """Test that waiting requests succeed when permits are released."""
        config = BulkheadConfig(
            max_concurrent_calls=1,
            max_wait_duration=timedelta(seconds=1)
        )
        bulkhead = SemaphoreBulkhead("test", config)
        
        async def holder_func():
            await asyncio.sleep(0.05)
            return "holder"
        
        async def waiter_func():
            return "waiter"
        
        # Start holder
        holder_task = asyncio.create_task(bulkhead._execute_async(holder_func))
        await asyncio.sleep(0.01)  # Ensure holder acquires first
        
        # Start waiter
        waiter_task = asyncio.create_task(bulkhead._execute_async(waiter_func))
        
        # Both should complete successfully
        holder_result = await holder_task
        waiter_result = await waiter_task
        
        assert holder_result == "holder"
        assert waiter_result == "waiter"