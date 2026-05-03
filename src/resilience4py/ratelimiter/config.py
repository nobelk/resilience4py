"""
Configuration classes for the Rate Limiter pattern.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, Any


@dataclass(frozen=True)
class RateLimiterConfig:
    """
    Configuration for RateLimiter.
    
    Attributes:
        limit_for_period: The number of permissions available during a limit refresh period.
        limit_refresh_period: The period in which the limit is refreshed.
        timeout_duration: The time a thread waits for a permission before timing out.
        tags: Optional tags for categorization and monitoring.
    """
    limit_for_period: int = 50
    limit_refresh_period: timedelta = timedelta(microseconds=500)
    timeout_duration: timedelta = timedelta(seconds=5)
    tags: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self) -> None:
        """
        Validate configuration parameters.

        Raises:
            ValueError: If any configuration parameter is invalid.
        """
        # Use ValueError so validation runs even under `python -O` (asserts get stripped).
        if self.limit_for_period <= 0:
            raise ValueError("limit_for_period must be greater than 0")
        if self.limit_refresh_period.total_seconds() <= 0:
            raise ValueError("limit_refresh_period must be greater than 0")
        if self.timeout_duration.total_seconds() < 0:
            raise ValueError("timeout_duration must be non-negative")
    
    def __post_init__(self) -> None:
        """Validate configuration on initialization."""
        self.validate()