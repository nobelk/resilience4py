"""
Semaphore-based bulkhead implementation using asyncio.Semaphore.
"""

from typing import Callable, Any, Optional
import asyncio
from datetime import datetime
from functools import partial

from .bulkhead import Bulkhead, BulkheadFullException
from .config import BulkheadConfig
from .events import (
    BulkheadOnCallPermittedEvent,
    BulkheadOnCallRejectedEvent,
    BulkheadOnCallFinishedEvent,
)
from ..core.events import Event


class SemaphoreBulkhead(Bulkhead):
    """
    Bulkhead implementation using asyncio.Semaphore.
    
    This implementation uses an asyncio Semaphore to limit concurrent
    access to a resource. It's suitable for async workloads and provides
    non-blocking behavior.
    """
    
    def __init__(self, name: str, config: BulkheadConfig):
        """
        Initialize semaphore bulkhead.

        Args:
            name: Name of the bulkhead instance
            config: Bulkhead configuration
        """
        super().__init__(name, config)
        self._max_calls = config.max_concurrent_calls
        self._semaphore = asyncio.Semaphore(self._max_calls)
        # Track available permits explicitly so we don't have to read
        # the private asyncio.Semaphore._value attribute.
        self._available_permits = self._max_calls
        self._counter_lock = asyncio.Lock()
        self._event_handlers: list[Callable[[Event], None]] = []
        self._metrics_initialized = False

    async def _init_metrics_if_needed(self) -> None:
        """Initialize metrics on first use (lazy init)."""
        if not self._metrics_initialized:
            await self.metrics.update_max_allowed_concurrent_calls(self._max_calls)
            await self.metrics.update_available_concurrent_calls(self._max_calls)
            self._metrics_initialized = True

    async def acquire_permission(self) -> bool:
        """
        Try to acquire permission to execute.

        Returns:
            True if permission was acquired, False otherwise
        """
        await self._init_metrics_if_needed()
        timeout = self.config.max_wait_duration.total_seconds()

        try:
            if timeout > 0:
                # Try to acquire with timeout
                await asyncio.wait_for(
                    self._semaphore.acquire(),
                    timeout=timeout
                )
            else:
                # Try to acquire without waiting. Use the explicit counter
                # under a lock to avoid racing on the private semaphore state.
                async with self._counter_lock:
                    if self._available_permits <= 0:
                        return False
                    await self._semaphore.acquire()

            async with self._counter_lock:
                self._available_permits -= 1
                available = self._available_permits
            await self.metrics.update_available_concurrent_calls(available)

            return True

        except asyncio.TimeoutError:
            return False

    async def release_permission(self) -> None:
        """Release previously acquired permission."""
        self._semaphore.release()

        async with self._counter_lock:
            self._available_permits += 1
            available = self._available_permits
        await self.metrics.update_available_concurrent_calls(available)
    
    async def on_call_permitted(self) -> None:
        """Called when a call is permitted."""
        event = BulkheadOnCallPermittedEvent(self.name)
        await self._publish_event(event)
    
    async def on_call_rejected(self) -> None:
        """Called when a call is rejected."""
        event = BulkheadOnCallRejectedEvent(self.name)
        await self._publish_event(event)
    
    async def on_call_finished(self) -> None:
        """Called when a call finishes."""
        event = BulkheadOnCallFinishedEvent(self.name)
        await self._publish_event(event)
    
    async def _execute_async(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Execute function with bulkhead protection.
        
        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result of func execution
            
        Raises:
            BulkheadFullException: If bulkhead is full and cannot accept the call
        """
        acquired = False
        
        try:
            # Try to acquire permission
            acquired = await self.acquire_permission()
            
            if not acquired:
                await self.on_call_rejected()
                raise BulkheadFullException(f"Bulkhead '{self.name}' is full")
            
            await self.on_call_permitted()
            
            # Execute the function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                # Run sync function in executor to avoid blocking.
                # run_in_executor doesn't accept kwargs, so bind them with partial.
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, partial(func, *args, **kwargs)
                )
            
            return result
            
        finally:
            if acquired:
                await self.release_permission()
                await self.on_call_finished()
    
    async def _publish_event(self, event: Event) -> None:
        """Publish event to registered handlers."""
        for handler in self._event_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception:
                # Log error but don't stop processing
                pass
    
    def on_event(self, handler: Callable[[Event], None]) -> None:
        """
        Register an event handler.
        
        Args:
            handler: Function to handle events
        """
        self._event_handlers.append(handler)