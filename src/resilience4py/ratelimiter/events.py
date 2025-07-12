"""
Event classes for the Rate Limiter pattern.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional


class RateLimiterEventType(Enum):
    """Rate limiter event types."""
    SUCCESS = auto()
    FAILURE = auto()


@dataclass
class RateLimiterEvent:
    """Base event class for rate limiter events."""
    name: str
    event_type: RateLimiterEventType
    creation_time: datetime = field(default_factory=datetime.now)
    
    def __str__(self) -> str:
        """String representation of the event."""
        return f"{self.event_type.name} event for rate limiter '{self.name}' at {self.creation_time}"


@dataclass
class RateLimiterOnSuccessEvent(RateLimiterEvent):
    """Event published when a call is permitted by the rate limiter."""
    
    def __init__(self, name: str):
        """
        Initialize success event.
        
        Args:
            name: The name of the rate limiter.
        """
        super().__init__(name=name, event_type=RateLimiterEventType.SUCCESS)


@dataclass
class RateLimiterOnFailureEvent(RateLimiterEvent):
    """Event published when a call is rejected by the rate limiter."""
    wait_time_nanos: Optional[int] = None
    
    def __init__(self, name: str, wait_time_nanos: Optional[int] = None):
        """
        Initialize failure event.
        
        Args:
            name: The name of the rate limiter.
            wait_time_nanos: The time in nanoseconds that would be required to wait for permission.
        """
        super().__init__(name=name, event_type=RateLimiterEventType.FAILURE)
        self.wait_time_nanos = wait_time_nanos