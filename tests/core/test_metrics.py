"""Tests for all metrics classes and sliding window behavior"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional

from resilience4py.core.metrics import (
    MetricsSnapshot, Metrics, BasicMetrics, 
    CallRecord, SlidingWindowMetrics, MetricsRegistry
)


class TestMetricsSnapshot:
    """Test suite for MetricsSnapshot"""
    
    def test_snapshot_creation(self):
        """Test creating a metrics snapshot"""
        snapshot = MetricsSnapshot(
            total_calls=100,
            successful_calls=90,
            failed_calls=10,
            total_duration=45.5
        )
        
        assert snapshot.total_calls == 100
        assert snapshot.successful_calls == 90
        assert snapshot.failed_calls == 10
        assert snapshot.total_duration == 45.5
        assert isinstance(snapshot.timestamp, datetime)
        assert snapshot.metrics == {}
    
    def test_snapshot_with_custom_metrics(self):
        """Test snapshot with additional metrics"""
        custom_metrics = {
            "p95_latency": 0.95,
            "p99_latency": 0.99,
            "custom_value": 42
        }
        
        snapshot = MetricsSnapshot(
            total_calls=50,
            successful_calls=48,
            failed_calls=2,
            total_duration=25.0,
            metrics=custom_metrics
        )
        
        assert snapshot.metrics == custom_metrics
        assert snapshot.metrics["p95_latency"] == 0.95
        assert snapshot.metrics["custom_value"] == 42
    
    def test_success_rate_calculation(self):
        """Test success rate calculation"""
        # Normal case
        snapshot = MetricsSnapshot(
            total_calls=100,
            successful_calls=75,
            failed_calls=25
        )
        assert snapshot.success_rate == 75.0
        assert snapshot.failure_rate == 25.0
        
        # All successful
        snapshot = MetricsSnapshot(
            total_calls=50,
            successful_calls=50,
            failed_calls=0
        )
        assert snapshot.success_rate == 100.0
        assert snapshot.failure_rate == 0.0
        
        # All failed
        snapshot = MetricsSnapshot(
            total_calls=30,
            successful_calls=0,
            failed_calls=30
        )
        assert snapshot.success_rate == 0.0
        assert snapshot.failure_rate == 100.0
        
        # No calls (edge case)
        snapshot = MetricsSnapshot()
        assert snapshot.success_rate == 100.0  # Default to 100%
        assert snapshot.failure_rate == 0.0
    
    def test_average_duration_calculation(self):
        """Test average duration calculation"""
        # Normal case
        snapshot = MetricsSnapshot(
            total_calls=10,
            total_duration=50.0
        )
        assert snapshot.average_duration == 5.0
        
        # No calls
        snapshot = MetricsSnapshot(
            total_calls=0,
            total_duration=0.0
        )
        assert snapshot.average_duration == 0.0
        
        # Very small durations
        snapshot = MetricsSnapshot(
            total_calls=1000,
            total_duration=0.5
        )
        assert snapshot.average_duration == 0.0005


class TestBasicMetrics:
    """Test suite for BasicMetrics"""
    
    @pytest.mark.asyncio
    async def test_basic_metrics_creation(self):
        """Test creating basic metrics"""
        metrics = BasicMetrics("test_metrics")
        
        assert metrics.name == "test_metrics"
        assert metrics._total_calls == 0
        assert metrics._successful_calls == 0
        assert metrics._failed_calls == 0
        assert metrics._total_duration == 0.0
        assert isinstance(metrics._lock, asyncio.Lock)
    
    @pytest.mark.asyncio
    async def test_record_success(self):
        """Test recording successful calls"""
        metrics = BasicMetrics("test")
        
        await metrics.record_success(0.1)
        await metrics.record_success(0.2)
        await metrics.record_success(0.15)
        
        snapshot = await metrics.get_snapshot()
        
        assert snapshot.total_calls == 3
        assert snapshot.successful_calls == 3
        assert snapshot.failed_calls == 0
        assert snapshot.total_duration == pytest.approx(0.45, 0.01)
        assert snapshot.success_rate == 100.0
    
    @pytest.mark.asyncio
    async def test_record_failure(self):
        """Test recording failed calls"""
        metrics = BasicMetrics("test")
        
        await metrics.record_failure(0.05, Exception("Error 1"))
        await metrics.record_failure(0.1)
        await metrics.record_failure(0.08, RuntimeError("Error 2"))
        
        snapshot = await metrics.get_snapshot()
        
        assert snapshot.total_calls == 3
        assert snapshot.successful_calls == 0
        assert snapshot.failed_calls == 3
        assert snapshot.total_duration == pytest.approx(0.23, 0.01)
        assert snapshot.failure_rate == 100.0
    
    @pytest.mark.asyncio
    async def test_mixed_success_failure(self):
        """Test recording mixed success and failure"""
        metrics = BasicMetrics("test")
        
        # Record some calls
        await metrics.record_success(0.1)
        await metrics.record_failure(0.2)
        await metrics.record_success(0.15)
        await metrics.record_failure(0.05)
        await metrics.record_success(0.2)
        
        snapshot = await metrics.get_snapshot()
        
        assert snapshot.total_calls == 5
        assert snapshot.successful_calls == 3
        assert snapshot.failed_calls == 2
        assert snapshot.total_duration == pytest.approx(0.7, 0.01)
        assert snapshot.success_rate == 60.0
        assert snapshot.average_duration == pytest.approx(0.14, 0.01)
    
    @pytest.mark.asyncio
    async def test_reset_metrics(self):
        """Test resetting metrics"""
        metrics = BasicMetrics("test")
        
        # Record some calls
        await metrics.record_success(0.1)
        await metrics.record_failure(0.2)
        
        # Reset
        await metrics.reset()
        
        # Check everything is reset
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 0
        assert snapshot.successful_calls == 0
        assert snapshot.failed_calls == 0
        assert snapshot.total_duration == 0.0
        
        # Verify we can record new calls
        await metrics.record_success(0.3)
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 1
        assert snapshot.successful_calls == 1
    
    @pytest.mark.asyncio
    async def test_thread_safety(self):
        """Test thread-safe operations"""
        metrics = BasicMetrics("test")
        
        async def record_many(count: int, success: bool):
            for i in range(count):
                if success:
                    await metrics.record_success(0.01)
                else:
                    await metrics.record_failure(0.01)
        
        # Run many concurrent operations
        tasks = []
        for i in range(10):
            tasks.append(record_many(100, i % 2 == 0))
        
        await asyncio.gather(*tasks)
        
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 1000
        assert snapshot.successful_calls == 500
        assert snapshot.failed_calls == 500


class TestCallRecord:
    """Test suite for CallRecord"""
    
    def test_call_record_creation(self):
        """Test creating a call record"""
        timestamp = time.time()
        record = CallRecord(
            timestamp=timestamp,
            duration=0.123,
            success=True,
            metadata={"key": "value"}
        )
        
        assert record.timestamp == timestamp
        assert record.duration == 0.123
        assert record.success is True
        assert record.metadata == {"key": "value"}
    
    def test_call_record_defaults(self):
        """Test call record with defaults"""
        record = CallRecord(
            timestamp=time.time(),
            duration=0.1,
            success=False
        )
        
        assert record.metadata == {}


class TestSlidingWindowMetrics:
    """Test suite for SlidingWindowMetrics"""
    
    @pytest.mark.asyncio
    async def test_count_based_window_creation(self):
        """Test creating count-based sliding window metrics"""
        metrics = SlidingWindowMetrics("test", window_size=100, window_type="COUNT_BASED")
        
        assert metrics.name == "test"
        assert metrics.window_size == 100
        assert metrics.window_type == "COUNT_BASED"
        assert len(metrics._calls) == 0
        # Check that deque has maxlen set
        assert metrics._calls.maxlen == 100
    
    @pytest.mark.asyncio
    async def test_time_based_window_creation(self):
        """Test creating time-based sliding window metrics"""
        metrics = SlidingWindowMetrics("test", window_size=60, window_type="TIME_BASED")
        
        assert metrics.name == "test"
        assert metrics.window_size == 60  # 60 seconds
        assert metrics.window_type == "TIME_BASED"
        # Time-based window should not have maxlen
        assert metrics._calls.maxlen is None
    
    @pytest.mark.asyncio
    async def test_count_based_window_overflow(self):
        """Test that count-based window maintains size limit"""
        metrics = SlidingWindowMetrics("test", window_size=5, window_type="COUNT_BASED")
        
        # Record more than window size
        for i in range(10):
            await metrics.record_success(0.1 * i)
        
        # Should only keep last 5
        assert len(metrics._calls) == 5
        
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 5
        
        # Verify we have the last 5 calls (with durations 0.5 to 0.9)
        durations = [call.duration for call in metrics._calls]
        expected = [0.5, 0.6, 0.7, 0.8, 0.9]
        assert durations == pytest.approx(expected, 0.01)
    
    @pytest.mark.asyncio
    async def test_time_based_window_cleanup(self):
        """Test that time-based window removes old records"""
        # Use 1 second window for faster testing
        metrics = SlidingWindowMetrics("test", window_size=1, window_type="TIME_BASED")
        
        # Record some calls
        for i in range(5):
            await metrics.record_success(0.1)
        
        # Should have all 5
        assert len(metrics._calls) == 5
        
        # Wait for window to expire
        await asyncio.sleep(1.1)
        
        # Record new call to trigger cleanup
        await metrics.record_success(0.2)
        
        # Old calls should be removed, only new one remains
        assert len(metrics._calls) == 1
        assert metrics._calls[0].duration == 0.2
    
    @pytest.mark.asyncio
    async def test_sliding_window_statistics(self):
        """Test statistical calculations in sliding window"""
        metrics = SlidingWindowMetrics("test", window_size=100)
        
        # Record calls with varying durations
        durations = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        for i, duration in enumerate(durations):
            if i < 8:  # 8 success, 2 failures
                await metrics.record_success(duration)
            else:
                await metrics.record_failure(duration, Exception("Test error"))
        
        snapshot = await metrics.get_snapshot()
        
        assert snapshot.total_calls == 10
        assert snapshot.successful_calls == 8
        assert snapshot.failed_calls == 2
        assert snapshot.total_duration == pytest.approx(5.5, 0.01)
        
        # Check calculated metrics
        assert snapshot.metrics['min_duration'] == 0.1
        assert snapshot.metrics['max_duration'] == 1.0
        assert snapshot.metrics['median_duration'] == 0.55
    
    @pytest.mark.asyncio
    async def test_percentile_calculations(self):
        """Test percentile calculations with enough data"""
        metrics = SlidingWindowMetrics("test", window_size=1000)
        
        # Generate 100 calls with known distribution
        for i in range(100):
            duration = i / 100.0  # 0.00 to 0.99
            await metrics.record_success(duration)
        
        snapshot = await metrics.get_snapshot()
        
        # With 100 evenly distributed values, percentiles should be predictable
        # P95 should be around 0.95
        assert 0.93 <= snapshot.metrics['p95_duration'] <= 0.97
        # P99 should be around 0.99
        assert 0.97 <= snapshot.metrics['p99_duration'] <= 0.99
    
    @pytest.mark.asyncio
    async def test_percentiles_with_insufficient_data(self):
        """Test percentile calculations with insufficient data"""
        metrics = SlidingWindowMetrics("test")
        
        # Only 10 calls (less than needed for accurate percentiles)
        for i in range(10):
            await metrics.record_success(i * 0.1)
        
        snapshot = await metrics.get_snapshot()
        
        # Should fall back to max value
        assert snapshot.metrics['p95_duration'] == 0.9  # max value
        assert snapshot.metrics['p99_duration'] == 0.9  # max value
    
    @pytest.mark.asyncio
    async def test_empty_window_snapshot(self):
        """Test snapshot of empty window"""
        metrics = SlidingWindowMetrics("test")
        
        snapshot = await metrics.get_snapshot()
        
        assert snapshot.total_calls == 0
        assert snapshot.successful_calls == 0
        assert snapshot.failed_calls == 0
        assert snapshot.total_duration == 0.0
        assert snapshot.metrics == {}  # No statistical metrics for empty window
    
    @pytest.mark.asyncio
    async def test_exception_metadata_storage(self):
        """Test that exceptions are stored in metadata"""
        metrics = SlidingWindowMetrics("test")
        
        error = RuntimeError("Test error")
        await metrics.record_failure(0.5, error)
        
        assert len(metrics._calls) == 1
        record = metrics._calls[0]
        assert not record.success
        assert record.metadata['exception'] == "Test error"
        
        # Test with no exception
        await metrics.record_failure(0.3)
        record = metrics._calls[1]
        assert record.metadata['exception'] is None


class ConcreteMetrics(Metrics):
    """Concrete implementation for testing abstract base class"""
    
    def __init__(self, name: str):
        super().__init__(name)
        self.successes = []
        self.failures = []
    
    async def record_success(self, duration: float, **kwargs) -> None:
        self.successes.append((duration, kwargs))
    
    async def record_failure(self, duration: float, exception: Optional[Exception] = None, **kwargs) -> None:
        self.failures.append((duration, exception, kwargs))
    
    async def get_snapshot(self) -> MetricsSnapshot:
        return MetricsSnapshot(
            total_calls=len(self.successes) + len(self.failures),
            successful_calls=len(self.successes),
            failed_calls=len(self.failures)
        )
    
    async def reset(self) -> None:
        self.successes.clear()
        self.failures.clear()


class TestMetricsAbstract:
    """Test suite for abstract Metrics class"""
    
    def test_abstract_metrics_cannot_instantiate(self):
        """Test that Metrics ABC cannot be instantiated directly"""
        with pytest.raises(TypeError):
            Metrics("test")
    
    @pytest.mark.asyncio
    async def test_concrete_implementation(self):
        """Test concrete implementation of Metrics"""
        metrics = ConcreteMetrics("test")
        
        await metrics.record_success(0.1, extra="data")
        await metrics.record_failure(0.2, RuntimeError("Error"))
        
        assert len(metrics.successes) == 1
        assert len(metrics.failures) == 1
        
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 2
        assert snapshot.successful_calls == 1
        assert snapshot.failed_calls == 1


class TestMetricsRegistry:
    """Test suite for MetricsRegistry"""
    
    @pytest.mark.asyncio
    async def test_registry_creation(self):
        """Test creating a metrics registry"""
        registry = MetricsRegistry()
        
        assert len(registry._metrics) == 0
        assert isinstance(registry._lock, asyncio.Lock)
    
    @pytest.mark.asyncio
    async def test_register_metrics(self):
        """Test registering metrics collectors"""
        registry = MetricsRegistry()
        
        metrics1 = BasicMetrics("component1")
        metrics2 = SlidingWindowMetrics("component2")
        
        await registry.register("metrics1", metrics1)
        await registry.register("metrics2", metrics2)
        
        assert len(registry._metrics) == 2
        assert await registry.get("metrics1") is metrics1
        assert await registry.get("metrics2") is metrics2
    
    @pytest.mark.asyncio
    async def test_unregister_metrics(self):
        """Test unregistering metrics"""
        registry = MetricsRegistry()
        
        metrics = BasicMetrics("test")
        await registry.register("test", metrics)
        
        # Unregister
        await registry.unregister("test")
        
        assert await registry.get("test") is None
        assert len(registry._metrics) == 0
        
        # Unregister non-existent (should not raise)
        await registry.unregister("non-existent")
    
    @pytest.mark.asyncio
    async def test_get_all_snapshots(self):
        """Test getting snapshots from all metrics"""
        registry = MetricsRegistry()
        
        # Register multiple metrics
        metrics1 = BasicMetrics("comp1")
        metrics2 = BasicMetrics("comp2")
        
        await metrics1.record_success(0.1)
        await metrics1.record_success(0.2)
        await metrics2.record_failure(0.3)
        
        await registry.register("metrics1", metrics1)
        await registry.register("metrics2", metrics2)
        
        # Get all snapshots
        snapshots = await registry.get_all_snapshots()
        
        assert len(snapshots) == 2
        assert "metrics1" in snapshots
        assert "metrics2" in snapshots
        
        assert snapshots["metrics1"].total_calls == 2
        assert snapshots["metrics1"].successful_calls == 2
        assert snapshots["metrics2"].total_calls == 1
        assert snapshots["metrics2"].failed_calls == 1
    
    @pytest.mark.asyncio
    async def test_reset_all_metrics(self):
        """Test resetting all registered metrics"""
        registry = MetricsRegistry()
        
        # Register and populate metrics
        metrics1 = BasicMetrics("comp1")
        metrics2 = BasicMetrics("comp2")
        
        await metrics1.record_success(0.1)
        await metrics2.record_failure(0.2)
        
        await registry.register("metrics1", metrics1)
        await registry.register("metrics2", metrics2)
        
        # Reset all
        await registry.reset_all()
        
        # Check all are reset
        snapshots = await registry.get_all_snapshots()
        assert snapshots["metrics1"].total_calls == 0
        assert snapshots["metrics2"].total_calls == 0
    
    @pytest.mark.asyncio
    async def test_registry_thread_safety(self):
        """Test thread-safe registry operations"""
        registry = MetricsRegistry()
        
        async def register_many(start_idx: int):
            for i in range(10):
                metrics = BasicMetrics(f"comp_{start_idx}_{i}")
                await registry.register(f"metrics_{start_idx}_{i}", metrics)
        
        # Register many metrics concurrently
        tasks = [register_many(i * 10) for i in range(10)]
        await asyncio.gather(*tasks)
        
        # Should have all 100 metrics
        assert len(registry._metrics) == 100
        
        # Get all snapshots should work
        snapshots = await registry.get_all_snapshots()
        assert len(snapshots) == 100