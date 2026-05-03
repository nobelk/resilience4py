"""
Thread pool-based bulkhead implementation using ThreadPoolExecutor.
"""

from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Any, Optional, Union
import asyncio
import contextvars
from functools import partial

from .bulkhead import Bulkhead, BulkheadFullException
from .config import ThreadPoolBulkheadConfig, BulkheadConfig
from .events import (
    BulkheadOnCallPermittedEvent,
    BulkheadOnCallRejectedEvent,
    BulkheadOnCallFinishedEvent,
)
from ..core.events import Event


class ThreadPoolBulkhead(Bulkhead):
    """
    Bulkhead implementation using ThreadPoolExecutor.
    
    This implementation uses a thread pool to execute tasks, making it
    suitable for CPU-bound operations that would otherwise block the
    event loop. It supports context propagation to maintain context
    across thread boundaries.
    """
    
    def __init__(self, name: str, config: ThreadPoolBulkheadConfig):
        """
        Initialize thread pool bulkhead.
        
        Args:
            name: Name of the bulkhead instance
            config: Thread pool bulkhead configuration
        """
        # Note: we pass the base config part to parent
        base_config = BulkheadConfig(
            max_concurrent_calls=config.max_thread_pool_size,
            max_wait_duration=config.keep_alive_duration,
            tags=config.tags
        )
        super().__init__(name, base_config)
        
        self.thread_config = config
        self._executor = ThreadPoolExecutor(
            max_workers=config.max_thread_pool_size,
            thread_name_prefix=f"bulkhead-{name}"
        )
        
        # Semaphore to control total concurrent executions (threads + queue)
        total_capacity = config.max_thread_pool_size + config.queue_capacity
        self._total_capacity = total_capacity
        self._semaphore = asyncio.Semaphore(total_capacity)
        # Track available permits explicitly so we don't need to read
        # the private asyncio.Semaphore._value attribute.
        self._available_permits = total_capacity
        self._event_handlers: list[Callable[[Event], None]] = []
        # Always defer metrics init: constructors must not depend on ambient
        # event-loop state, and asyncio.create_task() in __init__ produced
        # "coroutine was never awaited" warnings whenever no loop was running.
        self._metrics_initialized = False

    async def _ensure_metrics_initialized(self):
        """Initialize metrics on first use (lazy init)."""
        if not self._metrics_initialized:
            await self.metrics.update_max_allowed_concurrent_calls(self._total_capacity)
            await self.metrics.update_available_concurrent_calls(self._total_capacity)
            self._metrics_initialized = True
    
    async def acquire_permission(self) -> bool:
        """
        Try to acquire permission to execute.

        Returns:
            True if permission was acquired, False otherwise
        """
        await self._ensure_metrics_initialized()

        # Non-blocking check using our explicit counter.
        if self._available_permits <= 0:
            return False

        acquired = await self._semaphore.acquire()
        if acquired:
            self._available_permits -= 1
            await self.metrics.update_available_concurrent_calls(self._available_permits)

        return acquired

    async def release_permission(self) -> None:
        """Release previously acquired permission."""
        self._semaphore.release()
        self._available_permits += 1
        await self.metrics.update_available_concurrent_calls(self._available_permits)
    
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
    
    async def submit(self, func: Callable, *args, **kwargs) -> Any:
        """
        Submit a function to the thread pool for execution.
        
        This method provides direct access to thread pool submission
        with context propagation support.
        
        Args:
            func: Function to execute in thread pool
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result of func execution
            
        Raises:
            BulkheadFullException: If bulkhead is full
        """
        acquired = await self.acquire_permission()
        if not acquired:
            await self.on_call_rejected()
            raise BulkheadFullException(
                f"ThreadPool bulkhead '{self.name}' is full"
            )
        
        try:
            await self.on_call_permitted()
            
            # Copy context for propagation
            ctx = contextvars.copy_context()
            
            # Create a partial function that includes context
            wrapped_func = partial(ctx.run, func, *args, **kwargs)
            
            # Submit to thread pool
            future = self._executor.submit(wrapped_func)
            
            # Convert concurrent.futures.Future to asyncio.Future
            result = await asyncio.wrap_future(future)
            
            return result
            
        finally:
            await self.release_permission()
            await self.on_call_finished()
    
    async def _execute_async(self, func: Callable, *args, **kwargs):
        """
        Execute function with thread pool bulkhead protection.
        
        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result of func execution
            
        Raises:
            BulkheadFullException: If bulkhead is full
        """
        # For async functions, we'll run them in the current event loop
        # For sync functions, we'll submit them to the thread pool
        
        if asyncio.iscoroutinefunction(func):
            # Async function - acquire permission and run in event loop
            acquired = await self.acquire_permission()
            if not acquired:
                await self.on_call_rejected()
                raise BulkheadFullException(
                    f"ThreadPool bulkhead '{self.name}' is full"
                )
            
            try:
                await self.on_call_permitted()
                return await func(*args, **kwargs)
            finally:
                await self.release_permission()
                await self.on_call_finished()
        else:
            # Sync function - submit to thread pool
            return await self.submit(func, *args, **kwargs)
    
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
    
    def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the thread pool executor.
        
        Args:
            wait: If True, wait for all pending tasks to complete
        """
        self._executor.shutdown(wait=wait)
    
    def __del__(self):
        """Cleanup thread pool on deletion."""
        if hasattr(self, '_executor'):
            self.shutdown(wait=False)