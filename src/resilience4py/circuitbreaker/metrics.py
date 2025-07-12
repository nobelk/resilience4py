"""Circuit Breaker metrics collection module.

This module implements sliding window metrics for tracking call outcomes,
durations, and calculating failure/slow call rates.
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Deque, List, Optional, Union
import asyncio
import time


@dataclass
class CallOutcome:
    """Represents the outcome of a single call.
    
    Attributes:
        timestamp: When the call was made.
        duration_ms: Duration of the call in milliseconds.
        success: Whether the call succeeded.
        slow: Whether the call was considered slow.
    """
    timestamp: float
    duration_ms: float
    success: bool
    slow: bool


@dataclass
class Snapshot:
    """Snapshot of current metrics.
    
    Attributes:
        total_calls: Total number of calls in the window.
        failed_calls: Number of failed calls.
        slow_calls: Number of slow calls.
        failure_rate: Current failure rate percentage.
        slow_call_rate: Current slow call rate percentage.
        average_duration: Average duration of all calls in milliseconds.
    """
    total_calls: int
    failed_calls: int
    slow_calls: int
    failure_rate: float
    slow_call_rate: float
    average_duration: float
    
    @property
    def successful_calls(self) -> int:
        """Number of successful calls."""
        return self.total_calls - self.failed_calls


class SlidingWindowMetrics:
    """Thread-safe sliding window for metrics collection.
    
    This class implements both count-based and time-based sliding windows
    for tracking circuit breaker metrics.
    """
    
    def __init__(self, window_size: int, window_type: str, 
                 slow_call_duration_threshold_ms: float):
        """Initialize sliding window metrics.
        
        Args:
            window_size: Size of the sliding window. For count-based, this is
                the number of calls. For time-based, this is seconds.
            window_type: Type of window - "COUNT_BASED" or "TIME_BASED".
            slow_call_duration_threshold_ms: Threshold in milliseconds to
                consider a call as slow.
        """
        self.window_size = window_size
        self.window_type = window_type
        self.slow_call_duration_threshold_ms = slow_call_duration_threshold_ms
        self._lock = asyncio.Lock()
        
        if window_type == "COUNT_BASED":
            self._calls: Deque[CallOutcome] = deque(maxlen=window_size)
        else:  # TIME_BASED
            self._calls: Deque[CallOutcome] = deque()
    
    async def record_success(self, duration_ms: float) -> None:
        """Record a successful call.
        
        Args:
            duration_ms: Duration of the call in milliseconds.
        """
        outcome = CallOutcome(
            timestamp=time.time(),
            duration_ms=duration_ms,
            success=True,
            slow=duration_ms >= self.slow_call_duration_threshold_ms
        )
        
        async with self._lock:
            await self._add_call(outcome)
    
    async def record_failure(self, duration_ms: float) -> None:
        """Record a failed call.
        
        Args:
            duration_ms: Duration of the call in milliseconds.
        """
        outcome = CallOutcome(
            timestamp=time.time(),
            duration_ms=duration_ms,
            success=False,
            slow=duration_ms >= self.slow_call_duration_threshold_ms
        )
        
        async with self._lock:
            await self._add_call(outcome)
    
    async def get_snapshot(self) -> Snapshot:
        """Get a snapshot of current metrics.
        
        Returns:
            Snapshot containing current metrics.
        """
        async with self._lock:
            # Clean up old entries for time-based window
            if self.window_type == "TIME_BASED":
                await self._cleanup_old_entries()
            
            total_calls = len(self._calls)
            if total_calls == 0:
                return Snapshot(
                    total_calls=0,
                    failed_calls=0,
                    slow_calls=0,
                    failure_rate=0.0,
                    slow_call_rate=0.0,
                    average_duration=0.0
                )
            
            failed_calls = sum(1 for call in self._calls if not call.success)
            slow_calls = sum(1 for call in self._calls if call.slow)
            total_duration = sum(call.duration_ms for call in self._calls)
            
            failure_rate = (failed_calls / total_calls) * 100
            slow_call_rate = (slow_calls / total_calls) * 100
            average_duration = total_duration / total_calls
            
            return Snapshot(
                total_calls=total_calls,
                failed_calls=failed_calls,
                slow_calls=slow_calls,
                failure_rate=failure_rate,
                slow_call_rate=slow_call_rate,
                average_duration=average_duration
            )
    
    async def reset(self) -> None:
        """Reset all metrics."""
        async with self._lock:
            self._calls.clear()
    
    async def _add_call(self, outcome: CallOutcome) -> None:
        """Add a call outcome to the window.
        
        Args:
            outcome: The call outcome to add.
        """
        if self.window_type == "TIME_BASED":
            await self._cleanup_old_entries()
        
        self._calls.append(outcome)
    
    async def _cleanup_old_entries(self) -> None:
        """Remove entries older than the window size for time-based windows."""
        if self.window_type != "TIME_BASED":
            return
        
        current_time = time.time()
        window_start = current_time - self.window_size
        
        # Remove calls older than the window
        while self._calls and self._calls[0].timestamp < window_start:
            self._calls.popleft()


class HalfOpenMetrics:
    """Specialized metrics for half-open state.
    
    This class tracks metrics specifically for the half-open state,
    where only a limited number of calls are permitted.
    """
    
    def __init__(self, permitted_calls: int, slow_call_duration_threshold_ms: float):
        """Initialize half-open metrics.
        
        Args:
            permitted_calls: Number of calls permitted in half-open state.
            slow_call_duration_threshold_ms: Threshold to consider a call slow.
        """
        self.permitted_calls = permitted_calls
        self.slow_call_duration_threshold_ms = slow_call_duration_threshold_ms
        self._calls: List[CallOutcome] = []
        self._lock = asyncio.Lock()
    
    async def record_success(self, duration_ms: float) -> None:
        """Record a successful call."""
        outcome = CallOutcome(
            timestamp=time.time(),
            duration_ms=duration_ms,
            success=True,
            slow=duration_ms >= self.slow_call_duration_threshold_ms
        )
        
        async with self._lock:
            if len(self._calls) < self.permitted_calls:
                self._calls.append(outcome)
    
    async def record_failure(self, duration_ms: float) -> None:
        """Record a failed call."""
        outcome = CallOutcome(
            timestamp=time.time(),
            duration_ms=duration_ms,
            success=False,
            slow=duration_ms >= self.slow_call_duration_threshold_ms
        )
        
        async with self._lock:
            if len(self._calls) < self.permitted_calls:
                self._calls.append(outcome)
    
    async def get_snapshot(self) -> Snapshot:
        """Get current metrics snapshot."""
        async with self._lock:
            total_calls = len(self._calls)
            if total_calls == 0:
                return Snapshot(
                    total_calls=0,
                    failed_calls=0,
                    slow_calls=0,
                    failure_rate=0.0,
                    slow_call_rate=0.0,
                    average_duration=0.0
                )
            
            failed_calls = sum(1 for call in self._calls if not call.success)
            slow_calls = sum(1 for call in self._calls if call.slow)
            total_duration = sum(call.duration_ms for call in self._calls)
            
            failure_rate = (failed_calls / total_calls) * 100
            slow_call_rate = (slow_calls / total_calls) * 100
            average_duration = total_duration / total_calls
            
            return Snapshot(
                total_calls=total_calls,
                failed_calls=failed_calls,
                slow_calls=slow_calls,
                failure_rate=failure_rate,
                slow_call_rate=slow_call_rate,
                average_duration=average_duration
            )
    
    async def is_complete(self) -> bool:
        """Check if all permitted calls have been made."""
        async with self._lock:
            return len(self._calls) >= self.permitted_calls
    
    async def reset(self) -> None:
        """Reset metrics."""
        async with self._lock:
            self._calls.clear()