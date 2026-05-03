"""Main Retry pattern implementation.

This module provides the core Retry decorator that can be applied to both
synchronous and asynchronous functions to automatically retry failed operations.
"""

import asyncio
import time
from functools import wraps
from typing import TypeVar, Callable, Any, Optional, Union, Awaitable, cast
from datetime import datetime

from .config import RetryConfig
from .events import (
    RetryOnRetryEvent,
    RetryOnSuccessEvent,
    RetryOnErrorEvent,
    RetryOnIgnoredErrorEvent
)


# Type variables for generic function signatures
F = TypeVar('F', bound=Callable[..., Any])
T = TypeVar('T')


class MaxRetriesExceeded(Exception):
    """Exception raised when maximum retry attempts are exhausted.
    
    This exception is raised when fail_after_max_attempts is True in the
    configuration and all retry attempts have been exhausted.
    
    Attributes:
        message: Error message describing the failure.
        last_exception: The last exception that caused the final retry to fail.
        attempts: Total number of attempts made.
    """
    
    def __init__(self, message: str, last_exception: Exception, attempts: int):
        """Initialize the exception.
        
        Args:
            message: Error message.
            last_exception: The last exception encountered.
            attempts: Total number of attempts made.
        """
        super().__init__(message)
        self.last_exception = last_exception
        self.attempts = attempts


class Retry:
    """Retry pattern implementation.
    
    The Retry class implements a decorator that can be applied to functions
    to automatically retry failed operations according to the configured
    retry policy.
    
    Example:
        >>> from datetime import timedelta
        >>> from resilience4py.retry import Retry, RetryConfig, ExponentialBackoff
        >>> 
        >>> # Create a retry instance with exponential backoff
        >>> config = RetryConfig(
        ...     max_attempts=3,
        ...     interval_function=ExponentialBackoff(1.0)
        ... )
        >>> retry = Retry("api-retry", config)
        >>> 
        >>> @retry
        >>> async def fetch_data():
        ...     # This will be retried up to 3 times with exponential backoff
        ...     return await api_client.get("/data")
    
    Attributes:
        name: Unique name for this retry instance.
        config: Configuration controlling retry behavior.
    """
    
    def __init__(self, name: str, config: Optional[RetryConfig] = None):
        """Initialize the Retry decorator.
        
        Args:
            name: Unique name for this retry instance.
            config: Optional configuration. If not provided, uses default config.
            
        Raises:
            ValueError: If name is empty or config validation fails.
        """
        if not name:
            raise ValueError("Retry name cannot be empty")
        
        self.name = name
        self.config = config or RetryConfig()
        self.config.validate()
        
        # Event handlers can be registered here
        self._event_handlers = {
            'on_retry': [],
            'on_success': [],
            'on_error': [],
            'on_ignored_error': []
        }
    
    def __call__(self, func: F) -> F:
        """Decorate a function with retry logic.
        
        This method supports both synchronous and asynchronous functions.
        
        Args:
            func: The function to decorate.
            
        Returns:
            The decorated function with retry logic.
        """
        if asyncio.iscoroutinefunction(func):
            return cast(F, self._decorate_async(func))
        else:
            return cast(F, self._decorate_sync(func))
    
    def _decorate_sync(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorate a synchronous function.
        
        Args:
            func: The synchronous function to decorate.
            
        Returns:
            The decorated synchronous function.
        """
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Check if we're already in an event loop
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context, create a new thread to run sync version
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self._execute_sync, func, *args, **kwargs)
                    return future.result()
            except RuntimeError:
                # No event loop running, we can create one
                loop = asyncio.new_event_loop()
                try:
                    # Create an async wrapper for the sync function
                    async def async_wrapper(*wrapper_args, **wrapper_kwargs):
                        return func(*wrapper_args, **wrapper_kwargs)
                    
                    coro = self._execute_with_retry(async_wrapper, *args, **kwargs)
                    return loop.run_until_complete(coro)
                finally:
                    loop.close()
        
        return wrapper
    
    def _execute_sync(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute synchronous retry logic without asyncio.
        
        This is used when we're already in an async context and need to run
        sync code without interfering with the existing event loop.
        """
        last_exception: Optional[Exception] = None
        start_time = time.monotonic()
        
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                result = func(*args, **kwargs)
                
                # Check if result should trigger a retry
                if self.config.retry_on_result and self.config.retry_on_result(result):
                    if attempt < self.config.max_attempts:
                        # Calculate wait time
                        wait_time = self.config.get_wait_duration(attempt)
                        
                        # Sleep before next attempt
                        time.sleep(wait_time)
                        continue
                
                # Success
                return result
                
            except Exception as e:
                last_exception = e
                
                # Check if exception should be retried
                if not self.config.should_retry_exception(e):
                    raise
                
                if attempt < self.config.max_attempts:
                    # Calculate wait time
                    wait_time = self.config.get_wait_duration(attempt)
                    
                    # Wait before next attempt
                    time.sleep(wait_time)
                else:
                    # Max attempts reached
                    if self.config.fail_after_max_attempts:
                        raise MaxRetriesExceeded(
                            f"Retry '{self.name}' exhausted after {attempt} attempts",
                            e,
                            attempt
                        ) from e
                    else:
                        raise
        
        # This should never be reached
        assert last_exception is not None
        raise last_exception
    
    def _decorate_async(self, func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        """Decorate an asynchronous function.
        
        Args:
            func: The asynchronous function to decorate.
            
        Returns:
            The decorated asynchronous function.
        """
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await self._execute_with_retry(func, *args, **kwargs)
        
        return wrapper
    
    async def _execute_with_retry(self, func: Callable[..., Union[T, Awaitable[T]]], *args, **kwargs) -> T:
        """Execute a function with retry logic.
        
        This is the core retry implementation that handles both sync and async functions.
        
        Args:
            func: The function to execute with retries.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.
            
        Returns:
            The result of the successful function execution.
            
        Raises:
            MaxRetriesExceeded: If fail_after_max_attempts is True and all attempts fail.
            Exception: The last exception if fail_after_max_attempts is False.
        """
        last_exception: Optional[Exception] = None
        start_time = time.monotonic()
        
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                # Execute the function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # Check if result should trigger a retry
                if self.config.retry_on_result and self.config.retry_on_result(result):
                    if attempt < self.config.max_attempts:
                        # Calculate wait time
                        wait_time = self.config.get_wait_duration(attempt)
                        
                        # Emit retry event
                        await self._emit_retry_event(attempt, result, wait_time)
                        
                        # Wait before next attempt
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        # Max attempts reached but result still triggers retry
                        # Treat as success since no exception occurred
                        total_duration = time.monotonic() - start_time
                        await self._emit_success_event(attempt, last_exception, total_duration)
                        return result
                
                # Success - emit event and return
                total_duration = time.monotonic() - start_time
                await self._emit_success_event(attempt, last_exception, total_duration)
                return result
                
            except Exception as e:
                last_exception = e
                
                # Check if exception should be retried
                if not self.config.should_retry_exception(e):
                    await self._emit_ignored_error_event(attempt, e)
                    raise
                
                if attempt < self.config.max_attempts:
                    # Calculate wait time
                    wait_time = self.config.get_wait_duration(attempt)
                    
                    # Emit retry event
                    await self._emit_retry_event(attempt, e, wait_time)
                    
                    # Wait before next attempt
                    await asyncio.sleep(wait_time)
                else:
                    # Max attempts reached
                    total_duration = time.monotonic() - start_time
                    await self._emit_error_event(attempt, e, total_duration)
                    
                    if self.config.fail_after_max_attempts:
                        raise MaxRetriesExceeded(
                            f"Retry '{self.name}' exhausted after {attempt} attempts",
                            e,
                            attempt
                        ) from e
                    else:
                        raise
        
        # This should never be reached, but just in case
        assert last_exception is not None
        raise last_exception
    
    async def _emit_retry_event(self, attempt: int, last_result: Union[Exception, Any], wait_interval: float):
        """Emit a retry event.
        
        Args:
            attempt: The attempt number that just failed.
            last_result: The exception or result that triggered the retry.
            wait_interval: Time in seconds before the next retry.
        """
        event = RetryOnRetryEvent(
            retry_name=self.name,
            attempt=attempt,
            last_result=last_result,
            wait_interval=wait_interval
        )
        await self._publish_event('on_retry', event)
    
    async def _emit_success_event(self, attempt: int, last_exception: Optional[Exception], total_duration: float):
        """Emit a success event.
        
        Args:
            attempt: The successful attempt number.
            last_exception: The last exception before success (if any).
            total_duration: Total time spent including all retry attempts.
        """
        event = RetryOnSuccessEvent(
            retry_name=self.name,
            attempt=attempt,
            last_exception=last_exception,
            total_duration=total_duration
        )
        await self._publish_event('on_success', event)
    
    async def _emit_error_event(self, attempt: int, last_exception: Exception, total_duration: float):
        """Emit an error event when all retries are exhausted.
        
        Args:
            attempt: The final attempt number.
            last_exception: The exception from the final attempt.
            total_duration: Total time spent including all retry attempts.
        """
        event = RetryOnErrorEvent(
            retry_name=self.name,
            attempt=attempt,
            last_exception=last_exception,
            total_duration=total_duration
        )
        await self._publish_event('on_error', event)
    
    async def _emit_ignored_error_event(self, attempt: int, exception: Exception):
        """Emit an event when an exception is not retryable.
        
        Args:
            attempt: The attempt number when the error occurred.
            exception: The exception that was not retried.
        """
        event = RetryOnIgnoredErrorEvent(
            retry_name=self.name,
            attempt=attempt,
            exception=exception
        )
        await self._publish_event('on_ignored_error', event)
    
    async def _publish_event(self, event_type: str, event: Any):
        """Publish an event to registered handlers.
        
        Args:
            event_type: The type of event to publish.
            event: The event object to publish.
        """
        handlers = self._event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception:
                # Log error but don't stop event processing
                # In a real implementation, this would use proper logging
                pass
    
    def on_retry(self, handler: Callable[[RetryOnRetryEvent], None]):
        """Register a handler for retry events.
        
        Args:
            handler: Function to call when a retry is scheduled.
        """
        self._event_handlers['on_retry'].append(handler)
    
    def on_success(self, handler: Callable[[RetryOnSuccessEvent], None]):
        """Register a handler for success events.
        
        Args:
            handler: Function to call when an operation succeeds.
        """
        self._event_handlers['on_success'].append(handler)
    
    def on_error(self, handler: Callable[[RetryOnErrorEvent], None]):
        """Register a handler for error events.
        
        Args:
            handler: Function to call when all retries are exhausted.
        """
        self._event_handlers['on_error'].append(handler)
    
    def on_ignored_error(self, handler: Callable[[RetryOnIgnoredErrorEvent], None]):
        """Register a handler for ignored error events.
        
        Args:
            handler: Function to call when an error is not retryable.
        """
        self._event_handlers['on_ignored_error'].append(handler)