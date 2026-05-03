"""Tests for bulkhead edge cases and error conditions."""

import pytest
import asyncio
import time
from datetime import timedelta
from unittest.mock import Mock, AsyncMock, patch

from resilience4py.bulkhead.semaphore_bulkhead import SemaphoreBulkhead
from resilience4py.bulkhead.threadpool_bulkhead import ThreadPoolBulkhead
from resilience4py.bulkhead.config import BulkheadConfig, ThreadPoolBulkheadConfig
from resilience4py.bulkhead.bulkhead import BulkheadFullException


class TestSemaphoreBulkheadEdgeCases:
    """Test edge cases for SemaphoreBulkhead."""
    
    @pytest.mark.asyncio
    async def test_acquire_permission_edge_case_locked_semaphore(self):
        """Test edge case when semaphore is locked but has value > 0."""
        config = BulkheadConfig(max_concurrent_calls=2, max_wait_duration=timedelta(seconds=0))
        bulkhead = SemaphoreBulkhead("test", config)
        
        # Acquire one permit
        await bulkhead.acquire_permission()
        
        # Try to acquire when semaphore has value but might be in edge state
        permission = await bulkhead.acquire_permission()
        assert permission is True
    
    @pytest.mark.asyncio
    async def test_execute_async_with_exception_in_sync_function(self):
        """Test _execute_async when sync function raises exception."""
        config = BulkheadConfig(max_concurrent_calls=2)
        bulkhead = SemaphoreBulkhead("test", config)
        
        def failing_sync_func():
            raise ValueError("Sync function failed")
        
        with pytest.raises(ValueError, match="Sync function failed"):
            await bulkhead._execute_async(failing_sync_func)
        
        # Bulkhead should be available again
        assert bulkhead._available_permits == 2
    
    @pytest.mark.asyncio
    async def test_execute_async_with_exception_in_async_function(self):
        """Test _execute_async when async function raises exception."""
        config = BulkheadConfig(max_concurrent_calls=2)
        bulkhead = SemaphoreBulkhead("test", config)
        
        async def failing_async_func():
            raise RuntimeError("Async function failed")
        
        with pytest.raises(RuntimeError, match="Async function failed"):
            await bulkhead._execute_async(failing_async_func)
        
        # Bulkhead should be available again
        assert bulkhead._available_permits == 2
    
    @pytest.mark.asyncio
    async def test_publish_event_with_sync_handler_exception(self):
        """Test event publishing when sync handler raises exception."""
        config = BulkheadConfig(max_concurrent_calls=1)
        bulkhead = SemaphoreBulkhead("test", config)
        
        call_count = 0
        
        def failing_handler(event):
            raise RuntimeError("Handler failed")
        
        def working_handler(event):
            nonlocal call_count
            call_count += 1
        
        bulkhead.on_event(failing_handler)
        bulkhead.on_event(working_handler)
        
        async def test_func():
            return "success"
        
        # Execution should succeed despite handler failure
        result = await bulkhead._execute_async(test_func)
        assert result == "success"
        assert call_count == 2  # Working handler called for permitted and finished events
    
    @pytest.mark.asyncio
    async def test_publish_event_with_async_handler_exception(self):
        """Test event publishing when async handler raises exception."""
        config = BulkheadConfig(max_concurrent_calls=1)
        bulkhead = SemaphoreBulkhead("test", config)
        
        call_count = 0
        
        async def failing_async_handler(event):
            raise RuntimeError("Async handler failed")
        
        def working_handler(event):
            nonlocal call_count
            call_count += 1
        
        bulkhead.on_event(failing_async_handler)
        bulkhead.on_event(working_handler)
        
        async def test_func():
            return "success"
        
        # Execution should succeed despite handler failure
        result = await bulkhead._execute_async(test_func)
        assert result == "success"
        assert call_count == 2  # Working handler called for permitted and finished events
    
    @pytest.mark.asyncio
    async def test_multiple_event_handlers_registration(self):
        """Test registering multiple event handlers."""
        config = BulkheadConfig(max_concurrent_calls=1)
        bulkhead = SemaphoreBulkhead("test", config)
        
        events1 = []
        events2 = []
        
        def handler1(event):
            events1.append(event)
        
        def handler2(event):
            events2.append(event)
        
        bulkhead.on_event(handler1)
        bulkhead.on_event(handler2)
        
        async def test_func():
            return "test"
        
        await bulkhead._execute_async(test_func)
        
        # Both handlers should receive events
        assert len(events1) == 2
        assert len(events2) == 2
        assert len(bulkhead._event_handlers) == 2


class TestThreadPoolBulkheadEdgeCases:
    """Test edge cases for ThreadPoolBulkhead."""
    
    @pytest.mark.asyncio
    async def test_lazy_metrics_initialization(self):
        """Metrics initialize lazily on first use rather than at construction.

        Constructor must not depend on ambient event-loop state, so metric
        publication is deferred to the first async call. This avoids the
        "coroutine was never awaited" warnings produced by the old
        asyncio.create_task() in __init__.
        """
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2, queue_capacity=1)

        # Constructor must not require an event loop and must not have initialized metrics yet.
        bulkhead = ThreadPoolBulkhead("test", config)
        assert bulkhead._metrics_initialized is False

        # First call to _ensure_metrics_initialized populates the metric values.
        await bulkhead._ensure_metrics_initialized()
        assert bulkhead._metrics_initialized is True

        # Check metrics are properly set
        assert await bulkhead.metrics.get_max_allowed_concurrent_calls() == 3  # 2 + 1
        assert await bulkhead.metrics.get_available_concurrent_calls() == 3

        # Idempotent — calling again does not re-initialize.
        await bulkhead._ensure_metrics_initialized()
        assert bulkhead._metrics_initialized is True
    
    @pytest.mark.asyncio
    async def test_acquire_permission_when_semaphore_exhausted(self):
        """Test permission acquisition when semaphore is exhausted."""
        config = ThreadPoolBulkheadConfig(
            max_thread_pool_size=1,
            core_thread_pool_size=1,
            queue_capacity=0
        )
        bulkhead = ThreadPoolBulkhead("test", config)
        
        # Acquire the only available permission
        permission1 = await bulkhead.acquire_permission()
        assert permission1 is True
        
        # Next acquisition should fail
        permission2 = await bulkhead.acquire_permission()
        assert permission2 is False
    
    @pytest.mark.asyncio
    async def test_submit_with_context_propagation_exception(self):
        """Test submit when context propagation function raises exception."""
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2)
        bulkhead = ThreadPoolBulkhead("test", config)
        
        def failing_func():
            raise ValueError("Function failed in thread")
        
        with pytest.raises(ValueError, match="Function failed in thread"):
            await bulkhead.submit(failing_func)
    
    @pytest.mark.asyncio
    async def test_execute_async_with_async_function_exception(self):
        """Test _execute_async with async function that raises exception."""
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2)
        bulkhead = ThreadPoolBulkhead("test", config)
        
        async def failing_async_func():
            raise RuntimeError("Async function failed")
        
        with pytest.raises(RuntimeError, match="Async function failed"):
            await bulkhead._execute_async(failing_async_func)
        
        # Permissions should be released
        assert bulkhead._available_permits > 0
    
    @pytest.mark.asyncio
    async def test_execute_async_with_sync_function_exception(self):
        """Test _execute_async with sync function that raises exception."""
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2)
        bulkhead = ThreadPoolBulkhead("test", config)
        
        def failing_sync_func():
            raise ValueError("Sync function failed")
        
        with pytest.raises(ValueError, match="Sync function failed"):
            await bulkhead._execute_async(failing_sync_func)
        
        # Permissions should be released
        assert bulkhead._available_permits > 0
    
    @pytest.mark.asyncio
    async def test_multiple_async_functions_with_bulkhead(self):
        """Test multiple async functions running concurrently with bulkhead."""
        config = ThreadPoolBulkheadConfig(
            max_thread_pool_size=2,
            core_thread_pool_size=1,
            queue_capacity=1
        )
        bulkhead = ThreadPoolBulkhead("test", config)
        
        results = []
        
        async def async_task(task_id):
            await asyncio.sleep(0.01)
            results.append(task_id)
            return task_id
        
        # Submit multiple async tasks
        tasks = [
            asyncio.create_task(bulkhead._execute_async(async_task, i))
            for i in range(3)
        ]
        
        completed_results = await asyncio.gather(*tasks)
        assert sorted(completed_results) == [0, 1, 2]
        assert sorted(results) == [0, 1, 2]
    
    def test_destructor_cleanup(self):
        """Test that destructor properly cleans up thread pool."""
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2)
        bulkhead = ThreadPoolBulkhead("test", config)
        executor = bulkhead._executor
        
        # Manually trigger destructor
        bulkhead.__del__()
        
        # Executor should be shutdown
        assert executor._shutdown is True
    
    def test_destructor_without_executor(self):
        """Test destructor when executor doesn't exist."""
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2)
        bulkhead = ThreadPoolBulkhead("test", config)
        
        # Remove executor
        delattr(bulkhead, '_executor')
        
        # Destructor should not raise exception
        try:
            bulkhead.__del__()
        except AttributeError:
            pytest.fail("Destructor should handle missing executor gracefully")


class TestConfigurationEdgeCases:
    """Test configuration validation edge cases."""
    
    def test_bulkhead_config_validation_errors(self):
        """Test BulkheadConfig validation errors."""
        # Test negative max_concurrent_calls
        with pytest.raises(ValueError, match="max_concurrent_calls must be positive"):
            BulkheadConfig(max_concurrent_calls=0)
        
        with pytest.raises(ValueError, match="max_concurrent_calls must be positive"):
            BulkheadConfig(max_concurrent_calls=-1)
        
        # Test negative max_wait_duration
        with pytest.raises(ValueError, match="max_wait_duration cannot be negative"):
            BulkheadConfig(
                max_concurrent_calls=5,
                max_wait_duration=timedelta(seconds=-1)
            )
    
    def test_threadpool_config_validation_errors(self):
        """Test ThreadPoolBulkheadConfig validation errors."""
        # Test negative max_thread_pool_size
        with pytest.raises(ValueError, match="max_thread_pool_size must be positive"):
            ThreadPoolBulkheadConfig(max_thread_pool_size=0)
        
        # Test negative core_thread_pool_size
        with pytest.raises(ValueError, match="core_thread_pool_size must be positive"):
            ThreadPoolBulkheadConfig(core_thread_pool_size=0)
        
        # Test core > max
        with pytest.raises(ValueError, match="core_thread_pool_size cannot exceed max_thread_pool_size"):
            ThreadPoolBulkheadConfig(
                max_thread_pool_size=2,
                core_thread_pool_size=3
            )
        
        # Test negative queue_capacity
        with pytest.raises(ValueError, match="queue_capacity cannot be negative"):
            ThreadPoolBulkheadConfig(queue_capacity=-1)
        
        # Test negative keep_alive_duration
        with pytest.raises(ValueError, match="keep_alive_duration cannot be negative"):
            ThreadPoolBulkheadConfig(
                keep_alive_duration=timedelta(seconds=-1)
            )
    
    def test_valid_configurations(self):
        """Test that valid configurations pass validation."""
        # Valid BulkheadConfig
        config1 = BulkheadConfig(
            max_concurrent_calls=10,
            max_wait_duration=timedelta(seconds=5)
        )
        assert config1.max_concurrent_calls == 10
        
        # Valid ThreadPoolBulkheadConfig
        config2 = ThreadPoolBulkheadConfig(
            max_thread_pool_size=4,
            core_thread_pool_size=2,
            queue_capacity=10,
            keep_alive_duration=timedelta(milliseconds=100)
        )
        assert config2.max_thread_pool_size == 4
        assert config2.core_thread_pool_size == 2