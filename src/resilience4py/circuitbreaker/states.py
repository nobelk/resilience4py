"""Circuit Breaker state machine implementation.

This module implements the state pattern for the Circuit Breaker,
defining all possible states and their transitions.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional
import asyncio
import time

from .events import CircuitBreakerState
from .metrics import HalfOpenMetrics

if TYPE_CHECKING:
    from .circuit_breaker import CircuitBreaker


class State(ABC):
    """Abstract base class for circuit breaker states."""
    
    def __init__(self, circuit_breaker: 'CircuitBreaker', state_type: CircuitBreakerState):
        """Initialize state.
        
        Args:
            circuit_breaker: The circuit breaker instance.
            state_type: Type of this state.
        """
        self.circuit_breaker = circuit_breaker
        self.state_type = state_type
    
    @abstractmethod
    async def acquire_permission(self) -> bool:
        """Try to acquire permission for execution.
        
        Returns:
            True if the call is permitted, False otherwise.
        """
        pass
    
    @abstractmethod
    async def on_success(self, duration_ms: float) -> None:
        """Handle successful execution.
        
        Args:
            duration_ms: Duration of the successful call in milliseconds.
        """
        pass
    
    @abstractmethod
    async def on_error(self, duration_ms: float, exception: Exception) -> None:
        """Handle failed execution.
        
        Args:
            duration_ms: Duration of the failed call in milliseconds.
            exception: The exception that caused the failure.
        """
        pass
    
    async def should_transition(self) -> Optional[CircuitBreakerState]:
        """Check if state should transition.
        
        Returns:
            New state to transition to, or None if no transition needed.
        """
        return None


class ClosedState(State):
    """Circuit breaker closed state - normal operation.
    
    In this state, all calls are permitted and metrics are collected.
    The circuit breaker transitions to open state when failure or slow
    call thresholds are exceeded.
    """
    
    def __init__(self, circuit_breaker: 'CircuitBreaker'):
        super().__init__(circuit_breaker, CircuitBreakerState.CLOSED)
    
    async def acquire_permission(self) -> bool:
        """Always permit calls in closed state."""
        return True
    
    async def on_success(self, duration_ms: float) -> None:
        """Record success and check thresholds."""
        await self.circuit_breaker.metrics.record_success(duration_ms)
        await self._check_thresholds()
    
    async def on_error(self, duration_ms: float, exception: Exception) -> None:
        """Record failure and check thresholds."""
        # Check if we should record this exception
        if self.circuit_breaker.config.should_record_exception(exception):
            await self.circuit_breaker.metrics.record_failure(duration_ms)
            await self._check_thresholds()
        else:
            # Still record as success for metrics purposes
            await self.circuit_breaker.metrics.record_success(duration_ms)
    
    async def _check_thresholds(self) -> None:
        """Check if thresholds are exceeded and transition to open if needed."""
        metrics = await self.circuit_breaker.metrics.get_snapshot()
        
        # Only check thresholds if we have minimum number of calls
        if metrics.total_calls < self.circuit_breaker.config.minimum_number_of_calls:
            return
        
        # Check failure rate threshold
        if metrics.failure_rate >= self.circuit_breaker.config.failure_rate_threshold:
            await self.circuit_breaker.transition_to_state(CircuitBreakerState.OPEN)
            await self.circuit_breaker.publish_failure_rate_exceeded(metrics.failure_rate)
            return
        
        # Check slow call rate threshold
        if metrics.slow_call_rate >= self.circuit_breaker.config.slow_call_rate_threshold:
            await self.circuit_breaker.transition_to_state(CircuitBreakerState.OPEN)
            await self.circuit_breaker.publish_slow_call_rate_exceeded(metrics.slow_call_rate)


class OpenState(State):
    """Circuit breaker open state - calls are rejected.
    
    In this state, calls are not permitted. After a wait duration,
    the circuit breaker can transition to half-open state.
    """
    
    def __init__(self, circuit_breaker: 'CircuitBreaker'):
        super().__init__(circuit_breaker, CircuitBreakerState.OPEN)
        # Monotonic clock — wall-clock jumps from NTP/VM suspends would otherwise
        # corrupt half-open transition timing.
        self.opened_at = time.monotonic()
    
    async def acquire_permission(self) -> bool:
        """Reject calls but check if we should transition to half-open."""
        # Check if we should transition to half-open
        if self.circuit_breaker.config.automatic_transition_from_open_to_half_open:
            elapsed = time.monotonic() - self.opened_at
            wait_seconds = self.circuit_breaker.config.wait_duration_in_open_state.total_seconds()
            
            if elapsed >= wait_seconds:
                await self.circuit_breaker.transition_to_state(CircuitBreakerState.HALF_OPEN)
                # Try to acquire permission in the new state
                return await self.circuit_breaker.state.acquire_permission()
        
        return False
    
    async def on_success(self, duration_ms: float) -> None:
        """Should not be called in open state."""
        raise RuntimeError("on_success called in open state")
    
    async def on_error(self, duration_ms: float, exception: Exception) -> None:
        """Should not be called in open state."""
        raise RuntimeError("on_error called in open state")


class HalfOpenState(State):
    """Circuit breaker half-open state - limited calls permitted.
    
    In this state, a limited number of calls are permitted to test
    if the underlying service has recovered. Based on the outcomes,
    the circuit breaker transitions back to closed or open state.
    """
    
    def __init__(self, circuit_breaker: 'CircuitBreaker'):
        super().__init__(circuit_breaker, CircuitBreakerState.HALF_OPEN)
        self.metrics = HalfOpenMetrics(
            permitted_calls=circuit_breaker.config.permitted_calls_in_half_open,
            slow_call_duration_threshold_ms=circuit_breaker.config.slow_call_duration_threshold.total_seconds() * 1000
        )
        self.permits_used = 0
        self.entered_at = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire_permission(self) -> bool:
        """Permit limited number of calls."""
        async with self._lock:
            # Check max wait duration if configured
            max_wait = self.circuit_breaker.config.max_wait_duration_in_half_open.total_seconds()
            if max_wait > 0:
                elapsed = time.monotonic() - self.entered_at
                if elapsed >= max_wait:
                    # Timeout - transition back to open
                    await self.circuit_breaker.transition_to_state(CircuitBreakerState.OPEN)
                    return False
            
            if self.permits_used < self.circuit_breaker.config.permitted_calls_in_half_open:
                self.permits_used += 1
                return True
            
            return False
    
    async def on_success(self, duration_ms: float) -> None:
        """Record success and check if we should transition."""
        await self.metrics.record_success(duration_ms)
        await self._check_transition()
    
    async def on_error(self, duration_ms: float, exception: Exception) -> None:
        """Record failure and check if we should transition."""
        if self.circuit_breaker.config.should_record_exception(exception):
            await self.metrics.record_failure(duration_ms)
            await self._check_transition()
        else:
            await self.metrics.record_success(duration_ms)
            await self._check_transition()
    
    async def _check_transition(self) -> None:
        """Check if we should transition based on collected metrics."""
        if not await self.metrics.is_complete():
            return
        
        snapshot = await self.metrics.get_snapshot()
        
        # Check failure rate
        if snapshot.failure_rate >= self.circuit_breaker.config.failure_rate_threshold:
            await self.circuit_breaker.transition_to_state(CircuitBreakerState.OPEN)
            return
        
        # Check slow call rate
        if snapshot.slow_call_rate >= self.circuit_breaker.config.slow_call_rate_threshold:
            await self.circuit_breaker.transition_to_state(CircuitBreakerState.OPEN)
            return
        
        # All calls successful - transition to closed
        await self.circuit_breaker.transition_to_state(CircuitBreakerState.CLOSED)


class DisabledState(State):
    """Circuit breaker disabled state - all calls permitted, no metrics.
    
    In this state, the circuit breaker is effectively disabled.
    All calls are permitted and no metrics are collected.
    """
    
    def __init__(self, circuit_breaker: 'CircuitBreaker'):
        super().__init__(circuit_breaker, CircuitBreakerState.DISABLED)
    
    async def acquire_permission(self) -> bool:
        """Always permit calls when disabled."""
        return True
    
    async def on_success(self, duration_ms: float) -> None:
        """No-op when disabled."""
        pass
    
    async def on_error(self, duration_ms: float, exception: Exception) -> None:
        """No-op when disabled."""
        pass


class ForcedOpenState(State):
    """Circuit breaker forced open state - all calls rejected.
    
    In this state, the circuit breaker is manually forced open.
    No automatic transitions occur.
    """
    
    def __init__(self, circuit_breaker: 'CircuitBreaker'):
        super().__init__(circuit_breaker, CircuitBreakerState.FORCED_OPEN)
    
    async def acquire_permission(self) -> bool:
        """Always reject calls when forced open."""
        return False
    
    async def on_success(self, duration_ms: float) -> None:
        """Should not be called in forced open state."""
        raise RuntimeError("on_success called in forced open state")
    
    async def on_error(self, duration_ms: float, exception: Exception) -> None:
        """Should not be called in forced open state."""
        raise RuntimeError("on_error called in forced open state")


class MetricsOnlyState(State):
    """Circuit breaker metrics only state - all calls permitted, only collect metrics.
    
    In this state, all calls are permitted and metrics are collected,
    but no state transitions occur based on the metrics.
    """
    
    def __init__(self, circuit_breaker: 'CircuitBreaker'):
        super().__init__(circuit_breaker, CircuitBreakerState.METRICS_ONLY)
    
    async def acquire_permission(self) -> bool:
        """Always permit calls in metrics only state."""
        return True
    
    async def on_success(self, duration_ms: float) -> None:
        """Record success metrics only."""
        await self.circuit_breaker.metrics.record_success(duration_ms)
    
    async def on_error(self, duration_ms: float, exception: Exception) -> None:
        """Record failure metrics only."""
        if self.circuit_breaker.config.should_record_exception(exception):
            await self.circuit_breaker.metrics.record_failure(duration_ms)
        else:
            await self.circuit_breaker.metrics.record_success(duration_ms)