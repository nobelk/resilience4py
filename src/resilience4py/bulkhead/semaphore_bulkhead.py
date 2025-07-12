"""
Semaphore-based bulkhead implementation using asyncio.Semaphore.
"""

from typing import Callable, Any, Optional
import asyncio
from datetime import datetime

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
        self._semaphore = asyncio.Semaphore(config.max_concurrent_calls)
        self._event_handlers: list[Callable[[Event], None]] = []
        
        # Initialize metrics with deferred tasks
        self._deferred_metrics_init = (config.max_concurrent_calls,)
    
    async def _init_metrics_if_needed(self):
        """Initialize metrics if not already done."""
        if hasattr(self, '_deferred_metrics_init'):
            max_calls = self._deferred_metrics_init[0]
            await self.metrics.update_max_allowed_concurrent_calls(max_calls)
            await self.metrics.update_available_concurrent_calls(max_calls)
            delattr(self, '_deferred_metrics_init')
    
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
                # Try to acquire without waiting
                if self._semaphore._value > 0:
                    await self._semaphore.acquire()
                else:
                    return False
            
            # Update metrics
            available = self._semaphore._value
            await self.metrics.update_available_concurrent_calls(available)
            
            return True
            
        except asyncio.TimeoutError:
            return False
    
    async def release_permission(self) -> None:
        """Release previously acquired permission."""
        self._semaphore.release()
        
        # Update metrics
        available = self._semaphore._value
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
    
    async def _execute_async(self, func: Callable, *args, **kwargs):
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
                # Run sync function in executor to avoid blocking
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, func, *args, **kwargs)
            
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