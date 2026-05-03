"""
Atomic Rate Limiter implementation.

State transitions are serialized through an ``asyncio.Lock`` (see
``_state_lock``). The "atomic" naming refers to each reservation being a
single all-or-nothing operation against the limiter state, not to lock-free
concurrency.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Callable, Any, TypeVar, Union
from functools import wraps

from .config import RateLimiterConfig
from .events import RateLimiterOnSuccessEvent, RateLimiterOnFailureEvent


# Custom exception for rate limiter
class RequestNotPermitted(Exception):
    """Exception raised when a request is not permitted by the rate limiter."""
    pass


@dataclass
class RateLimiterState:
    """
    Immutable state for atomic rate limiter.
    
    Attributes:
        active_permissions: Number of available permissions in the current cycle.
        active_cycle: The current refresh cycle number.
        nanoseconds_to_wait: Time in nanoseconds to wait for the next permission.
    """
    active_permissions: int
    active_cycle: int
    nanoseconds_to_wait: int


F = TypeVar('F', bound=Callable[..., Any])


class AtomicRateLimiter:
    """
    Rate limiter whose state transitions are atomic under ``asyncio.Lock``.

    Each call to :meth:`_reserve_permission` takes the state lock, computes
    the cycle position, and either grants a permit or returns the wait
    duration — all as one indivisible operation. Permission checks are
    *not* lock-free; the lock is acquired on every reservation.
    """
    
    def __init__(self, name: str, config: RateLimiterConfig):
        """
        Initialize the atomic rate limiter.
        
        Args:
            name: The name of the rate limiter.
            config: The configuration for the rate limiter.
        """
        self.name = name
        self.config = config
        self._state_lock = asyncio.Lock()
        self._state = RateLimiterState(
            active_permissions=config.limit_for_period,
            active_cycle=0,
            nanoseconds_to_wait=0
        )
        self._event_publishers: list = []
        # Typed listeners keyed by event class — populated via add_event_listener.
        self._event_listeners: dict[type, list[Callable]] = {}
    
    def __call__(self, func: F) -> F:
        """
        Decorate a function with rate limiting.
        
        Args:
            func: The function to decorate.
            
        Returns:
            The decorated function.
        """
        if asyncio.iscoroutinefunction(func):
            return self._decorate_async(func)
        else:
            return self._decorate_sync(func)
    
    def _decorate_sync(self, func: F) -> F:
        """
        Decorate a synchronous function.
        
        Args:
            func: The synchronous function to decorate.
            
        Returns:
            The decorated function.
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Run async implementation in sync context
            loop = asyncio.new_event_loop()
            try:
                coro = self._execute_async(func, *args, **kwargs)
                return loop.run_until_complete(coro)
            finally:
                loop.close()
        return wrapper
    
    def _decorate_async(self, func: F) -> F:
        """
        Decorate an asynchronous function.
        
        Args:
            func: The asynchronous function to decorate.
            
        Returns:
            The decorated function.
        """
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await self._execute_async(func, *args, **kwargs)
        return wrapper
    
    async def _execute_async(self, func: Callable, *args, **kwargs):
        """
        Execute function with rate limiting.
        
        Args:
            func: The function to execute.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.
            
        Returns:
            The result of the function execution.
            
        Raises:
            RequestNotPermitted: If the rate limit is exceeded and timeout is reached.
        """
        wait_time = await self._reserve_permission()
        
        if wait_time < 0:
            # Permission denied due to timeout
            await self._publish_event(RateLimiterOnFailureEvent(self.name, abs(wait_time)))
            raise RequestNotPermitted(f"Rate limiter '{self.name}' denied permission")
        
        if wait_time > 0:
            # Wait for the required time
            await asyncio.sleep(wait_time / 1_000_000_000)  # Convert nanos to seconds
        
        # Permission granted
        await self._publish_event(RateLimiterOnSuccessEvent(self.name))
        
        # Execute function
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    
    async def _reserve_permission(self) -> int:
        """
        Reserve permission and return wait time in nanoseconds.
        
        Returns:
            The wait time in nanoseconds:
            - 0 if permission is immediately available
            - Positive value if need to wait
            - Negative value if timeout would be exceeded
        """
        async with self._state_lock:
            # Monotonic clock — wall-clock jumps would corrupt cycle accounting.
            current_nanos = time.monotonic_ns()
            cycle_length_nanos = int(self.config.limit_refresh_period.total_seconds() * 1_000_000_000)
            current_cycle = current_nanos // cycle_length_nanos
            
            # Refresh if new cycle
            if current_cycle != self._state.active_cycle:
                cycles_passed = current_cycle - self._state.active_cycle
                new_permissions = min(
                    cycles_passed * self.config.limit_for_period,
                    self.config.limit_for_period
                )
                self._state = RateLimiterState(
                    active_permissions=int(new_permissions),
                    active_cycle=current_cycle,
                    nanoseconds_to_wait=0
                )
            
            # Try to acquire permission
            if self._state.active_permissions > 0:
                self._state = RateLimiterState(
                    active_permissions=self._state.active_permissions - 1,
                    active_cycle=self._state.active_cycle,
                    nanoseconds_to_wait=0
                )
                return 0
            else:
                # Calculate wait time until next cycle
                next_cycle = self._state.active_cycle + 1
                next_cycle_start_nanos = next_cycle * cycle_length_nanos
                nanoseconds_to_wait = next_cycle_start_nanos - current_nanos
                
                # Check timeout
                timeout_nanos = int(self.config.timeout_duration.total_seconds() * 1_000_000_000)
                if nanoseconds_to_wait > timeout_nanos:
                    return -nanoseconds_to_wait
                
                return nanoseconds_to_wait
    
    async def _publish_event(self, event: Union[RateLimiterOnSuccessEvent, RateLimiterOnFailureEvent]):
        """
        Publish an event to all registered publishers and typed listeners.

        Args:
            event: The event to publish.
        """
        for publisher in self._event_publishers:
            try:
                await publisher.publish(event)
            except Exception:
                # Listener failures must not break rate limiting; log via warnings
                # so consumer bugs are visible without crashing the call path.
                import logging
                logging.getLogger(__name__).warning(
                    "Event publisher %r failed for %s", publisher, type(event).__name__,
                    exc_info=True,
                )

        # Dispatch to typed listeners (matches by exact event type).
        for listener in list(self._event_listeners.get(type(event), ())):
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(event)
                else:
                    listener(event)
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    "Event listener %r failed for %s", listener, type(event).__name__,
                    exc_info=True,
                )

    def add_event_publisher(self, publisher):
        """
        Add an event publisher.

        Args:
            publisher: The event publisher to add.
        """
        self._event_publishers.append(publisher)

    def remove_event_publisher(self, publisher):
        """
        Remove an event publisher.

        Args:
            publisher: The event publisher to remove.
        """
        if publisher in self._event_publishers:
            self._event_publishers.remove(publisher)

    def add_event_listener(self, event_type: type, listener: Callable) -> None:
        """Register a listener for a specific event type.

        Args:
            event_type: The event class to listen for.
            listener: Sync or async callable invoked with the event.
        """
        self._event_listeners.setdefault(event_type, []).append(listener)

    def remove_event_listener(self, event_type: type, listener: Callable) -> bool:
        """Remove a previously registered listener.

        Returns:
            True if the listener was found and removed, False otherwise.
        """
        listeners = self._event_listeners.get(event_type)
        if listeners and listener in listeners:
            listeners.remove(listener)
            if not listeners:
                del self._event_listeners[event_type]
            return True
        return False
    
    async def get_metrics(self) -> dict:
        """
        Get current metrics for the rate limiter.
        
        Returns:
            A dictionary containing current metrics.
        """
        async with self._state_lock:
            return {
                "name": self.name,
                "available_permissions": self._state.active_permissions,
                "limit_for_period": self.config.limit_for_period,
                "current_cycle": self._state.active_cycle,
            }
    
    async def reset(self):
        """Reset the rate limiter to its initial state."""
        async with self._state_lock:
            self._state = RateLimiterState(
                active_permissions=self.config.limit_for_period,
                active_cycle=0,
                nanoseconds_to_wait=0
            )