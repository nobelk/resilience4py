"""
Event classes for bulkhead pattern.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional

from ..core.events import Event


class BulkheadEventType(Enum):
    """Bulkhead event types."""
    CALL_PERMITTED = auto()
    CALL_REJECTED = auto()
    CALL_FINISHED = auto()


@dataclass
class BulkheadEvent(Event):
    """Base class for bulkhead events."""
    bulkhead_name: str = ""
    
    def __post_init__(self):
        """Set name to bulkhead name if not provided."""
        if not self.name:
            object.__setattr__(self, 'name', self.bulkhead_name)


@dataclass
class BulkheadOnCallPermittedEvent(BulkheadEvent):
    """Event emitted when a call is permitted by the bulkhead."""
    
    def __init__(self, bulkhead_name: str):
        super().__init__(
            bulkhead_name=bulkhead_name,
            event_type=BulkheadEventType.CALL_PERMITTED,
            name=bulkhead_name
        )


@dataclass
class BulkheadOnCallRejectedEvent(BulkheadEvent):
    """Event emitted when a call is rejected by the bulkhead."""
    
    def __init__(self, bulkhead_name: str):
        super().__init__(
            bulkhead_name=bulkhead_name,
            event_type=BulkheadEventType.CALL_REJECTED,
            name=bulkhead_name
        )


@dataclass
class BulkheadOnCallFinishedEvent(BulkheadEvent):
    """Event emitted when a call finishes execution."""
    
    def __init__(self, bulkhead_name: str):
        super().__init__(
            bulkhead_name=bulkhead_name,
            event_type=BulkheadEventType.CALL_FINISHED,
            name=bulkhead_name
        )