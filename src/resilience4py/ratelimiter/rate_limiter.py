"""
Main RateLimiter class that provides the public interface.
"""

from typing import Optional, Dict, Callable, Any, TypeVar, cast
from weakref import WeakValueDictionary
import asyncio

from .atomic_rate_limiter import AtomicRateLimiter, RequestNotPermitted
from .config import RateLimiterConfig
from .events import RateLimiterOnSuccessEvent, RateLimiterOnFailureEvent


F = TypeVar('F', bound=Callable[..., Any])


class RateLimiterRegistry:
    """
    Registry for managing RateLimiter instances.
    
    This registry ensures that rate limiters with the same name share the same
    underlying atomic rate limiter instance.
    """
    
    def __init__(self) -> None:
        """Initialize the registry."""
        self._default_config = RateLimiterConfig()
        self._instances: WeakValueDictionary[str, AtomicRateLimiter] = WeakValueDictionary()
        self._configs: Dict[str, RateLimiterConfig] = {}
        self._lock = asyncio.Lock()
    
    async def get_or_create(self, name: str, config: Optional[RateLimiterConfig] = None) -> AtomicRateLimiter:
        """
        Get or create a rate limiter instance.
        
        Args:
            name: The name of the rate limiter.
            config: Optional configuration for the rate limiter.
            
        Returns:
            The rate limiter instance.
        """
        async with self._lock:
            if name in self._instances:
                return self._instances[name]
            
            final_config = config or self._configs.get(name) or self._default_config
            instance = AtomicRateLimiter(name, final_config)
            self._instances[name] = instance
            if config:
                self._configs[name] = config
            return instance
    
    def set_default_config(self, config: RateLimiterConfig) -> None:
        """
        Set the default configuration for new rate limiters.

        Args:
            config: The default configuration to use.
        """
        self._default_config = config

    def remove(self, name: str) -> None:
        """
        Remove a rate limiter from the registry.
        
        Args:
            name: The name of the rate limiter to remove.
        """
        if name in self._instances:
            del self._instances[name]
        if name in self._configs:
            del self._configs[name]


# Global registry instance
_registry = RateLimiterRegistry()


class RateLimiter:
    """
    High-level RateLimiter interface.
    
    This class provides a convenient interface for using rate limiters in applications.
    It can be used as a decorator or called directly to manage rate limiting.
    
    Example:
        # As a decorator
        @RateLimiter("my-api", RateLimiterConfig(limit_for_period=10))
        async def my_api_call():
            return await fetch_data()
        
        # Direct usage
        rate_limiter = RateLimiter("my-limiter")
        
        @rate_limiter
        def my_function():
            return "result"
    """
    
    def __init__(self, name: str, config: Optional[RateLimiterConfig] = None):
        """
        Initialize the rate limiter.
        
        Args:
            name: The name of the rate limiter.
            config: Optional configuration for the rate limiter.
        """
        self.name = name
        self.config = config
        self._atomic_limiter: Optional[AtomicRateLimiter] = None
        # Listeners registered before the underlying limiter exists are held
        # here, then flushed in _get_limiter().
        self._pending_listeners: list[tuple[type, Callable]] = []

    async def _get_limiter(self) -> AtomicRateLimiter:
        """
        Get the underlying atomic rate limiter.

        Returns:
            The atomic rate limiter instance.
        """
        if self._atomic_limiter is None:
            self._atomic_limiter = await _registry.get_or_create(self.name, self.config)
            for event_type, listener in self._pending_listeners:
                self._atomic_limiter.add_event_listener(event_type, listener)
        return self._atomic_limiter
    
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
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            loop = asyncio.new_event_loop()
            try:
                limiter = loop.run_until_complete(self._get_limiter())
                decorated = limiter(func)
                return decorated(*args, **kwargs)
            finally:
                loop.close()
        return cast(F, wrapper)

    def _decorate_async(self, func: F) -> F:
        """
        Decorate an asynchronous function.

        Args:
            func: The asynchronous function to decorate.

        Returns:
            The decorated function.
        """
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            limiter = await self._get_limiter()
            decorated = limiter(func)
            return await decorated(*args, **kwargs)
        return cast(F, wrapper)
    
    @staticmethod
    def of(name: str, config: Optional[RateLimiterConfig] = None) -> 'RateLimiter':
        """
        Factory method to create a rate limiter.
        
        Args:
            name: The name of the rate limiter.
            config: Optional configuration for the rate limiter.
            
        Returns:
            A new RateLimiter instance.
        """
        return RateLimiter(name, config)
    
    @staticmethod
    def set_default_config(config: RateLimiterConfig) -> None:
        """
        Set the default configuration for all new rate limiters.

        Args:
            config: The default configuration to use.
        """
        _registry.set_default_config(config)
    
    async def acquire_permission(self) -> bool:
        """
        Try to acquire permission without decorating a function.
        
        Returns:
            True if permission was granted, False otherwise.
        """
        limiter = await self._get_limiter()
        try:
            wait_time = await limiter._reserve_permission()
            if wait_time < 0:
                return False
            if wait_time > 0:
                await asyncio.sleep(wait_time / 1_000_000_000)
            return True
        except Exception:
            return False
    
    async def get_metrics(self) -> dict:
        """
        Get current metrics for this rate limiter.
        
        Returns:
            A dictionary containing current metrics.
        """
        limiter = await self._get_limiter()
        return await limiter.get_metrics()
    
    async def reset(self) -> None:
        """Reset this rate limiter to its initial state."""
        limiter = await self._get_limiter()
        await limiter.reset()
    
    def add_event_listener(self, event_type: type, listener: Callable) -> None:
        """
        Add an event listener for a specific event type.

        Listeners registered before the underlying AtomicRateLimiter exists are
        held until the first call (which creates the limiter). After that, new
        listeners attach immediately. Listeners may be sync or async callables
        that accept the event as their only argument.

        Args:
            event_type: The event class to listen for (e.g.
                ``RateLimiterOnSuccessEvent`` or ``RateLimiterOnFailureEvent``).
            listener: Callable invoked with the event when it fires.
        """
        self._pending_listeners.append((event_type, listener))
        if self._atomic_limiter is not None:
            self._atomic_limiter.add_event_listener(event_type, listener)

    def remove_event_listener(self, event_type: type, listener: Callable) -> bool:
        """Remove a previously registered listener.

        Returns:
            True if a matching listener was removed, False otherwise.
        """
        removed = False
        try:
            self._pending_listeners.remove((event_type, listener))
            removed = True
        except ValueError:
            pass
        if self._atomic_limiter is not None:
            removed = self._atomic_limiter.remove_event_listener(event_type, listener) or removed
        return removed


# Convenience functions
def rate_limit(limit_for_period: int, refresh_period_seconds: float = 1.0) -> RateLimiter:
    """
    Create a rate limiter with simple configuration.
    
    Args:
        limit_for_period: Number of allowed calls per period.
        refresh_period_seconds: Period length in seconds.
        
    Returns:
        A configured RateLimiter instance.
    """
    from datetime import timedelta
    config = RateLimiterConfig(
        limit_for_period=limit_for_period,
        limit_refresh_period=timedelta(seconds=refresh_period_seconds)
    )
    return RateLimiter(f"rate-limit-{limit_for_period}-{refresh_period_seconds}", config)


__all__ = ["RateLimiter", "RateLimiterRegistry", "RequestNotPermitted", "rate_limit"]