"""Tests for thread pool-based bulkhead implementation."""

import pytest
import asyncio
import contextvars
import threading
import time
from datetime import timedelta
from unittest.mock import Mock, patch
from concurrent.futures import ThreadPoolExecutor

from resilience4py.bulkhead.threadpool_bulkhead import ThreadPoolBulkhead
from resilience4py.bulkhead.config import ThreadPoolBulkheadConfig, BulkheadConfig
from resilience4py.bulkhead.bulkhead import BulkheadFullException
from resilience4py.bulkhead.events import (
    BulkheadOnCallPermittedEvent,
    BulkheadOnCallRejectedEvent,
    BulkheadOnCallFinishedEvent
)


class TestThreadPoolBulkhead:
    """Test cases for ThreadPoolBulkhead."""
    
    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test bulkhead initialization."""
        config = ThreadPoolBulkheadConfig(
            max_thread_pool_size=4,
            core_thread_pool_size=2,
            queue_capacity=10
        )
        bulkhead = ThreadPoolBulkhead("test-bulkhead", config)

        assert bulkhead.name == "test-bulkhead"
        assert bulkhead.thread_config == config
        assert isinstance(bulkhead._executor, ThreadPoolExecutor)
        assert bulkhead._executor._max_workers == 4

        # Check semaphore capacity (threads + queue)
        assert bulkhead._available_permits == 14  # 4 + 10

        # Metrics initialize lazily — trigger explicit init then verify.
        await bulkhead._ensure_metrics_initialized()
        assert await bulkhead.metrics.get_max_allowed_concurrent_calls() == 14
        assert await bulkhead.metrics.get_available_concurrent_calls() == 14
    
    @pytest.mark.asyncio
    async def test_acquire_release_permission(self):
        """Test permission acquisition and release."""
        config = ThreadPoolBulkheadConfig(
            max_thread_pool_size=2,
            queue_capacity=1
        )
        bulkhead = ThreadPoolBulkhead("test", config)
        
        # Total capacity is 3 (2 threads + 1 queue)
        assert await bulkhead.acquire_permission() is True
        assert bulkhead._available_permits == 2
        
        assert await bulkhead.acquire_permission() is True
        assert bulkhead._available_permits == 1
        
        assert await bulkhead.acquire_permission() is True
        assert bulkhead._available_permits == 0
        
        # Next should fail
        assert await bulkhead.acquire_permission() is False
        
        # Release one
        await bulkhead.release_permission()
        assert bulkhead._available_permits == 1
        
        # Now acquisition should succeed
        assert await bulkhead.acquire_permission() is True
    
    @pytest.mark.asyncio
    async def test_submit_sync_function(self):
        """Test submitting sync function to thread pool."""
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2)
        bulkhead = ThreadPoolBulkhead("test", config)
        
        def sync_func(x, y):
            # Verify we're in a different thread
            assert threading.current_thread().name.startswith("bulkhead-test")
            return x + y
        
        result = await bulkhead.submit(sync_func, 10, 20)
        assert result == 30
    
    @pytest.mark.asyncio
    async def test_submit_with_kwargs(self):
        """Test submitting function with keyword arguments."""
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2)
        bulkhead = ThreadPoolBulkhead("test", config)
        
        def func_with_kwargs(a, b=5, c=10):
            return a + b + c
        
        result = await bulkhead.submit(func_with_kwargs, 1, b=2, c=3)
        assert result == 6
    
    @pytest.mark.asyncio
    async def test_submit_bulkhead_full(self):
        """Test submit when bulkhead is full."""
        config = ThreadPoolBulkheadConfig(
            max_thread_pool_size=1,
            core_thread_pool_size=1,  # Must not exceed max_thread_pool_size
            queue_capacity=0
        )
        bulkhead = ThreadPoolBulkhead("test", config)
        
        def slow_func():
            time.sleep(0.1)
            return "done"
        
        # Start first execution
        task1 = asyncio.create_task(bulkhead.submit(slow_func))
        await asyncio.sleep(0.01)  # Ensure it starts
        
        # Second should be rejected
        with pytest.raises(BulkheadFullException, match="ThreadPool bulkhead 'test' is full"):
            await bulkhead.submit(slow_func)
        
        # Wait for first to complete
        await task1
    
    @pytest.mark.asyncio
    async def test_context_propagation(self):
        """Test that context variables are propagated to thread pool."""
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2)
        bulkhead = ThreadPoolBulkhead("test", config)
        
        # Create a context variable
        request_id = contextvars.ContextVar('request_id')
        request_id.set("test-123")
        
        def check_context():
            # Context should be preserved in thread
            return request_id.get()
        
        result = await bulkhead.submit(check_context)
        assert result == "test-123"
    
    @pytest.mark.asyncio
    async def test_execute_async_with_sync_function(self):
        """Test _execute_async with sync function (uses thread pool)."""
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2)
        bulkhead = ThreadPoolBulkhead("test", config)
        
        def sync_func(x):
            return x * 2
        
        result = await bulkhead._execute_async(sync_func, 5)
        assert result == 10
    
    @pytest.mark.asyncio
    async def test_execute_async_with_async_function(self):
        """Test _execute_async with async function (runs in event loop)."""
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2)
        bulkhead = ThreadPoolBulkhead("test", config)
        
        async def async_func(x):
            await asyncio.sleep(0.01)
            # Should be in main thread (event loop)
            assert threading.current_thread() == threading.main_thread()
            return x * 3
        
        result = await bulkhead._execute_async(async_func, 4)
        assert result == 12
    
    @pytest.mark.asyncio
    async def test_concurrent_thread_pool_execution(self):
        """Test concurrent execution in thread pool."""
        config = ThreadPoolBulkheadConfig(
            max_thread_pool_size=3,
            queue_capacity=2
        )
        bulkhead = ThreadPoolBulkhead("test", config)
        
        execution_times = []
        thread_names = set()
        
        def track_execution(task_id):
            thread_names.add(threading.current_thread().name)
            start = time.time()
            time.sleep(0.05)
            execution_times.append((task_id, time.time() - start))
            return task_id
        
        # Submit 5 tasks (3 threads + 2 queue)
        tasks = [
            asyncio.create_task(bulkhead.submit(track_execution, i))
            for i in range(5)
        ]
        
        results = await asyncio.gather(*tasks)
        assert sorted(results) == list(range(5))
        
        # Should have used at most 3 threads
        assert len(thread_names) <= 3
        
        # All tasks should have completed
        assert len(execution_times) == 5
    
    @pytest.mark.asyncio
    async def test_queue_overflow(self):
        """Test behavior when both thread pool and queue are full."""
        config = ThreadPoolBulkheadConfig(
            max_thread_pool_size=2,
            queue_capacity=1
        )
        bulkhead = ThreadPoolBulkhead("test", config)
        
        def slow_task(i):
            time.sleep(0.1)
            return i
        
        # Submit tasks to fill threads and queue
        tasks = []
        for i in range(3):  # 2 threads + 1 queue
            tasks.append(asyncio.create_task(bulkhead.submit(slow_task, i)))
            await asyncio.sleep(0.01)
        
        # Next submission should fail
        with pytest.raises(BulkheadFullException):
            await bulkhead.submit(slow_task, 99)
        
        # Wait for all tasks
        results = await asyncio.gather(*tasks)
        assert sorted(results) == [0, 1, 2]
    
    @pytest.mark.asyncio
    async def test_event_emission(self):
        """Test event emission for thread pool bulkhead."""
        config = ThreadPoolBulkheadConfig(
            max_thread_pool_size=1,
            core_thread_pool_size=1,  # Must not exceed max_thread_pool_size
            queue_capacity=0
        )
        bulkhead = ThreadPoolBulkhead("test", config)
        
        events = []
        
        def event_handler(event):
            events.append(event)
        
        bulkhead.on_event(event_handler)
        
        # Successful execution
        def success_func():
            return "success"
        
        await bulkhead.submit(success_func)
        
        # Should have permitted and finished events
        assert len(events) == 2
        assert isinstance(events[0], BulkheadOnCallPermittedEvent)
        assert isinstance(events[1], BulkheadOnCallFinishedEvent)
        
        # Clear events
        events.clear()
        
        # Fill the bulkhead
        def blocking_func():
            time.sleep(0.1)
        
        task = asyncio.create_task(bulkhead.submit(blocking_func))
        await asyncio.sleep(0.01)
        
        # Try another (should be rejected)
        with pytest.raises(BulkheadFullException):
            await bulkhead.submit(success_func)
        
        # Should have rejected event
        rejected_events = [e for e in events if isinstance(e, BulkheadOnCallRejectedEvent)]
        assert len(rejected_events) == 1
        
        await task
    
    @pytest.mark.asyncio
    async def test_exception_propagation(self):
        """Test that exceptions from submitted functions are propagated."""
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2)
        bulkhead = ThreadPoolBulkhead("test", config)
        
        def failing_func():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError, match="Test error"):
            await bulkhead.submit(failing_func)
        
        # Bulkhead should be available again
        assert bulkhead._available_permits > 0
    
    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test graceful shutdown of thread pool."""
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2)
        bulkhead = ThreadPoolBulkhead("test", config)
        
        completed = []
        
        def task(i):
            time.sleep(0.05)
            completed.append(i)
            return i
        
        # Submit tasks and wait a bit for them to start
        task1 = asyncio.create_task(bulkhead.submit(task, 1))
        task2 = asyncio.create_task(bulkhead.submit(task, 2))
        await asyncio.sleep(0.01)  # Let tasks start
        
        # Tasks should complete before shutdown
        await asyncio.gather(task1, task2)
        assert sorted(completed) == [1, 2]
        
        # Now shutdown with wait
        bulkhead.shutdown(wait=True)
        
        # Further submissions should fail
        with pytest.raises(RuntimeError):  # Executor is shutdown
            await bulkhead.submit(task, 3)
    
    @pytest.mark.asyncio
    async def test_shutdown_no_wait(self):
        """Test immediate shutdown without waiting."""
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2)
        bulkhead = ThreadPoolBulkhead("test", config)
        
        def slow_task():
            time.sleep(0.1)  # Shorter delay
            return "done"
        
        # Immediate shutdown (before submitting)
        bulkhead.shutdown(wait=False)
        
        # Task should fail due to shutdown
        with pytest.raises(RuntimeError, match="cannot schedule new futures after shutdown"):
            await bulkhead.submit(slow_task)
    
    @pytest.mark.asyncio
    async def test_metrics_updates(self):
        """Test that metrics are properly updated during execution."""
        config = ThreadPoolBulkheadConfig(
            max_thread_pool_size=2,
            queue_capacity=1
        )
        bulkhead = ThreadPoolBulkhead("test", config)

        # Initial state — trigger lazy metric init explicitly.
        await bulkhead._ensure_metrics_initialized()
        assert await bulkhead.metrics.get_max_allowed_concurrent_calls() == 3
        assert await bulkhead.metrics.get_available_concurrent_calls() == 3
        
        def task():
            time.sleep(0.05)
        
        # Submit tasks
        task1 = asyncio.create_task(bulkhead.submit(task))
        await asyncio.sleep(0.01)
        assert await bulkhead.metrics.get_available_concurrent_calls() == 2
        
        task2 = asyncio.create_task(bulkhead.submit(task))
        await asyncio.sleep(0.01)
        assert await bulkhead.metrics.get_available_concurrent_calls() == 1
        
        # Wait for completion
        await asyncio.gather(task1, task2)
        assert await bulkhead.metrics.get_available_concurrent_calls() == 3
    
    def test_destructor(self):
        """Test that destructor shuts down thread pool."""
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2)
        bulkhead = ThreadPoolBulkhead("test", config)
        executor = bulkhead._executor
        
        # Delete bulkhead
        del bulkhead
        
        # Executor should be shutdown
        assert executor._shutdown is True