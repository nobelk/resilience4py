"""
Base bulkhead implementation.
"""

from abc import ABC, abstractmethod
from typing import Callable, Any, Optional
import asyncio

from ..core.decorators import BaseDecorator
from .config import BulkheadConfig
from .events import (
    BulkheadOnCallPermittedEvent,
    BulkheadOnCallRejectedEvent,
    BulkheadOnCallFinishedEvent,
)


class BulkheadFullException(Exception):
    """Exception raised when bulkhead is full and cannot accept more calls."""
    pass


class Bulkhead(BaseDecorator, ABC):
    """
    Abstract base class for bulkhead implementations.
    
    The Bulkhead pattern limits the number of concurrent calls to a particular
    resource to prevent resource exhaustion.
    """
    
    def __init__(self, name: str, config: BulkheadConfig):
        """
        Initialize bulkhead.
        
        Args:
            name: Name of the bulkhead instance
            config: Bulkhead configuration
        """
        super().__init__(name)
        self.config = config
        self._metrics = BulkheadMetrics()
    
    @abstractmethod
    async def acquire_permission(self) -> bool:
        """
        Try to acquire permission to execute.
        
        Returns:
            True if permission was acquired, False otherwise
        """
        pass
    
    @abstractmethod
    async def release_permission(self) -> None:
        """Release previously acquired permission."""
        pass
    
    @abstractmethod
    async def on_call_permitted(self) -> None:
        """Called when a call is permitted."""
        pass
    
    @abstractmethod
    async def on_call_rejected(self) -> None:
        """Called when a call is rejected."""
        pass
    
    @abstractmethod
    async def on_call_finished(self) -> None:
        """Called when a call finishes."""
        pass
    
    @property
    def metrics(self) -> 'BulkheadMetrics':
        """Get bulkhead metrics."""
        return self._metrics


class BulkheadMetrics:
    """Metrics collector for bulkhead."""

    def __init__(self) -> None:
        self._available_concurrent_calls = 0
        self._max_allowed_concurrent_calls = 0
        self._lock = asyncio.Lock()
    
    async def get_available_concurrent_calls(self) -> int:
        """Get number of available concurrent call slots."""
        async with self._lock:
            return self._available_concurrent_calls
    
    async def get_max_allowed_concurrent_calls(self) -> int:
        """Get maximum allowed concurrent calls."""
        async with self._lock:
            return self._max_allowed_concurrent_calls
    
    async def update_available_concurrent_calls(self, available: int) -> None:
        """Update available concurrent calls."""
        async with self._lock:
            self._available_concurrent_calls = available
    
    async def update_max_allowed_concurrent_calls(self, max_allowed: int) -> None:
        """Update maximum allowed concurrent calls."""
        async with self._lock:
            self._max_allowed_concurrent_calls = max_allowed