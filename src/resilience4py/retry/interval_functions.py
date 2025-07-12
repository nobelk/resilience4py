"""Interval functions for retry pattern.

This module provides various interval functions that determine the wait time
between retry attempts. These functions implement different backoff strategies.
"""

from abc import ABC, abstractmethod
from typing import Optional
import random
import math


class IntervalFunction(ABC):
    """Base class for retry interval strategies.
    
    An interval function determines how long to wait between retry attempts.
    The function takes the current attempt number and returns the wait time
    in seconds.
    """
    
    @abstractmethod
    def __call__(self, attempt: int) -> float:
        """Calculate wait time for the given attempt.
        
        Args:
            attempt: The attempt number (1-based, so first retry is attempt 2).
            
        Returns:
            Wait time in seconds before the next retry attempt.
        """
        pass


class FixedInterval(IntervalFunction):
    """Fixed interval between retry attempts.
    
    This interval function returns the same wait time for every retry attempt,
    regardless of the attempt number.
    
    Attributes:
        interval_seconds: The fixed wait time in seconds between attempts.
    """
    
    def __init__(self, interval_seconds: float):
        """Initialize with a fixed interval.
        
        Args:
            interval_seconds: The fixed wait time in seconds. Must be non-negative.
            
        Raises:
            ValueError: If interval_seconds is negative.
        """
        if interval_seconds < 0:
            raise ValueError(f"interval_seconds must be non-negative, got {interval_seconds}")
        self.interval_seconds = interval_seconds
    
    def __call__(self, attempt: int) -> float:
        """Return the fixed interval.
        
        Args:
            attempt: The attempt number (ignored for fixed intervals).
            
        Returns:
            The fixed interval in seconds.
        """
        return self.interval_seconds


class ExponentialBackoff(IntervalFunction):
    """Exponential backoff interval between retry attempts.
    
    This interval function increases the wait time exponentially with each
    retry attempt using the formula: initial_interval * (multiplier ** (attempt - 1))
    
    Attributes:
        initial_interval: The wait time in seconds for the first retry.
        multiplier: The multiplication factor for each subsequent retry.
        max_interval: Optional maximum wait time in seconds.
    """
    
    def __init__(
        self,
        initial_interval: float,
        multiplier: float = 2.0,
        max_interval: Optional[float] = None
    ):
        """Initialize exponential backoff parameters.
        
        Args:
            initial_interval: The wait time in seconds for the first retry.
                Must be non-negative.
            multiplier: The multiplication factor for each subsequent retry.
                Must be greater than 0.
            max_interval: Optional maximum wait time in seconds. If specified,
                the calculated interval will be capped at this value.
                
        Raises:
            ValueError: If any parameter is invalid.
        """
        if initial_interval < 0:
            raise ValueError(f"initial_interval must be non-negative, got {initial_interval}")
        if multiplier <= 0:
            raise ValueError(f"multiplier must be greater than 0, got {multiplier}")
        if max_interval is not None and max_interval < initial_interval:
            raise ValueError(
                f"max_interval ({max_interval}) must be >= initial_interval ({initial_interval})"
            )
        
        self.initial_interval = initial_interval
        self.multiplier = multiplier
        self.max_interval = max_interval
    
    def __call__(self, attempt: int) -> float:
        """Calculate exponential backoff interval.
        
        Args:
            attempt: The attempt number (1-based).
            
        Returns:
            Wait time in seconds, capped at max_interval if specified.
        """
        interval = self.initial_interval * (self.multiplier ** (attempt - 1))
        if self.max_interval is not None:
            interval = min(interval, self.max_interval)
        return interval


class LinearBackoff(IntervalFunction):
    """Linear backoff interval between retry attempts.
    
    This interval function increases the wait time linearly with each
    retry attempt using the formula: initial_interval + (increment * (attempt - 1))
    
    Attributes:
        initial_interval: The wait time in seconds for the first retry.
        increment: The additional wait time added for each subsequent retry.
        max_interval: Optional maximum wait time in seconds.
    """
    
    def __init__(
        self,
        initial_interval: float,
        increment: float = 1.0,
        max_interval: Optional[float] = None
    ):
        """Initialize linear backoff parameters.
        
        Args:
            initial_interval: The wait time in seconds for the first retry.
                Must be non-negative.
            increment: The additional wait time for each subsequent retry.
                Can be negative for decreasing intervals.
            max_interval: Optional maximum wait time in seconds.
                
        Raises:
            ValueError: If any parameter is invalid.
        """
        if initial_interval < 0:
            raise ValueError(f"initial_interval must be non-negative, got {initial_interval}")
        if max_interval is not None and max_interval < 0:
            raise ValueError(f"max_interval must be non-negative, got {max_interval}")
        
        self.initial_interval = initial_interval
        self.increment = increment
        self.max_interval = max_interval
    
    def __call__(self, attempt: int) -> float:
        """Calculate linear backoff interval.
        
        Args:
            attempt: The attempt number (1-based).
            
        Returns:
            Wait time in seconds, capped at max_interval if specified.
        """
        interval = self.initial_interval + (self.increment * (attempt - 1))
        # Ensure non-negative interval
        interval = max(0, interval)
        if self.max_interval is not None:
            interval = min(interval, self.max_interval)
        return interval


class RandomInterval(IntervalFunction):
    """Random interval between retry attempts.
    
    This interval function returns a random wait time between min_interval
    and max_interval for each retry attempt.
    
    Attributes:
        min_interval: Minimum wait time in seconds.
        max_interval: Maximum wait time in seconds.
    """
    
    def __init__(self, min_interval: float = 0.0, max_interval: float = 1.0):
        """Initialize random interval parameters.
        
        Args:
            min_interval: Minimum wait time in seconds. Must be non-negative.
            max_interval: Maximum wait time in seconds. Must be >= min_interval.
            
        Raises:
            ValueError: If any parameter is invalid.
        """
        if min_interval < 0:
            raise ValueError(f"min_interval must be non-negative, got {min_interval}")
        if max_interval < min_interval:
            raise ValueError(
                f"max_interval ({max_interval}) must be >= min_interval ({min_interval})"
            )
        
        self.min_interval = min_interval
        self.max_interval = max_interval
    
    def __call__(self, attempt: int) -> float:
        """Return a random interval.
        
        Args:
            attempt: The attempt number (ignored for random intervals).
            
        Returns:
            Random wait time between min_interval and max_interval seconds.
        """
        return random.uniform(self.min_interval, self.max_interval)


class ExponentialRandomBackoff(IntervalFunction):
    """Exponential backoff with random jitter.
    
    This interval function combines exponential backoff with random jitter
    to prevent thundering herd problems. The wait time is calculated as:
    random(0, min(max_interval, initial_interval * (multiplier ** (attempt - 1))))
    
    Attributes:
        initial_interval: The base wait time in seconds.
        multiplier: The multiplication factor for exponential growth.
        max_interval: Maximum wait time in seconds.
    """
    
    def __init__(
        self,
        initial_interval: float = 1.0,
        multiplier: float = 2.0,
        max_interval: float = 30.0
    ):
        """Initialize exponential random backoff parameters.
        
        Args:
            initial_interval: The base wait time in seconds. Must be positive.
            multiplier: The multiplication factor. Must be greater than 1.
            max_interval: Maximum wait time in seconds. Must be positive.
            
        Raises:
            ValueError: If any parameter is invalid.
        """
        if initial_interval <= 0:
            raise ValueError(f"initial_interval must be positive, got {initial_interval}")
        if multiplier <= 1:
            raise ValueError(f"multiplier must be greater than 1, got {multiplier}")
        if max_interval <= 0:
            raise ValueError(f"max_interval must be positive, got {max_interval}")
        
        self.initial_interval = initial_interval
        self.multiplier = multiplier
        self.max_interval = max_interval
    
    def __call__(self, attempt: int) -> float:
        """Calculate exponential backoff with random jitter.
        
        Args:
            attempt: The attempt number (1-based).
            
        Returns:
            Random wait time between 0 and the calculated exponential interval.
        """
        exp_interval = self.initial_interval * (self.multiplier ** (attempt - 1))
        max_wait = min(self.max_interval, exp_interval)
        return random.uniform(0, max_wait)


class FibonacciBackoff(IntervalFunction):
    """Fibonacci sequence based backoff interval.
    
    This interval function uses the Fibonacci sequence to determine wait times,
    providing a more gradual increase than exponential backoff.
    
    Attributes:
        initial_interval: The base unit of time in seconds.
        max_interval: Optional maximum wait time in seconds.
    """
    
    def __init__(self, initial_interval: float = 1.0, max_interval: Optional[float] = None):
        """Initialize Fibonacci backoff parameters.
        
        Args:
            initial_interval: The base unit of time in seconds. Must be positive.
            max_interval: Optional maximum wait time in seconds.
            
        Raises:
            ValueError: If any parameter is invalid.
        """
        if initial_interval <= 0:
            raise ValueError(f"initial_interval must be positive, got {initial_interval}")
        if max_interval is not None and max_interval <= 0:
            raise ValueError(f"max_interval must be positive, got {max_interval}")
        
        self.initial_interval = initial_interval
        self.max_interval = max_interval
        self._fib_cache = {1: 1, 2: 1}  # Cache for Fibonacci numbers
    
    def _fibonacci(self, n: int) -> int:
        """Calculate the nth Fibonacci number (1-indexed).
        
        Args:
            n: The position in the Fibonacci sequence (1-indexed).
            
        Returns:
            The nth Fibonacci number.
        """
        if n in self._fib_cache:
            return self._fib_cache[n]
        
        # Calculate and cache
        fib = self._fibonacci(n - 1) + self._fibonacci(n - 2)
        self._fib_cache[n] = fib
        return fib
    
    def __call__(self, attempt: int) -> float:
        """Calculate Fibonacci backoff interval.
        
        Args:
            attempt: The attempt number (1-based).
            
        Returns:
            Wait time based on Fibonacci sequence, capped at max_interval.
        """
        fib_number = self._fibonacci(max(1, attempt))
        interval = self.initial_interval * fib_number
        
        if self.max_interval is not None:
            interval = min(interval, self.max_interval)
        
        return interval