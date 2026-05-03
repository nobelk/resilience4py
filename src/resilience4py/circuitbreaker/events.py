"""Circuit Breaker event definitions.

This module defines all events emitted by the Circuit Breaker pattern,
allowing monitoring and observability of circuit breaker state changes and operations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional


class CircuitBreakerEventType(Enum):
    """Types of events emitted by Circuit Breaker."""
    SUCCESS = auto()
    ERROR = auto()
    NOT_PERMITTED = auto()
    STATE_TRANSITION = auto()
    RESET = auto()
    IGNORED_ERROR = auto()
    SLOW_CALL_RATE_EXCEEDED = auto()
    FAILURE_RATE_EXCEEDED = auto()
    MANUAL_STATE_TRANSITION = auto()


class CircuitBreakerState(Enum):
    """States of the Circuit Breaker state machine."""
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"
    DISABLED = "DISABLED"
    FORCED_OPEN = "FORCED_OPEN"
    METRICS_ONLY = "METRICS_ONLY"


@dataclass
class CircuitBreakerEvent:
    """Base class for all Circuit Breaker events.
    
    Attributes:
        circuit_breaker_name: Name of the circuit breaker that emitted the event.
        event_type: Type of the event.
        creation_time: Timestamp when the event was created.
    """
    circuit_breaker_name: str
    event_type: CircuitBreakerEventType
    creation_time: datetime = field(default_factory=datetime.now)


@dataclass
class CircuitBreakerOnSuccessEvent(CircuitBreakerEvent):
    """Event emitted when a call succeeds.
    
    Attributes:
        duration_ms: Duration of the successful call in milliseconds.
    """
    duration_ms: float = 0.0
    
    @classmethod
    def create(cls, circuit_breaker_name: str, duration_ms: float) -> "CircuitBreakerOnSuccessEvent":
        """Factory method to create the event."""
        return cls(
            circuit_breaker_name=circuit_breaker_name,
            event_type=CircuitBreakerEventType.SUCCESS,
            duration_ms=duration_ms
        )


@dataclass
class CircuitBreakerOnErrorEvent(CircuitBreakerEvent):
    """Event emitted when a call fails.
    
    Attributes:
        duration_ms: Duration of the failed call in milliseconds.
        exception: The exception that caused the failure.
    """
    duration_ms: float = 0.0
    exception: Optional[Exception] = None
    
    @classmethod
    def create(cls, circuit_breaker_name: str, duration_ms: float, exception: Exception) -> "CircuitBreakerOnErrorEvent":
        """Factory method to create the event."""
        return cls(
            circuit_breaker_name=circuit_breaker_name,
            event_type=CircuitBreakerEventType.ERROR,
            duration_ms=duration_ms,
            exception=exception
        )


@dataclass
class CircuitBreakerOnCallNotPermittedEvent(CircuitBreakerEvent):
    """Event emitted when a call is not permitted by the circuit breaker."""

    @classmethod
    def create(cls, circuit_breaker_name: str) -> "CircuitBreakerOnCallNotPermittedEvent":
        """Factory method to create the event."""
        return cls(
            circuit_breaker_name=circuit_breaker_name,
            event_type=CircuitBreakerEventType.NOT_PERMITTED
        )


@dataclass
class CircuitBreakerOnStateTransitionEvent(CircuitBreakerEvent):
    """Event emitted when circuit breaker changes state.
    
    Attributes:
        from_state: Previous state of the circuit breaker.
        to_state: New state of the circuit breaker.
    """
    from_state: Optional[CircuitBreakerState] = None
    to_state: Optional[CircuitBreakerState] = None
    
    @classmethod
    def create(cls, circuit_breaker_name: str, from_state: CircuitBreakerState,
               to_state: CircuitBreakerState) -> "CircuitBreakerOnStateTransitionEvent":
        """Factory method to create the event."""
        return cls(
            circuit_breaker_name=circuit_breaker_name,
            event_type=CircuitBreakerEventType.STATE_TRANSITION,
            from_state=from_state,
            to_state=to_state
        )


@dataclass
class CircuitBreakerOnResetEvent(CircuitBreakerEvent):
    """Event emitted when circuit breaker is reset."""

    @classmethod
    def create(cls, circuit_breaker_name: str) -> "CircuitBreakerOnResetEvent":
        """Factory method to create the event."""
        return cls(
            circuit_breaker_name=circuit_breaker_name,
            event_type=CircuitBreakerEventType.RESET
        )


@dataclass
class CircuitBreakerOnIgnoredErrorEvent(CircuitBreakerEvent):
    """Event emitted when an error is ignored by the circuit breaker.
    
    Attributes:
        exception: The exception that was ignored.
    """
    exception: Optional[Exception] = None
    
    @classmethod
    def create(cls, circuit_breaker_name: str, exception: Exception) -> "CircuitBreakerOnIgnoredErrorEvent":
        """Factory method to create the event."""
        return cls(
            circuit_breaker_name=circuit_breaker_name,
            event_type=CircuitBreakerEventType.IGNORED_ERROR,
            exception=exception
        )


@dataclass
class CircuitBreakerOnSlowCallRateExceededEvent(CircuitBreakerEvent):
    """Event emitted when slow call rate threshold is exceeded.
    
    Attributes:
        slow_call_rate: Current slow call rate percentage.
    """
    slow_call_rate: float = 0.0
    
    @classmethod
    def create(cls, circuit_breaker_name: str, slow_call_rate: float) -> "CircuitBreakerOnSlowCallRateExceededEvent":
        """Factory method to create the event."""
        return cls(
            circuit_breaker_name=circuit_breaker_name,
            event_type=CircuitBreakerEventType.SLOW_CALL_RATE_EXCEEDED,
            slow_call_rate=slow_call_rate
        )


@dataclass
class CircuitBreakerOnFailureRateExceededEvent(CircuitBreakerEvent):
    """Event emitted when failure rate threshold is exceeded.
    
    Attributes:
        failure_rate: Current failure rate percentage.
    """
    failure_rate: float = 0.0
    
    @classmethod
    def create(cls, circuit_breaker_name: str, failure_rate: float) -> "CircuitBreakerOnFailureRateExceededEvent":
        """Factory method to create the event."""
        return cls(
            circuit_breaker_name=circuit_breaker_name,
            event_type=CircuitBreakerEventType.FAILURE_RATE_EXCEEDED,
            failure_rate=failure_rate
        )


@dataclass
class CircuitBreakerOnManualStateTransitionEvent(CircuitBreakerEvent):
    """Event emitted when circuit breaker state is manually changed.
    
    Attributes:
        from_state: Previous state of the circuit breaker.
        to_state: New state of the circuit breaker.
    """
    from_state: Optional[CircuitBreakerState] = None
    to_state: Optional[CircuitBreakerState] = None
    
    @classmethod
    def create(cls, circuit_breaker_name: str, from_state: CircuitBreakerState,
               to_state: CircuitBreakerState) -> "CircuitBreakerOnManualStateTransitionEvent":
        """Factory method to create the event."""
        return cls(
            circuit_breaker_name=circuit_breaker_name,
            event_type=CircuitBreakerEventType.MANUAL_STATE_TRANSITION,
            from_state=from_state,
            to_state=to_state
        )