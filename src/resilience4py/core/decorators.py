"""
Base decorator utilities for resilience patterns

Provides a base decorator class that supports both synchronous
and asynchronous functions transparently.
"""

from functools import wraps
from typing import TypeVar, Callable, Union, Awaitable, Any, List, cast
import asyncio
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable[..., Any])


class BaseDecorator(ABC):
    """Base class for resilience decorators
    
    This class provides the foundation for all resilience pattern
    decorators. It automatically handles both synchronous and
    asynchronous functions, running sync functions in an event loop.
    
    Attributes:
        name: Unique name for this decorator instance
    """
    
    def __init__(self, name: str):
        """Initialize base decorator
        
        Args:
            name: Unique name for this decorator instance
        """
        self.name = name
    
    def __call__(self, func: F) -> F:
        """Decorate synchronous or asynchronous functions
        
        This method automatically detects whether the decorated function
        is synchronous or asynchronous and applies the appropriate wrapper.
        
        Args:
            func: Function to decorate
            
        Returns:
            Decorated function with the same signature
        """
        if asyncio.iscoroutinefunction(func):
            return self._decorate_async(func)
        else:
            return self._decorate_sync(func)
    
    def _decorate_sync(self, func: F) -> F:
        """Wrap synchronous function to use async implementation
        
        Args:
            func: Synchronous function to wrap
            
        Returns:
            Wrapped synchronous function
        """
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Try to get the current event loop
            try:
                loop = asyncio.get_running_loop()
                # If we're already in an event loop, we need to run in a thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self._run_sync_in_new_loop, func, args, kwargs)
                    return future.result()
            except RuntimeError:
                # No event loop running, create a new one
                return self._run_sync_in_new_loop(func, args, kwargs)

        return cast(F, wrapper)

    def _run_sync_in_new_loop(self, func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        """Run sync function in a new event loop
        
        Args:
            func: Function to run
            args: Positional arguments
            kwargs: Keyword arguments
            
        Returns:
            Function result
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            coro = self._execute_async(func, *args, **kwargs)
            return loop.run_until_complete(coro)
        finally:
            loop.close()
            asyncio.set_event_loop(None)
    
    def _decorate_async(self, func: F) -> F:
        """Wrap asynchronous function
        
        Args:
            func: Asynchronous function to wrap
            
        Returns:
            Wrapped asynchronous function
        """
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await self._execute_async(func, *args, **kwargs)

        return cast(F, wrapper)

    @abstractmethod
    async def _execute_async(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute function with resilience pattern
        
        This method must be implemented by subclasses to apply the
        specific resilience pattern logic.
        
        Args:
            func: Function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Result of the function execution
            
        Raises:
            Any exception raised by the function or resilience logic
        """
        pass
    
    def __repr__(self) -> str:
        """String representation of decorator"""
        return f"{self.__class__.__name__}(name='{self.name}')"


class CompositeDecorator(BaseDecorator):
    """Decorator that composes multiple resilience patterns
    
    This decorator allows chaining multiple resilience patterns
    together, executing them in order.
    
    Attributes:
        decorators: List of decorators to apply in order
    """
    
    def __init__(self, name: str, decorators: List[BaseDecorator]):
        """Initialize composite decorator
        
        Args:
            name: Unique name for this composite
            decorators: List of decorators to apply in order
        """
        super().__init__(name)
        self.decorators = decorators
    
    async def _execute_async(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute function through all decorators in order

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result of the function execution
        """
        # Build the chain of decorators
        current_func: Callable[..., Any] = func

        # Apply decorators in reverse order so they execute in the correct order
        for decorator in reversed(self.decorators):
            # Create a closure to capture the current function
            def make_wrapped(f: Callable[..., Any], d: 'BaseDecorator') -> Callable[..., Any]:
                async def wrapped(*a: Any, **kw: Any) -> Any:
                    return await d._execute_async(f, *a, **kw)
                return wrapped

            current_func = make_wrapped(current_func, decorator)

        # Execute the wrapped function
        return await current_func(*args, **kwargs)