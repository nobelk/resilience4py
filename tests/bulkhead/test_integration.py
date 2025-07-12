"""Integration tests for bulkhead pattern implementations."""

import pytest
import asyncio
import time
import threading
from datetime import timedelta
from unittest.mock import Mock

from resilience4py.bulkhead.semaphore_bulkhead import SemaphoreBulkhead
from resilience4py.bulkhead.threadpool_bulkhead import ThreadPoolBulkhead
from resilience4py.bulkhead.config import BulkheadConfig, ThreadPoolBulkheadConfig
from resilience4py.bulkhead.bulkhead import BulkheadFullException
from resilience4py.bulkhead.events import (
    BulkheadOnCallPermittedEvent,
    BulkheadOnCallRejectedEvent,
    BulkheadOnCallFinishedEvent
)


class TestBulkheadIntegration:
    """Integration tests for bulkhead implementations."""
    
    @pytest.mark.asyncio
    async def test_semaphore_bulkhead_stress_test(self):
        """Stress test semaphore bulkhead with many concurrent requests."""
        config = BulkheadConfig(
            max_concurrent_calls=10,
            max_wait_duration=timedelta(milliseconds=100)
        )
        bulkhead = SemaphoreBulkhead("stress-test", config)
        
        successful_calls = []
        rejected_calls = []
        
        async def worker(worker_id):
            try:
                async def task():
                    await asyncio.sleep(0.05)  # Simulate work
                    return worker_id
                
                result = await bulkhead._execute_async(task)
                successful_calls.append(result)
            except BulkheadFullException:
                rejected_calls.append(worker_id)
        
        # Launch 50 concurrent workers
        workers = [
            asyncio.create_task(worker(i))
            for i in range(50)
        ]
        
        await asyncio.gather(*workers)
        
        # Should have some successful and some rejected
        assert len(successful_calls) > 0
        assert len(rejected_calls) > 0
        assert len(successful_calls) + len(rejected_calls) == 50
        
        # No more than 10 should execute concurrently
        # (This is implicitly tested by the bulkhead logic)
    
    @pytest.mark.asyncio
    async def test_threadpool_bulkhead_cpu_bound_tasks(self):
        """Test thread pool bulkhead with CPU-bound tasks."""
        config = ThreadPoolBulkheadConfig(
            max_thread_pool_size=4,
            core_thread_pool_size=2,
            queue_capacity=10
        )
        bulkhead = ThreadPoolBulkhead("cpu-test", config)
        
        def cpu_bound_task(n):
            """Simulate CPU-bound work."""
            result = 0
            for i in range(n * 1000):
                result += i ** 2
            return result
        
        # Submit multiple CPU-bound tasks
        tasks = [
            asyncio.create_task(bulkhead.submit(cpu_bound_task, i))
            for i in range(10)
        ]
        
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        duration = time.time() - start_time
        
        # All tasks should complete
        assert len(results) == 10
        
        # Should have used thread pool for parallelism
        # (Duration should be less than sequential execution)
        assert duration < 2.0  # Reasonable upper bound
        
        bulkhead.shutdown()
    
    @pytest.mark.asyncio
    async def test_mixed_sync_async_workload(self):
        """Test handling mixed sync/async workload with semaphore bulkhead."""
        config = BulkheadConfig(max_concurrent_calls=5)
        bulkhead = SemaphoreBulkhead("mixed-test", config)
        
        results = []
        
        async def async_task(value):
            await asyncio.sleep(0.02)
            return f"async-{value}"
        
        def sync_task(value):
            time.sleep(0.02)
            return f"sync-{value}"
        
        # Mix async and sync tasks
        tasks = []
        for i in range(10):
            if i % 2 == 0:
                task = bulkhead._execute_async(async_task, i)
            else:
                task = bulkhead._execute_async(sync_task, i)
            tasks.append(asyncio.create_task(task))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successes and failures
        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, BulkheadFullException)]
        
        assert len(successes) > 0
        assert len(failures) > 0  # Some should be rejected due to concurrency limit
    
    @pytest.mark.asyncio
    async def test_event_ordering_and_consistency(self):
        """Test that events are emitted in correct order."""
        config = BulkheadConfig(max_concurrent_calls=2)
        bulkhead = SemaphoreBulkhead("event-test", config)
        
        event_log = []
        
        def log_event(event):
            event_log.append((
                type(event).__name__,
                event.creation_time,
                time.time()
            ))
        
        bulkhead.on_event(log_event)
        
        async def task(task_id):
            await asyncio.sleep(0.05)
            return task_id
        
        # Execute tasks
        task1 = asyncio.create_task(bulkhead._execute_async(task, 1))
        await asyncio.sleep(0.001)  # Allow task1 to start
        task2 = asyncio.create_task(bulkhead._execute_async(task, 2))
        await asyncio.sleep(0.001)  # Allow task2 to start
        
        # This should be rejected
        try:
            await bulkhead._execute_async(task, 3)
        except BulkheadFullException:
            pass
        
        await asyncio.gather(task1, task2)
        
        # Verify event order
        event_types = [e[0] for e in event_log]
        
        # Should have 2 permitted, 1 rejected, 2 finished
        assert event_types.count("BulkheadOnCallPermittedEvent") == 2
        assert event_types.count("BulkheadOnCallRejectedEvent") == 1
        assert event_types.count("BulkheadOnCallFinishedEvent") == 2
        
        # Permitted events should come before their corresponding finished events
        permitted_indices = [i for i, e in enumerate(event_types) if "Permitted" in e]
        finished_indices = [i for i, e in enumerate(event_types) if "Finished" in e]
        
        assert len(permitted_indices) == len(finished_indices)
        assert all(p < f for p, f in zip(sorted(permitted_indices), sorted(finished_indices)))
    
    @pytest.mark.asyncio
    async def test_bulkhead_recovery_after_errors(self):
        """Test that bulkhead recovers properly after errors."""
        config = BulkheadConfig(max_concurrent_calls=3)
        bulkhead = SemaphoreBulkhead("recovery-test", config)
        
        call_count = 0
        
        async def failing_task():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError("Intentional failure")
            return "success"
        
        # First two calls should fail
        with pytest.raises(RuntimeError):
            await bulkhead._execute_async(failing_task)
        
        with pytest.raises(RuntimeError):
            await bulkhead._execute_async(failing_task)
        
        # Bulkhead should still be functional
        result = await bulkhead._execute_async(failing_task)
        assert result == "success"
        
        # All permits should be available again
        assert bulkhead._semaphore._value == 3
    
    @pytest.mark.asyncio
    async def test_threadpool_context_isolation(self):
        """Test that thread pool provides proper context isolation."""
        config = ThreadPoolBulkheadConfig(
            max_thread_pool_size=3,
            queue_capacity=0
        )
        bulkhead = ThreadPoolBulkhead("context-test", config)
        
        results = {}
        
        def isolated_task(task_id):
            # Each thread should have its own local storage
            local_data = threading.local()
            local_data.value = task_id
            
            # Simulate some work
            time.sleep(0.05)
            
            # Value should be unchanged
            return (task_id, local_data.value)
        
        # Submit tasks concurrently
        tasks = [
            asyncio.create_task(bulkhead.submit(isolated_task, i))
            for i in range(3)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Each task should see its own value
        for task_id, stored_value in results:
            assert task_id == stored_value
        
        bulkhead.shutdown()
    
    @pytest.mark.asyncio
    async def test_graceful_degradation_under_load(self):
        """Test that system degrades gracefully under heavy load."""
        # Small bulkhead to simulate resource constraints
        config = BulkheadConfig(
            max_concurrent_calls=3,
            max_wait_duration=timedelta(milliseconds=50)
        )
        bulkhead = SemaphoreBulkhead("degradation-test", config)
        
        metrics = {
            'accepted': 0,
            'rejected': 0,
            'completed': 0,
            'errors': 0
        }
        
        async def monitored_task(task_id):
            try:
                async def work():
                    metrics['accepted'] += 1
                    await asyncio.sleep(0.1)  # Simulate work
                    metrics['completed'] += 1
                    return task_id
                
                return await bulkhead._execute_async(work)
            except BulkheadFullException:
                metrics['rejected'] += 1
                return None
            except Exception:
                metrics['errors'] += 1
                raise
        
        # Submit many tasks rapidly
        tasks = [
            asyncio.create_task(monitored_task(i))
            for i in range(20)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # System should handle load gracefully
        assert metrics['rejected'] > 0  # Some rejections expected
        assert metrics['completed'] > 0  # Some completions expected
        assert metrics['errors'] == 0    # No unexpected errors
        assert metrics['accepted'] == metrics['completed']  # All accepted should complete
    
    @pytest.mark.asyncio
    async def test_concurrent_bulkhead_instances(self):
        """Test multiple bulkhead instances operating independently."""
        # Create two bulkheads with different configurations
        bulkhead1 = SemaphoreBulkhead(
            "bulkhead-1",
            BulkheadConfig(max_concurrent_calls=2)
        )
        
        bulkhead2 = ThreadPoolBulkhead(
            "bulkhead-2",
            ThreadPoolBulkheadConfig(
                max_thread_pool_size=3,
                queue_capacity=2
            )
        )
        
        results1 = []
        results2 = []
        
        async def task1(value):
            await asyncio.sleep(0.05)
            results1.append(value)
            return f"b1-{value}"
        
        def task2(value):
            time.sleep(0.05)
            results2.append(value)
            return f"b2-{value}"
        
        # Submit tasks to both bulkheads concurrently
        all_tasks = []
        
        for i in range(5):
            all_tasks.append(
                asyncio.create_task(bulkhead1._execute_async(task1, i))
            )
            all_tasks.append(
                asyncio.create_task(bulkhead2.submit(task2, i))
            )
        
        results = await asyncio.gather(*all_tasks, return_exceptions=True)
        
        # Both bulkheads should have processed some tasks
        assert len(results1) > 0
        assert len(results2) > 0
        
        # Some tasks should have been rejected from bulkhead1 (lower capacity)
        b1_rejections = [r for r in results if isinstance(r, BulkheadFullException) and "bulkhead-1" in str(r)]
        assert len(b1_rejections) > 0
        
        # Clean up
        bulkhead2.shutdown()