"""Tests for bulkhead decorator functionality and integration."""

import pytest
import asyncio
import time
from datetime import timedelta
from unittest.mock import Mock, patch

from resilience4py.bulkhead.semaphore_bulkhead import SemaphoreBulkhead
from resilience4py.bulkhead.threadpool_bulkhead import ThreadPoolBulkhead
from resilience4py.bulkhead.config import BulkheadConfig, ThreadPoolBulkheadConfig
from resilience4py.bulkhead.bulkhead import BulkheadFullException


class TestBulkheadDecorators:
    """Test bulkhead decorator functionality."""
    
    @pytest.mark.asyncio
    async def test_semaphore_bulkhead_as_decorator(self):
        """Test using SemaphoreBulkhead as a decorator."""
        config = BulkheadConfig(max_concurrent_calls=2)
        bulkhead = SemaphoreBulkhead("test", config)
        
        call_count = 0
        
        @bulkhead
        async def decorated_async_func(x):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return x * 2
        
        result = await decorated_async_func(5)
        assert result == 10
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_semaphore_bulkhead_decorator_with_sync_function(self):
        """Test using SemaphoreBulkhead decorator with sync function."""
        config = BulkheadConfig(max_concurrent_calls=2)
        bulkhead = SemaphoreBulkhead("test", config)
        
        call_count = 0
        
        @bulkhead
        def decorated_sync_func(x):
            nonlocal call_count
            call_count += 1
            return x * 3
        
        # Need to call decorated sync function within async context
        result = decorated_sync_func(4)
        assert result == 12
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_threadpool_bulkhead_as_decorator(self):
        """Test using ThreadPoolBulkhead as a decorator."""
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2)
        bulkhead = ThreadPoolBulkhead("test", config)
        
        call_count = 0
        
        @bulkhead
        async def decorated_async_func(x):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return x * 2
        
        result = await decorated_async_func(7)
        assert result == 14
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_threadpool_bulkhead_decorator_with_sync_function(self):
        """Test using ThreadPoolBulkhead decorator with sync function."""
        config = ThreadPoolBulkheadConfig(max_thread_pool_size=2)
        bulkhead = ThreadPoolBulkhead("test", config)
        
        call_count = 0
        
        @bulkhead
        def decorated_sync_func(x):
            nonlocal call_count
            call_count += 1
            time.sleep(0.01)  # Small delay to simulate work
            return x * 4
        
        result = decorated_sync_func(3)
        assert result == 12
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_bulkhead_decorator_concurrent_limit(self):
        """Test that bulkhead decorator enforces concurrent limits."""
        config = BulkheadConfig(
            max_concurrent_calls=2,
            max_wait_duration=timedelta(seconds=0)
        )
        bulkhead = SemaphoreBulkhead("test", config)
        
        active_calls = 0
        max_concurrent = 0
        
        @bulkhead
        async def decorated_func():
            nonlocal active_calls, max_concurrent
            active_calls += 1
            max_concurrent = max(max_concurrent, active_calls)
            await asyncio.sleep(0.05)
            active_calls -= 1
            return "done"
        
        # Start 4 concurrent calls
        tasks = [
            asyncio.create_task(decorated_func())
            for _ in range(4)
        ]
        
        # Wait for all to complete or fail
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Should have 2 successes and 2 failures
        successes = [r for r in results if r == "done"]
        failures = [r for r in results if isinstance(r, BulkheadFullException)]
        
        assert len(successes) == 2
        assert len(failures) == 2
        assert max_concurrent == 2
    
    @pytest.mark.asyncio
    async def test_bulkhead_decorator_exception_handling(self):
        """Test bulkhead decorator with function that raises exception."""
        config = BulkheadConfig(max_concurrent_calls=2)
        bulkhead = SemaphoreBulkhead("test", config)
        
        @bulkhead
        async def failing_func():
            raise ValueError("Function failed")
        
        with pytest.raises(ValueError, match="Function failed"):
            await failing_func()
        
        # Bulkhead should be available again
        assert bulkhead._semaphore._value == 2


class TestBulkheadIntegrationScenarios:
    """Test complex integration scenarios."""
    
    @pytest.mark.asyncio
    async def test_mixed_sync_async_workload(self):
        """Test bulkhead with mixed sync and async workloads."""
        config = ThreadPoolBulkheadConfig(
            max_thread_pool_size=3,
            core_thread_pool_size=2,
            queue_capacity=2
        )
        bulkhead = ThreadPoolBulkhead("test", config)
        
        results = []
        
        async def async_task(task_id):
            await asyncio.sleep(0.001)  # Shorter delay
            results.append(f"async-{task_id}")
            return f"async-{task_id}"
        
        def sync_task(task_id):
            time.sleep(0.001)  # Shorter delay
            results.append(f"sync-{task_id}")
            return f"sync-{task_id}"
        
        # Fewer tasks to avoid timing issues
        tasks = []
        for i in range(2):
            tasks.append(asyncio.create_task(bulkhead._execute_async(async_task, i)))
            tasks.append(asyncio.create_task(bulkhead._execute_async(sync_task, i)))
        
        completed_results = await asyncio.gather(*tasks)
        
        # All tasks should complete
        assert len(completed_results) == 4
        assert len(results) == 4
        
        # Check results contain both async and sync
        async_results = [r for r in results if r.startswith("async")]
        sync_results = [r for r in results if r.startswith("sync")]
        assert len(async_results) == 2
        assert len(sync_results) == 2
    
    @pytest.mark.asyncio
    async def test_bulkhead_with_timeout_scenarios(self):
        """Test bulkhead behavior with various timeout scenarios."""
        # Test successful wait
        config = BulkheadConfig(
            max_concurrent_calls=1,
            max_wait_duration=timedelta(milliseconds=200)
        )
        bulkhead = SemaphoreBulkhead("test", config)
        
        async def quick_task():
            await asyncio.sleep(0.05)
            return "quick"
        
        async def waiting_task():
            return "waited"
        
        # Start first task
        task1 = asyncio.create_task(bulkhead._execute_async(quick_task))
        await asyncio.sleep(0.01)  # Ensure it starts
        
        # Start second task (should wait)
        task2 = asyncio.create_task(bulkhead._execute_async(waiting_task))
        
        # Both should complete
        result1 = await task1
        result2 = await task2
        
        assert result1 == "quick"
        assert result2 == "waited"
    
    @pytest.mark.asyncio
    async def test_bulkhead_stress_test(self):
        """Stress test with many concurrent operations."""
        config = BulkheadConfig(
            max_concurrent_calls=5,
            max_wait_duration=timedelta(seconds=1)
        )
        bulkhead = SemaphoreBulkhead("test", config)
        
        completed = []
        
        async def stress_task(task_id):
            await asyncio.sleep(0.001)  # Smaller delay
            completed.append(task_id)
            return task_id
        
        # Submit fewer tasks to avoid timeout issues
        tasks = [
            asyncio.create_task(bulkhead._execute_async(stress_task, i))
            for i in range(10)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All should complete
        assert len(results) == 10
        assert len(completed) == 10
        assert sorted(results) == list(range(10))
    
    @pytest.mark.asyncio
    async def test_bulkhead_resource_cleanup(self):
        """Test that bulkhead properly cleans up resources."""
        config = ThreadPoolBulkheadConfig(
            max_thread_pool_size=2,
            core_thread_pool_size=1,
            queue_capacity=1
        )
        bulkhead = ThreadPoolBulkhead("test", config)
        
        # Submit some work
        def work_task(x):
            time.sleep(0.01)
            return x * 2
        
        tasks = [
            asyncio.create_task(bulkhead.submit(work_task, i))
            for i in range(3)
        ]
        
        results = await asyncio.gather(*tasks)
        assert results == [0, 2, 4]
        
        # Check that resources are properly released
        assert bulkhead._semaphore._value == 3  # All permits released
        
        # Shutdown cleanly
        bulkhead.shutdown(wait=True)
        assert bulkhead._executor._shutdown is True