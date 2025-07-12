"""Retry configuration module.

This module provides configuration options for the retry pattern implementation.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Callable, Optional, TypeVar, List

# Type variable for generic return types
T = TypeVar('T')


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for the Retry pattern.
    
    This configuration class defines all the parameters that control the behavior
    of the retry pattern, including the number of attempts, wait durations,
    and conditions for retrying.
    
    Attributes:
        max_attempts: Maximum number of retry attempts (including initial attempt).
            Must be greater than 0. Default is 3.
        wait_duration: Fixed wait duration between retry attempts when no interval
            function is specified. Default is 500ms.
        interval_function: Optional custom interval function that determines the
            wait time between retries based on the attempt number. If specified,
            this overrides wait_duration.
        retry_on_exception: Predicate function that determines whether an exception
            should trigger a retry. Default is to retry on all exceptions.
        retry_on_result: Optional predicate function that determines whether a
            successful result should trigger a retry. Useful for retrying on
            specific return values.
        fail_after_max_attempts: If True, raises MaxRetriesExceeded after all
            attempts are exhausted. If False, re-raises the last exception.
            Default is False.
        retry_exceptions: Optional list of exception types to retry on. If specified,
            only these exception types will trigger retries.
        abort_exceptions: Optional list of exception types that should immediately
            abort retry attempts. These exceptions will be raised immediately without
            further retries.
        tags: Optional dictionary of tags for metadata/monitoring purposes.
    """
    
    max_attempts: int = 3
    wait_duration: timedelta = timedelta(milliseconds=500)
    interval_function: Optional[Callable[[int], float]] = None
    retry_on_exception: Callable[[Exception], bool] = lambda e: True
    retry_on_result: Optional[Callable[[T], bool]] = None
    fail_after_max_attempts: bool = False
    retry_exceptions: Optional[List[type]] = None
    abort_exceptions: Optional[List[type]] = None
    tags: dict = field(default_factory=dict)
    
    def validate(self) -> None:
        """Validate configuration parameters.
        
        Raises:
            ValueError: If any configuration parameter is invalid.
        """
        if self.max_attempts <= 0:
            raise ValueError(f"max_attempts must be greater than 0, got {self.max_attempts}")
        
        if self.wait_duration.total_seconds() < 0:
            raise ValueError(f"wait_duration must be non-negative, got {self.wait_duration}")
        
        if self.retry_exceptions and self.abort_exceptions:
            # Check for overlapping exception types
            retry_set = set(self.retry_exceptions)
            abort_set = set(self.abort_exceptions)
            overlap = retry_set & abort_set
            if overlap:
                raise ValueError(
                    f"Exception types cannot be in both retry_exceptions and abort_exceptions: {overlap}"
                )
    
    def should_retry_exception(self, exception: Exception) -> bool:
        """Determine if an exception should trigger a retry.
        
        This method checks the exception against abort_exceptions,
        retry_exceptions, and the retry_on_exception predicate.
        
        Args:
            exception: The exception to check.
            
        Returns:
            True if the exception should trigger a retry, False otherwise.
        """
        # Check abort exceptions first
        if self.abort_exceptions:
            for abort_type in self.abort_exceptions:
                if isinstance(exception, abort_type):
                    return False
        
        # Check retry exceptions if specified
        if self.retry_exceptions:
            for retry_type in self.retry_exceptions:
                if isinstance(exception, retry_type):
                    return self.retry_on_exception(exception)
            return False
        
        # Use the predicate function
        return self.retry_on_exception(exception)
    
    def get_wait_duration(self, attempt: int) -> float:
        """Get the wait duration for a given attempt number.
        
        Args:
            attempt: The attempt number (1-based).
            
        Returns:
            Wait duration in seconds.
        """
        if self.interval_function:
            return self.interval_function(attempt)
        return self.wait_duration.total_seconds()