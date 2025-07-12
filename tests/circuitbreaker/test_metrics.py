"""Tests for Circuit Breaker metrics."""

import asyncio
import time
from datetime import timedelta
import pytest

from resilience4py.circuitbreaker.metrics import (
    CallOutcome, Snapshot, SlidingWindowMetrics, HalfOpenMetrics
)


class TestCallOutcome:
    """Test CallOutcome dataclass."""
    
    def test_call_outcome_creation(self):
        """Test creating a CallOutcome."""
        outcome = CallOutcome(
            timestamp=1234567890.0,
            duration_ms=150.0,
            success=True,
            slow=False
        )
        
        assert outcome.timestamp == 1234567890.0
        assert outcome.duration_ms == 150.0
        assert outcome.success is True
        assert outcome.slow is False


class TestSnapshot:
    """Test Snapshot dataclass."""
    
    def test_snapshot_creation(self):
        """Test creating a Snapshot."""
        snapshot = Snapshot(
            total_calls=100,
            failed_calls=20,
            slow_calls=10,
            failure_rate=20.0,
            slow_call_rate=10.0,
            average_duration=150.0
        )
        
        assert snapshot.total_calls == 100
        assert snapshot.failed_calls == 20
        assert snapshot.slow_calls == 10
        assert snapshot.failure_rate == 20.0
        assert snapshot.slow_call_rate == 10.0
        assert snapshot.average_duration == 150.0
        assert snapshot.successful_calls == 80
    
    def test_successful_calls_property(self):
        """Test successful_calls calculated property."""
        snapshot = Snapshot(
            total_calls=50,
            failed_calls=15,
            slow_calls=5,
            failure_rate=30.0,
            slow_call_rate=10.0,
            average_duration=100.0
        )
        
        assert snapshot.successful_calls == 35


class TestSlidingWindowMetrics:
    """Test SlidingWindowMetrics for both count-based and time-based windows."""
    
    @pytest.mark.asyncio
    async def test_count_based_window_initialization(self):
        """Test count-based sliding window initialization."""
        metrics = SlidingWindowMetrics(
            window_size=10,
            window_type="COUNT_BASED",
            slow_call_duration_threshold_ms=500.0
        )
        
        assert metrics.window_size == 10
        assert metrics.window_type == "COUNT_BASED"
        assert metrics.slow_call_duration_threshold_ms == 500.0
        
        # Initial snapshot should be empty
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 0
        assert snapshot.failed_calls == 0
        assert snapshot.slow_calls == 0
        assert snapshot.failure_rate == 0.0
        assert snapshot.slow_call_rate == 0.0
        assert snapshot.average_duration == 0.0
    
    @pytest.mark.asyncio
    async def test_time_based_window_initialization(self):
        """Test time-based sliding window initialization."""
        metrics = SlidingWindowMetrics(
            window_size=60,  # 60 seconds
            window_type="TIME_BASED",
            slow_call_duration_threshold_ms=1000.0
        )
        
        assert metrics.window_size == 60
        assert metrics.window_type == "TIME_BASED"
        assert metrics.slow_call_duration_threshold_ms == 1000.0
    
    @pytest.mark.asyncio
    async def test_record_success(self):
        """Test recording successful calls."""
        metrics = SlidingWindowMetrics(
            window_size=10,
            window_type="COUNT_BASED",
            slow_call_duration_threshold_ms=500.0
        )
        
        # Record fast successful call
        await metrics.record_success(100.0)
        snapshot = await metrics.get_snapshot()
        
        assert snapshot.total_calls == 1
        assert snapshot.successful_calls == 1
        assert snapshot.failed_calls == 0
        assert snapshot.slow_calls == 0
        assert snapshot.failure_rate == 0.0
        assert snapshot.slow_call_rate == 0.0
        assert snapshot.average_duration == 100.0
        
        # Record slow successful call
        await metrics.record_success(600.0)
        snapshot = await metrics.get_snapshot()
        
        assert snapshot.total_calls == 2
        assert snapshot.successful_calls == 2
        assert snapshot.failed_calls == 0
        assert snapshot.slow_calls == 1
        assert snapshot.failure_rate == 0.0
        assert snapshot.slow_call_rate == 50.0
        assert snapshot.average_duration == 350.0
    
    @pytest.mark.asyncio
    async def test_record_failure(self):
        """Test recording failed calls."""
        metrics = SlidingWindowMetrics(
            window_size=10,
            window_type="COUNT_BASED",
            slow_call_duration_threshold_ms=500.0
        )
        
        # Record fast failed call
        await metrics.record_failure(100.0)
        snapshot = await metrics.get_snapshot()
        
        assert snapshot.total_calls == 1
        assert snapshot.successful_calls == 0
        assert snapshot.failed_calls == 1
        assert snapshot.slow_calls == 0
        assert snapshot.failure_rate == 100.0
        assert snapshot.slow_call_rate == 0.0
        
        # Record slow failed call
        await metrics.record_failure(600.0)
        snapshot = await metrics.get_snapshot()
        
        assert snapshot.total_calls == 2
        assert snapshot.successful_calls == 0
        assert snapshot.failed_calls == 2
        assert snapshot.slow_calls == 1
        assert snapshot.failure_rate == 100.0
        assert snapshot.slow_call_rate == 50.0
    
    @pytest.mark.asyncio
    async def test_count_based_window_eviction(self):
        """Test that count-based window evicts old entries."""
        metrics = SlidingWindowMetrics(
            window_size=3,
            window_type="COUNT_BASED",
            slow_call_duration_threshold_ms=500.0
        )
        
        # Fill the window
        await metrics.record_success(100.0)
        await metrics.record_failure(200.0)
        await metrics.record_success(300.0)
        
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 3
        assert snapshot.failed_calls == 1
        assert snapshot.failure_rate == 33.33333333333333
        
        # Add more calls - should evict oldest
        await metrics.record_success(400.0)
        await metrics.record_success(500.0)
        
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 3  # Still 3 due to window size
        assert snapshot.failed_calls == 0  # Failure was evicted
        assert snapshot.failure_rate == 0.0
    
    @pytest.mark.asyncio
    async def test_time_based_window_eviction(self):
        """Test that time-based window evicts old entries."""
        metrics = SlidingWindowMetrics(
            window_size=1,  # 1 second window
            window_type="TIME_BASED",
            slow_call_duration_threshold_ms=500.0
        )
        
        # Record some calls
        await metrics.record_success(100.0)
        await metrics.record_failure(200.0)
        
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 2
        assert snapshot.failed_calls == 1
        
        # Wait for entries to expire
        await asyncio.sleep(1.1)
        
        # Old entries should be evicted
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 0
        assert snapshot.failed_calls == 0
    
    @pytest.mark.asyncio
    async def test_mixed_call_outcomes(self):
        """Test metrics with mixed success/failure and fast/slow calls."""
        metrics = SlidingWindowMetrics(
            window_size=10,
            window_type="COUNT_BASED",
            slow_call_duration_threshold_ms=500.0
        )
        
        # Record various outcomes
        await metrics.record_success(100.0)  # Fast success
        await metrics.record_success(600.0)  # Slow success
        await metrics.record_failure(200.0)  # Fast failure
        await metrics.record_failure(700.0)  # Slow failure
        await metrics.record_success(300.0)  # Fast success
        
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 5
        assert snapshot.successful_calls == 3
        assert snapshot.failed_calls == 2
        assert snapshot.slow_calls == 2
        assert snapshot.failure_rate == 40.0
        assert snapshot.slow_call_rate == 40.0
        assert snapshot.average_duration == 380.0
    
    @pytest.mark.asyncio
    async def test_reset_metrics(self):
        """Test resetting metrics."""
        metrics = SlidingWindowMetrics(
            window_size=10,
            window_type="COUNT_BASED",
            slow_call_duration_threshold_ms=500.0
        )
        
        # Add some data
        await metrics.record_success(100.0)
        await metrics.record_failure(200.0)
        
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 2
        
        # Reset
        await metrics.reset()
        
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 0
        assert snapshot.failed_calls == 0
        assert snapshot.slow_calls == 0
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test thread safety of metrics operations."""
        metrics = SlidingWindowMetrics(
            window_size=100,
            window_type="COUNT_BASED",
            slow_call_duration_threshold_ms=500.0
        )
        
        # Concurrently record many operations
        async def record_batch():
            for i in range(10):
                if i % 2 == 0:
                    await metrics.record_success(100.0 + i * 50)
                else:
                    await metrics.record_failure(100.0 + i * 50)
        
        # Run multiple batches concurrently
        await asyncio.gather(
            record_batch(),
            record_batch(),
            record_batch(),
            record_batch(),
            record_batch()
        )
        
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 50  # 5 batches * 10 calls each
        assert snapshot.successful_calls == 25  # Half are successes
        assert snapshot.failed_calls == 25  # Half are failures


class TestHalfOpenMetrics:
    """Test HalfOpenMetrics specialized for half-open state."""
    
    @pytest.mark.asyncio
    async def test_half_open_metrics_initialization(self):
        """Test half-open metrics initialization."""
        metrics = HalfOpenMetrics(
            permitted_calls=5,
            slow_call_duration_threshold_ms=500.0
        )
        
        assert metrics.permitted_calls == 5
        assert metrics.slow_call_duration_threshold_ms == 500.0
        assert not await metrics.is_complete()
    
    @pytest.mark.asyncio
    async def test_half_open_metrics_completion(self):
        """Test half-open metrics completion tracking."""
        metrics = HalfOpenMetrics(
            permitted_calls=3,
            slow_call_duration_threshold_ms=500.0
        )
        
        # Record calls up to limit
        await metrics.record_success(100.0)
        assert not await metrics.is_complete()
        
        await metrics.record_failure(200.0)
        assert not await metrics.is_complete()
        
        await metrics.record_success(300.0)
        assert await metrics.is_complete()
        
        # Additional calls should not be recorded
        await metrics.record_success(400.0)
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 3  # Only permitted calls recorded
    
    @pytest.mark.asyncio
    async def test_half_open_metrics_snapshot(self):
        """Test half-open metrics snapshot calculation."""
        metrics = HalfOpenMetrics(
            permitted_calls=4,
            slow_call_duration_threshold_ms=500.0
        )
        
        await metrics.record_success(100.0)  # Fast success
        await metrics.record_success(600.0)  # Slow success
        await metrics.record_failure(200.0)  # Fast failure
        await metrics.record_failure(700.0)  # Slow failure
        
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 4
        assert snapshot.successful_calls == 2
        assert snapshot.failed_calls == 2
        assert snapshot.slow_calls == 2
        assert snapshot.failure_rate == 50.0
        assert snapshot.slow_call_rate == 50.0
        assert snapshot.average_duration == 400.0
    
    @pytest.mark.asyncio
    async def test_half_open_metrics_reset(self):
        """Test resetting half-open metrics."""
        metrics = HalfOpenMetrics(
            permitted_calls=3,
            slow_call_duration_threshold_ms=500.0
        )
        
        # Add data
        await metrics.record_success(100.0)
        await metrics.record_failure(200.0)
        assert not await metrics.is_complete()
        
        # Reset
        await metrics.reset()
        
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 0
        assert not await metrics.is_complete()
    
    @pytest.mark.asyncio
    async def test_half_open_empty_snapshot(self):
        """Test half-open metrics empty snapshot."""
        metrics = HalfOpenMetrics(
            permitted_calls=5,
            slow_call_duration_threshold_ms=500.0
        )
        
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 0
        assert snapshot.failed_calls == 0
        assert snapshot.slow_calls == 0
        assert snapshot.failure_rate == 0.0
        assert snapshot.slow_call_rate == 0.0
        assert snapshot.average_duration == 0.0


class TestMetricsEdgeCases:
    """Test edge cases in metrics calculation."""
    
    @pytest.mark.asyncio
    async def test_zero_duration_calls(self):
        """Test handling of zero duration calls."""
        metrics = SlidingWindowMetrics(
            window_size=10,
            window_type="COUNT_BASED",
            slow_call_duration_threshold_ms=500.0
        )
        
        await metrics.record_success(0.0)
        await metrics.record_failure(0.0)
        
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 2
        assert snapshot.average_duration == 0.0
        assert snapshot.slow_calls == 0  # Zero duration is not slow
    
    @pytest.mark.asyncio
    async def test_exact_threshold_duration(self):
        """Test calls with duration exactly at threshold."""
        metrics = SlidingWindowMetrics(
            window_size=10,
            window_type="COUNT_BASED",
            slow_call_duration_threshold_ms=500.0
        )
        
        await metrics.record_success(500.0)  # Exactly at threshold
        await metrics.record_success(499.9)  # Just below threshold
        
        snapshot = await metrics.get_snapshot()
        assert snapshot.slow_calls == 1  # Only the 500ms call is slow
    
    @pytest.mark.asyncio
    async def test_very_large_window_size(self):
        """Test metrics with very large window size."""
        metrics = SlidingWindowMetrics(
            window_size=10000,
            window_type="COUNT_BASED",
            slow_call_duration_threshold_ms=500.0
        )
        
        # Add many calls
        for i in range(1000):
            if i % 3 == 0:
                await metrics.record_failure(100.0)
            else:
                await metrics.record_success(100.0)
        
        snapshot = await metrics.get_snapshot()
        assert snapshot.total_calls == 1000
        assert snapshot.failed_calls == 334  # ~333 failures
        assert abs(snapshot.failure_rate - 33.4) < 0.1