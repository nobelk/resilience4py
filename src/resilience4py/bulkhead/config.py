"""
Configuration classes for bulkhead patterns.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, Any

from ..core.config import BaseConfig


@dataclass(frozen=True)
class BulkheadConfig(BaseConfig):
    """
    Configuration for semaphore-based bulkhead.
    
    Attributes:
        max_concurrent_calls: Maximum number of concurrent calls allowed
        max_wait_duration: Maximum time to wait for permission (0 means no wait)
        tags: Optional tags for categorization
    """
    max_concurrent_calls: int = 25
    max_wait_duration: timedelta = timedelta(seconds=0)
    tags: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self) -> None:
        """Validate configuration parameters."""
        if self.max_concurrent_calls <= 0:
            raise ValueError("max_concurrent_calls must be positive")
        if self.max_wait_duration.total_seconds() < 0:
            raise ValueError("max_wait_duration cannot be negative")


@dataclass(frozen=True)
class ThreadPoolBulkheadConfig(BaseConfig):
    """
    Configuration for thread pool-based bulkhead.
    
    Attributes:
        max_thread_pool_size: Maximum number of threads in the pool
        core_thread_pool_size: Core number of threads to keep alive
        queue_capacity: Maximum number of tasks that can wait in queue
        keep_alive_duration: Time to keep idle threads alive
        tags: Optional tags for categorization
    """
    max_thread_pool_size: int = 4
    core_thread_pool_size: int = 2
    queue_capacity: int = 100
    keep_alive_duration: timedelta = timedelta(milliseconds=20)
    tags: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self) -> None:
        """Validate configuration parameters."""
        if self.max_thread_pool_size <= 0:
            raise ValueError("max_thread_pool_size must be positive")
        if self.core_thread_pool_size <= 0:
            raise ValueError("core_thread_pool_size must be positive")
        if self.core_thread_pool_size > self.max_thread_pool_size:
            raise ValueError("core_thread_pool_size cannot exceed max_thread_pool_size")
        if self.queue_capacity < 0:
            raise ValueError("queue_capacity cannot be negative")
        if self.keep_alive_duration.total_seconds() < 0:
            raise ValueError("keep_alive_duration cannot be negative")