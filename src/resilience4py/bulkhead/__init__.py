"""
Bulkhead pattern implementation for resilience4py.

The Bulkhead pattern isolates different parts of an application into pools
to prevent failures in one part from affecting other parts.
"""

from .bulkhead import Bulkhead, BulkheadFullException
from .semaphore_bulkhead import SemaphoreBulkhead
from .threadpool_bulkhead import ThreadPoolBulkhead
from .config import BulkheadConfig, ThreadPoolBulkheadConfig
from .events import (
    BulkheadEvent,
    BulkheadOnCallPermittedEvent,
    BulkheadOnCallRejectedEvent,
    BulkheadOnCallFinishedEvent,
)

__all__ = [
    "Bulkhead",
    "BulkheadFullException",
    "SemaphoreBulkhead",
    "ThreadPoolBulkhead",
    "BulkheadConfig",
    "ThreadPoolBulkheadConfig",
    "BulkheadEvent",
    "BulkheadOnCallPermittedEvent",
    "BulkheadOnCallRejectedEvent",
    "BulkheadOnCallFinishedEvent",
]