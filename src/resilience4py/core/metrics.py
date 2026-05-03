"""
Metrics abstractions for resilience patterns

Provides base classes for collecting and reporting metrics
across all resilience patterns.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
import asyncio
import time
from collections import deque
import statistics


@dataclass
class MetricsSnapshot:
    """Immutable snapshot of metrics at a point in time
    
    This base class can be extended by specific patterns to include
    additional metrics relevant to that pattern.
    
    Attributes:
        timestamp: When this snapshot was taken
        total_calls: Total number of calls recorded
        successful_calls: Number of successful calls
        failed_calls: Number of failed calls
        total_duration: Total duration of all calls in seconds
        metrics: Additional pattern-specific metrics
    """
    timestamp: datetime = field(default_factory=datetime.now)
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_duration: float = 0.0
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as a percentage"""
        if self.total_calls == 0:
            return 100.0
        return (self.successful_calls / self.total_calls) * 100.0
    
    @property
    def failure_rate(self) -> float:
        """Calculate failure rate as a percentage"""
        return 100.0 - self.success_rate
    
    @property
    def average_duration(self) -> float:
        """Calculate average call duration in seconds"""
        if self.total_calls == 0:
            return 0.0
        return self.total_duration / self.total_calls


class Metrics(ABC):
    """Abstract base class for metrics collection
    
    Each resilience pattern should implement its own metrics class
    that extends this base class with pattern-specific metrics.
    """
    
    def __init__(self, name: str):
        """Initialize metrics collector
        
        Args:
            name: Name of the component collecting metrics
        """
        self.name = name
        self._lock = asyncio.Lock()
    
    @abstractmethod
    async def record_success(self, duration: float, **kwargs: Any) -> None:
        """Record a successful call

        Args:
            duration: Duration of the call in seconds
            **kwargs: Additional pattern-specific metrics
        """
        pass

    @abstractmethod
    async def record_failure(self, duration: float, exception: Optional[Exception] = None, **kwargs: Any) -> None:
        """Record a failed call
        
        Args:
            duration: Duration of the call in seconds
            exception: Optional exception that caused the failure
            **kwargs: Additional pattern-specific metrics
        """
        pass
    
    @abstractmethod
    async def get_snapshot(self) -> MetricsSnapshot:
        """Get current metrics snapshot
        
        Returns:
            Immutable snapshot of current metrics
        """
        pass
    
    @abstractmethod
    async def reset(self) -> None:
        """Reset all metrics to initial state"""
        pass


class BasicMetrics(Metrics):
    """Basic implementation of metrics collection
    
    This implementation provides simple counters and averages
    without sliding windows or time-based aggregation.
    """
    
    def __init__(self, name: str):
        """Initialize basic metrics collector
        
        Args:
            name: Name of the component collecting metrics
        """
        super().__init__(name)
        self._total_calls = 0
        self._successful_calls = 0
        self._failed_calls = 0
        self._total_duration = 0.0
        self._start_time = time.time()
    
    async def record_success(self, duration: float, **kwargs: Any) -> None:
        """Record a successful call"""
        async with self._lock:
            self._total_calls += 1
            self._successful_calls += 1
            self._total_duration += duration

    async def record_failure(self, duration: float, exception: Optional[Exception] = None, **kwargs: Any) -> None:
        """Record a failed call"""
        async with self._lock:
            self._total_calls += 1
            self._failed_calls += 1
            self._total_duration += duration
    
    async def get_snapshot(self) -> MetricsSnapshot:
        """Get current metrics snapshot"""
        async with self._lock:
            return MetricsSnapshot(
                total_calls=self._total_calls,
                successful_calls=self._successful_calls,
                failed_calls=self._failed_calls,
                total_duration=self._total_duration
            )
    
    async def reset(self) -> None:
        """Reset all metrics to initial state"""
        async with self._lock:
            self._total_calls = 0
            self._successful_calls = 0
            self._failed_calls = 0
            self._total_duration = 0.0
            self._start_time = time.time()


@dataclass
class CallRecord:
    """Record of a single call for sliding window metrics
    
    Attributes:
        timestamp: When the call was made
        duration: How long the call took in seconds
        success: Whether the call was successful
        metadata: Additional call-specific data
    """
    timestamp: float
    duration: float
    success: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


class SlidingWindowMetrics(Metrics):
    """Metrics implementation with sliding window support
    
    This implementation maintains a sliding window of call records
    for more accurate recent metrics calculation.
    """
    
    def __init__(self, name: str, window_size: int = 1000, 
                 window_type: str = "COUNT_BASED"):
        """Initialize sliding window metrics
        
        Args:
            name: Name of the component collecting metrics
            window_size: Size of the sliding window
            window_type: Type of window ("COUNT_BASED" or "TIME_BASED")
        """
        super().__init__(name)
        self.window_size = window_size
        self.window_type = window_type
        self._calls: deque[CallRecord] = deque(maxlen=window_size if window_type == "COUNT_BASED" else None)
    
    async def record_success(self, duration: float, **kwargs: Any) -> None:
        """Record a successful call"""
        async with self._lock:
            record = CallRecord(
                timestamp=time.time(),
                duration=duration,
                success=True,
                metadata=kwargs
            )
            self._calls.append(record)
            await self._cleanup_old_records()

    async def record_failure(self, duration: float, exception: Optional[Exception] = None, **kwargs: Any) -> None:
        """Record a failed call"""
        async with self._lock:
            record = CallRecord(
                timestamp=time.time(),
                duration=duration,
                success=False,
                metadata={**kwargs, 'exception': str(exception) if exception else None}
            )
            self._calls.append(record)
            await self._cleanup_old_records()
    
    async def get_snapshot(self) -> MetricsSnapshot:
        """Get current metrics snapshot"""
        async with self._lock:
            if not self._calls:
                return MetricsSnapshot()
            
            total_calls = len(self._calls)
            successful_calls = sum(1 for call in self._calls if call.success)
            failed_calls = total_calls - successful_calls
            total_duration = sum(call.duration for call in self._calls)
            
            # Calculate additional metrics
            durations = [call.duration for call in self._calls]
            metrics = {
                'min_duration': min(durations),
                'max_duration': max(durations),
                'median_duration': statistics.median(durations),
                'p95_duration': statistics.quantiles(durations, n=20)[18] if len(durations) >= 20 else max(durations),
                'p99_duration': statistics.quantiles(durations, n=100)[98] if len(durations) >= 100 else max(durations),
            }
            
            return MetricsSnapshot(
                total_calls=total_calls,
                successful_calls=successful_calls,
                failed_calls=failed_calls,
                total_duration=total_duration,
                metrics=metrics
            )
    
    async def reset(self) -> None:
        """Reset all metrics to initial state"""
        async with self._lock:
            self._calls.clear()
    
    async def _cleanup_old_records(self) -> None:
        """Remove old records for TIME_BASED windows"""
        if self.window_type == "TIME_BASED":
            cutoff_time = time.time() - self.window_size
            while self._calls and self._calls[0].timestamp < cutoff_time:
                self._calls.popleft()


class MetricsRegistry:
    """Central registry for all metrics collectors
    
    Provides a way to access and manage metrics from all
    resilience patterns in one place.
    """
    
    def __init__(self) -> None:
        """Initialize metrics registry"""
        self._metrics: Dict[str, Metrics] = {}
        self._lock = asyncio.Lock()
    
    async def register(self, name: str, metrics: Metrics) -> None:
        """Register a metrics collector
        
        Args:
            name: Unique name for the metrics
            metrics: Metrics collector instance
        """
        async with self._lock:
            self._metrics[name] = metrics
    
    async def unregister(self, name: str) -> None:
        """Unregister a metrics collector
        
        Args:
            name: Name of the metrics to remove
        """
        async with self._lock:
            self._metrics.pop(name, None)
    
    async def get(self, name: str) -> Optional[Metrics]:
        """Get a metrics collector by name
        
        Args:
            name: Name of the metrics
            
        Returns:
            Metrics instance or None if not found
        """
        async with self._lock:
            return self._metrics.get(name)
    
    async def get_all_snapshots(self) -> Dict[str, MetricsSnapshot]:
        """Get snapshots from all registered metrics
        
        Returns:
            Dictionary mapping names to snapshots
        """
        async with self._lock:
            snapshots = {}
            for name, metrics in self._metrics.items():
                snapshots[name] = await metrics.get_snapshot()
            return snapshots
    
    async def reset_all(self) -> None:
        """Reset all registered metrics"""
        async with self._lock:
            for metrics in self._metrics.values():
                await metrics.reset()