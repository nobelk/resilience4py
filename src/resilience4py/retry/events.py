"""Retry-specific events.

This module defines all the events that can be emitted by the retry pattern
during its operation. These events can be used for monitoring, logging, and
metrics collection.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Union, Any
from enum import Enum, auto


class RetryEventType(Enum):
    """Enumeration of retry event types."""
    
    ON_RETRY = auto()
    ON_SUCCESS = auto()
    ON_ERROR = auto()
    ON_IGNORED_ERROR = auto()


class RetryEvent:
    """Base class for all retry events.
    
    Attributes:
        retry_name: Name of the retry instance that generated the event.
        event_type: Type of the retry event.
        creation_time: Timestamp when the event was created.
    """
    
    def __init__(self, retry_name: str, event_type: RetryEventType):
        """Initialize base retry event."""
        self.retry_name = retry_name
        self.event_type = event_type
        self.creation_time = datetime.now()


class RetryOnRetryEvent(RetryEvent):
    """Event emitted when a retry attempt is scheduled.
    
    This event is emitted after a failed attempt when another retry
    will be attempted.
    
    Attributes:
        retry_name: Name of the retry instance.
        event_type: Always RetryEventType.ON_RETRY.
        attempt: The attempt number that just failed (1-based).
        last_result: The exception or result that triggered the retry.
        wait_interval: Time in seconds before the next retry attempt.
        creation_time: Timestamp when the event was created.
    """
    
    def __init__(self, retry_name: str, attempt: int, last_result: Union[Exception, Any], wait_interval: float):
        """Initialize retry event.
        
        Args:
            retry_name: Name of the retry instance.
            attempt: The attempt number that just failed.
            last_result: The exception or result that triggered the retry.
            wait_interval: Time before the next retry attempt.
            
        Raises:
            ValueError: If attempt is not positive or wait_interval is negative.
        """
        super().__init__(retry_name=retry_name, event_type=RetryEventType.ON_RETRY)
        
        if attempt <= 0:
            raise ValueError(f"attempt must be positive, got {attempt}")
        if wait_interval < 0:
            raise ValueError(f"wait_interval must be non-negative, got {wait_interval}")
        
        self.attempt = attempt
        self.last_result = last_result
        self.wait_interval = wait_interval
    
    @property
    def is_exception_retry(self) -> bool:
        """Check if this retry was triggered by an exception."""
        return isinstance(self.last_result, Exception)
    
    @property
    def exception(self) -> Optional[Exception]:
        """Get the exception if this was an exception retry."""
        return self.last_result if isinstance(self.last_result, Exception) else None
    
    @property
    def result(self) -> Any:
        """Get the result if this was a result-based retry."""
        return None if isinstance(self.last_result, Exception) else self.last_result


class RetryOnSuccessEvent(RetryEvent):
    """Event emitted when a retry attempt succeeds.
    
    This event is emitted when a function call succeeds (either on the
    first attempt or after retries).
    
    Attributes:
        retry_name: Name of the retry instance.
        event_type: Always RetryEventType.ON_SUCCESS.
        attempt: The successful attempt number (1-based).
        last_exception: The last exception before success (if any).
        total_duration: Total time spent including all retry attempts (seconds).
        creation_time: Timestamp when the event was created.
    """
    
    def __init__(self, retry_name: str, attempt: int, last_exception: Optional[Exception], total_duration: float):
        """Initialize success event.
        
        Args:
            retry_name: Name of the retry instance.
            attempt: The successful attempt number.
            last_exception: The last exception before success (if any).
            total_duration: Total time spent including all retry attempts.
            
        Raises:
            ValueError: If attempt is not positive or total_duration is negative.
        """
        super().__init__(retry_name=retry_name, event_type=RetryEventType.ON_SUCCESS)
        
        if attempt <= 0:
            raise ValueError(f"attempt must be positive, got {attempt}")
        if total_duration < 0:
            raise ValueError(f"total_duration must be non-negative, got {total_duration}")
        
        self.attempt = attempt
        self.last_exception = last_exception
        self.total_duration = total_duration
    
    @property
    def had_retries(self) -> bool:
        """Check if there were any retry attempts before success."""
        return self.attempt > 1
    
    @property
    def retry_count(self) -> int:
        """Get the number of retry attempts (excluding the initial attempt)."""
        return self.attempt - 1


class RetryOnErrorEvent(RetryEvent):
    """Event emitted when all retry attempts are exhausted.
    
    This event is emitted when the maximum number of retry attempts
    has been reached and the operation still fails.
    
    Attributes:
        retry_name: Name of the retry instance.
        event_type: Always RetryEventType.ON_ERROR.
        attempt: The final attempt number (1-based).
        last_exception: The exception from the final attempt.
        total_duration: Total time spent including all retry attempts (seconds).
        creation_time: Timestamp when the event was created.
    """
    
    def __init__(self, retry_name: str, attempt: int, last_exception: Exception, total_duration: float):
        """Initialize error event.
        
        Args:
            retry_name: Name of the retry instance.
            attempt: The final attempt number.
            last_exception: The exception from the final attempt.
            total_duration: Total time spent including all retry attempts.
            
        Raises:
            ValueError: If attempt is not positive or total_duration is negative.
            TypeError: If last_exception is not an Exception.
        """
        super().__init__(retry_name=retry_name, event_type=RetryEventType.ON_ERROR)
        
        if attempt <= 0:
            raise ValueError(f"attempt must be positive, got {attempt}")
        if total_duration < 0:
            raise ValueError(f"total_duration must be non-negative, got {total_duration}")
        if not isinstance(last_exception, Exception):
            raise TypeError(f"last_exception must be an Exception, got {type(last_exception)}")
        
        self.attempt = attempt
        self.last_exception = last_exception
        self.total_duration = total_duration
    
    @property
    def total_attempts(self) -> int:
        """Get the total number of attempts made."""
        return self.attempt


class RetryOnIgnoredErrorEvent(RetryEvent):
    """Event emitted when an exception is not retryable.
    
    This event is emitted when an exception occurs that should not
    trigger a retry (e.g., it's in the abort_exceptions list or doesn't
    match the retry predicate).
    
    Attributes:
        retry_name: Name of the retry instance.
        event_type: Always RetryEventType.ON_IGNORED_ERROR.
        attempt: The attempt number when the error occurred (1-based).
        exception: The exception that was not retried.
        creation_time: Timestamp when the event was created.
    """
    
    def __init__(self, retry_name: str, attempt: int, exception: Exception):
        """Initialize ignored error event.
        
        Args:
            retry_name: Name of the retry instance.
            attempt: The attempt number when the error occurred.
            exception: The exception that was not retried.
            
        Raises:
            ValueError: If attempt is not positive.
            TypeError: If exception is not an Exception.
        """
        super().__init__(retry_name=retry_name, event_type=RetryEventType.ON_IGNORED_ERROR)
        
        if attempt <= 0:
            raise ValueError(f"attempt must be positive, got {attempt}")
        if not isinstance(exception, Exception):
            raise TypeError(f"exception must be an Exception, got {type(exception)}")
        
        self.attempt = attempt
        self.exception = exception
    
    @property
    def exception_type(self) -> type:
        """Get the type of the ignored exception."""
        return type(self.exception)
    
    @property
    def exception_message(self) -> str:
        """Get the message of the ignored exception."""
        # For exceptions with args, get the first arg (the message)
        if self.exception.args:
            return str(self.exception.args[0])
        return str(self.exception)