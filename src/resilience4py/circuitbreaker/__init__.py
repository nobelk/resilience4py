"""Circuit Breaker pattern implementation.

This module provides the Circuit Breaker pattern for fault tolerance,
protecting systems from cascading failures by monitoring function calls
and preventing calls to failing services.
"""

from .circuit_breaker import CircuitBreaker, CallNotPermittedException
from .config import CircuitBreakerConfig, SlidingWindowType
from .events import (
    CircuitBreakerState,
    CircuitBreakerEvent,
    CircuitBreakerEventType,
    CircuitBreakerOnSuccessEvent,
    CircuitBreakerOnErrorEvent,
    CircuitBreakerOnCallNotPermittedEvent,
    CircuitBreakerOnStateTransitionEvent,
    CircuitBreakerOnResetEvent,
    CircuitBreakerOnIgnoredErrorEvent,
    CircuitBreakerOnSlowCallRateExceededEvent,
    CircuitBreakerOnFailureRateExceededEvent,
    CircuitBreakerOnManualStateTransitionEvent
)
from .metrics import SlidingWindowMetrics, Snapshot

__all__ = [
    # Main classes
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CallNotPermittedException",
    
    # Enums
    "CircuitBreakerState",
    "CircuitBreakerEventType",
    "SlidingWindowType",
    
    # Events
    "CircuitBreakerEvent",
    "CircuitBreakerOnSuccessEvent",
    "CircuitBreakerOnErrorEvent",
    "CircuitBreakerOnCallNotPermittedEvent",
    "CircuitBreakerOnStateTransitionEvent",
    "CircuitBreakerOnResetEvent",
    "CircuitBreakerOnIgnoredErrorEvent",
    "CircuitBreakerOnSlowCallRateExceededEvent",
    "CircuitBreakerOnFailureRateExceededEvent",
    "CircuitBreakerOnManualStateTransitionEvent",
    
    # Metrics
    "SlidingWindowMetrics",
    "Snapshot",
]