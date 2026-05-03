"""Circuit Breaker configuration module.

This module provides the configuration dataclass for the Circuit Breaker pattern,
allowing customization of failure thresholds, sliding windows, and state transitions.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Callable, List, Type, Optional
from enum import Enum


class SlidingWindowType(Enum):
    """Types of sliding windows for metrics collection."""
    COUNT_BASED = "COUNT_BASED"
    TIME_BASED = "TIME_BASED"


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Configuration for Circuit Breaker pattern.
    
    Attributes:
        failure_rate_threshold: Failure rate threshold in percentage. When the failure rate
            is equal or greater than the threshold, the circuit breaker transitions to open.
        slow_call_rate_threshold: Slow call rate threshold in percentage. When the slow call
            rate is equal or greater than the threshold, the circuit breaker transitions to open.
        slow_call_duration_threshold: Duration threshold to consider a call as slow.
        permitted_calls_in_half_open: Number of permitted calls when circuit breaker is half open.
        sliding_window_size: Size of the sliding window which is used to record the outcome of calls.
        sliding_window_type: Type of the sliding window (COUNT_BASED or TIME_BASED).
        minimum_number_of_calls: Minimum number of calls required before calculating error rate.
        wait_duration_in_open_state: Duration to wait in open state before transitioning to half-open.
        max_wait_duration_in_half_open: Maximum duration to wait in half-open state.
            0 means no maximum wait duration.
        automatic_transition_from_open_to_half_open: Whether to automatically transition from
            open to half-open state after wait duration.
        record_exceptions: List of exceptions to record as failures.
        ignore_exceptions: List of exceptions to ignore (not count as failures).
        record_failure_predicate: Optional predicate to determine if an exception should be
            recorded as a failure.
        ignore_failure_predicate: Optional predicate to determine if an exception should be
            ignored.
    """
    failure_rate_threshold: float = 50.0
    slow_call_rate_threshold: float = 100.0
    slow_call_duration_threshold: timedelta = timedelta(seconds=60)
    permitted_calls_in_half_open: int = 10
    sliding_window_size: int = 100
    sliding_window_type: SlidingWindowType = SlidingWindowType.COUNT_BASED
    minimum_number_of_calls: int = 100
    wait_duration_in_open_state: timedelta = timedelta(seconds=60)
    max_wait_duration_in_half_open: timedelta = timedelta(seconds=0)
    automatic_transition_from_open_to_half_open: bool = True
    record_exceptions: List[Type[Exception]] = field(default_factory=list)
    ignore_exceptions: List[Type[Exception]] = field(default_factory=list)
    record_failure_predicate: Optional[Callable[[Exception], bool]] = None
    ignore_failure_predicate: Optional[Callable[[Exception], bool]] = None

    def __post_init__(self) -> None:
        """Validate configuration parameters."""
        self.validate()
    
    def validate(self) -> None:
        """Validate that configuration parameters are within acceptable ranges.
        
        Raises:
            ValueError: If any configuration parameter is invalid.
        """
        if not 0 < self.failure_rate_threshold <= 100:
            raise ValueError(
                f"failure_rate_threshold must be between 0 and 100, got {self.failure_rate_threshold}"
            )
        
        if not 0 < self.slow_call_rate_threshold <= 100:
            raise ValueError(
                f"slow_call_rate_threshold must be between 0 and 100, got {self.slow_call_rate_threshold}"
            )
        
        if self.sliding_window_size <= 0:
            raise ValueError(
                f"sliding_window_size must be greater than 0, got {self.sliding_window_size}"
            )
        
        if self.minimum_number_of_calls <= 0:
            raise ValueError(
                f"minimum_number_of_calls must be greater than 0, got {self.minimum_number_of_calls}"
            )
        
        if self.permitted_calls_in_half_open <= 0:
            raise ValueError(
                f"permitted_calls_in_half_open must be greater than 0, got {self.permitted_calls_in_half_open}"
            )
        
        if self.wait_duration_in_open_state.total_seconds() <= 0:
            raise ValueError(
                "wait_duration_in_open_state must be positive"
            )
        
        if self.max_wait_duration_in_half_open.total_seconds() < 0:
            raise ValueError(
                "max_wait_duration_in_half_open must be non-negative"
            )
        
        if self.slow_call_duration_threshold.total_seconds() <= 0:
            raise ValueError(
                "slow_call_duration_threshold must be positive"
            )
    
    def should_record_exception(self, exception: Exception) -> bool:
        """Determine if an exception should be recorded as a failure.
        
        Args:
            exception: The exception to check.
            
        Returns:
            True if the exception should be recorded as a failure.
        """
        # First check ignore list
        if self.ignore_exceptions:
            for ignore_type in self.ignore_exceptions:
                if isinstance(exception, ignore_type):
                    return False
        
        # Check ignore predicate
        if self.ignore_failure_predicate and self.ignore_failure_predicate(exception):
            return False
        
        # Check record list
        if self.record_exceptions:
            for record_type in self.record_exceptions:
                if isinstance(exception, record_type):
                    return True
            # If record_exceptions is specified but exception doesn't match, don't record
            return False
        
        # Check record predicate
        if self.record_failure_predicate:
            return self.record_failure_predicate(exception)
        
        # By default, record all exceptions not explicitly ignored
        return True