"""Circuit Breaker pattern implementation.

This module provides the main CircuitBreaker class that implements the
circuit breaker pattern for fault tolerance in distributed systems.
"""

import asyncio
import time
from functools import partial, wraps
from typing import Any, Callable, Optional, TypeVar, Union, Awaitable, Dict, List, cast
from weakref import WeakSet

from .config import CircuitBreakerConfig, SlidingWindowType
from .events import (
    CircuitBreakerState,
    CircuitBreakerEvent,
    CircuitBreakerOnSuccessEvent,
    CircuitBreakerOnErrorEvent,
    CircuitBreakerOnCallNotPermittedEvent,
    CircuitBreakerOnStateTransitionEvent,
    CircuitBreakerOnResetEvent,
    CircuitBreakerOnIgnoredErrorEvent,
    CircuitBreakerOnSlowCallRateExceededEvent,
    CircuitBreakerOnFailureRateExceededEvent,
    CircuitBreakerOnManualStateTransitionEvent
)
from .metrics import SlidingWindowMetrics
from .states import (
    State,
    ClosedState,
    OpenState,
    HalfOpenState,
    DisabledState,
    ForcedOpenState,
    MetricsOnlyState
)


F = TypeVar('F', bound=Callable[..., Any])


class CallNotPermittedException(Exception):
    """Exception raised when a call is not permitted by the circuit breaker."""
    pass


class CircuitBreaker:
    """Circuit Breaker pattern implementation.
    
    The circuit breaker monitors function calls and prevents calls to a
    function that is likely to fail, allowing the system to recover.
    
    Example:
        >>> cb = CircuitBreaker("my-service", CircuitBreakerConfig(
        ...     failure_rate_threshold=50.0,
        ...     sliding_window_size=100
        ... ))
        >>> 
        >>> @cb
        >>> async def call_external_service():
        ...     # Make external call
        ...     pass
    """
    
    # Class-level registry to track all circuit breaker instances
    _instances: WeakSet['CircuitBreaker'] = WeakSet()
    _registry: Dict[str, 'CircuitBreaker'] = {}
    _registry_lock = asyncio.Lock()
    
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        """Initialize circuit breaker.
        
        Args:
            name: Unique name for this circuit breaker.
            config: Configuration for the circuit breaker. If not provided,
                default configuration is used.
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        # Initialize metrics
        self.metrics = SlidingWindowMetrics(
            window_size=self.config.sliding_window_size,
            window_type=self.config.sliding_window_type.value,
            slow_call_duration_threshold_ms=self.config.slow_call_duration_threshold.total_seconds() * 1000
        )
        
        # Initialize state
        self._state_lock = asyncio.Lock()
        self._state: State = ClosedState(self)
        
        # Event listeners
        self._event_listeners: Dict[type, List[Callable]] = {}
        
        # Add to instances
        CircuitBreaker._instances.add(self)
    
    @classmethod
    async def get_or_create(cls, name: str, config: Optional[CircuitBreakerConfig] = None) -> 'CircuitBreaker':
        """Get existing circuit breaker or create new one.
        
        Args:
            name: Name of the circuit breaker.
            config: Configuration to use if creating new instance.
            
        Returns:
            Circuit breaker instance.
        """
        async with cls._registry_lock:
            if name in cls._registry:
                return cls._registry[name]
            
            cb = cls(name, config)
            cls._registry[name] = cb
            return cb
    
    @property
    def state(self) -> State:
        """Get current state."""
        return self._state
    
    @property
    def state_name(self) -> CircuitBreakerState:
        """Get current state name."""
        return self._state.state_type
    
    def __call__(self, func: F) -> F:
        """Decorate a function with circuit breaker protection.
        
        Args:
            func: Function to protect.
            
        Returns:
            Decorated function.
        """
        if asyncio.iscoroutinefunction(func):
            return self._decorate_async(func)
        else:
            return self._decorate_sync(func)
    
    def _decorate_sync(self, func: F) -> F:
        """Decorate synchronous function."""
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Run async implementation in sync context
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop, create new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(
                        self._execute_async(func, *args, **kwargs)
                    )
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
            else:
                # Already in async context
                return asyncio.run_coroutine_threadsafe(
                    self._execute_async(func, *args, **kwargs),
                    loop
                ).result()

        return cast(F, wrapper)

    def _decorate_async(self, func: F) -> F:
        """Decorate asynchronous function."""
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await self._execute_async(func, *args, **kwargs)

        return cast(F, wrapper)

    async def _execute_async(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.
            
        Returns:
            Result of the function call.
            
        Raises:
            CallNotPermittedException: If the call is not permitted.
            Exception: Any exception raised by the function.
        """
        # Try to acquire permission
        if not await self._state.acquire_permission():
            await self._publish_event(CircuitBreakerOnCallNotPermittedEvent.create(self.name))
            raise CallNotPermittedException(
                f"CircuitBreaker '{self.name}' is {self.state_name.value}"
            )
        
        # Execute the function and measure duration. Use monotonic so the duration
        # cannot go negative if wall-clock jumps mid-call.
        start_time = time.monotonic()
        try:
            # Execute function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                # Run sync function in executor to avoid blocking.
                # run_in_executor doesn't accept kwargs, so bind them with partial.
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, partial(func, *args, **kwargs)
                )
            
            # Record success
            duration_ms = (time.monotonic() - start_time) * 1000
            await self._state.on_success(duration_ms)
            await self._publish_event(
                CircuitBreakerOnSuccessEvent.create(self.name, duration_ms)
            )
            
            return result
            
        except Exception as e:
            # Record error
            duration_ms = (time.monotonic() - start_time) * 1000
            
            # Check if we should ignore this exception
            if not self.config.should_record_exception(e):
                await self._publish_event(
                    CircuitBreakerOnIgnoredErrorEvent.create(self.name, e)
                )
            
            await self._state.on_error(duration_ms, e)
            await self._publish_event(
                CircuitBreakerOnErrorEvent.create(self.name, duration_ms, e)
            )
            
            raise
    
    async def transition_to_state(self, new_state: CircuitBreakerState) -> None:
        """Transition to a new state.
        
        Args:
            new_state: State to transition to.
        """
        async with self._state_lock:
            old_state = self._state.state_type
            
            if old_state == new_state:
                return
            
            # Create new state instance
            if new_state == CircuitBreakerState.CLOSED:
                self._state = ClosedState(self)
            elif new_state == CircuitBreakerState.OPEN:
                self._state = OpenState(self)
            elif new_state == CircuitBreakerState.HALF_OPEN:
                self._state = HalfOpenState(self)
            elif new_state == CircuitBreakerState.DISABLED:
                self._state = DisabledState(self)
            elif new_state == CircuitBreakerState.FORCED_OPEN:
                self._state = ForcedOpenState(self)
            elif new_state == CircuitBreakerState.METRICS_ONLY:
                self._state = MetricsOnlyState(self)
            else:
                raise ValueError(f"Unknown state: {new_state}")
            
            # Publish transition event
            await self._publish_event(
                CircuitBreakerOnStateTransitionEvent.create(self.name, old_state, new_state)
            )
    
    async def reset(self) -> None:
        """Reset the circuit breaker to closed state and clear metrics."""
        async with self._state_lock:
            await self.metrics.reset()
            self._state = ClosedState(self)
            await self._publish_event(CircuitBreakerOnResetEvent.create(self.name))
    
    async def disable(self) -> None:
        """Disable the circuit breaker."""
        await self.transition_to_state(CircuitBreakerState.DISABLED)
    
    async def force_open(self) -> None:
        """Force the circuit breaker to open state."""
        await self.transition_to_state(CircuitBreakerState.FORCED_OPEN)
    
    async def close(self) -> None:
        """Close the circuit breaker."""
        await self.transition_to_state(CircuitBreakerState.CLOSED)
    
    async def transition_to_metrics_only(self) -> None:
        """Transition to metrics only mode."""
        await self.transition_to_state(CircuitBreakerState.METRICS_ONLY)
    
    def on_event(self, event_type: type, listener: Callable[[CircuitBreakerEvent], None]) -> None:
        """Register an event listener.
        
        Args:
            event_type: Type of event to listen for.
            listener: Function to call when event occurs.
        """
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append(listener)
    
    def remove_event_listener(self, event_type: type, listener: Callable[[CircuitBreakerEvent], None]) -> None:
        """Remove an event listener.
        
        Args:
            event_type: Type of event.
            listener: Listener to remove.
        """
        if event_type in self._event_listeners:
            self._event_listeners[event_type].remove(listener)
    
    async def _publish_event(self, event: CircuitBreakerEvent) -> None:
        """Publish an event to all listeners.
        
        Args:
            event: Event to publish.
        """
        listeners = self._event_listeners.get(type(event), [])
        for listener in listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(event)
                else:
                    listener(event)
            except Exception:
                # Ignore exceptions in event listeners
                pass
    
    async def publish_failure_rate_exceeded(self, failure_rate: float) -> None:
        """Publish failure rate exceeded event."""
        await self._publish_event(
            CircuitBreakerOnFailureRateExceededEvent.create(self.name, failure_rate)
        )
    
    async def publish_slow_call_rate_exceeded(self, slow_call_rate: float) -> None:
        """Publish slow call rate exceeded event."""
        await self._publish_event(
            CircuitBreakerOnSlowCallRateExceededEvent.create(self.name, slow_call_rate)
        )
    
    def decorate(self, func: F) -> F:
        """Alternative way to decorate a function.
        
        Args:
            func: Function to decorate.
            
        Returns:
            Decorated function.
        """
        return self(func)
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics.
        
        Returns:
            Dictionary containing current metrics.
        """
        snapshot = await self.metrics.get_snapshot()
        return {
            'name': self.name,
            'state': self.state_name.value,
            'total_calls': snapshot.total_calls,
            'successful_calls': snapshot.successful_calls,
            'failed_calls': snapshot.failed_calls,
            'slow_calls': snapshot.slow_calls,
            'failure_rate': snapshot.failure_rate,
            'slow_call_rate': snapshot.slow_call_rate,
            'average_duration_ms': snapshot.average_duration
        }