"""
Base configuration classes for resilience patterns

Provides immutable configuration using frozen dataclasses.
"""

from dataclasses import dataclass, field
from typing import TypeVar, Generic, Dict, Any
from abc import ABC, abstractmethod

T = TypeVar('T')


@dataclass(frozen=True)
class BaseConfig(ABC):
    """Base configuration class for all resilience patterns
    
    All configuration classes should inherit from this base class
    and implement the validate() method to ensure configuration
    parameters are valid.
    
    Attributes:
        tags: Optional tags for categorizing or identifying configurations
    """
    tags: Dict[str, Any] = field(default_factory=dict)
    
    @abstractmethod
    def validate(self) -> None:
        """Validate configuration parameters
        
        This method should raise appropriate exceptions if the
        configuration is invalid. It's called automatically when
        the configuration is created.
        
        Raises:
            ValueError: If configuration parameters are invalid
            AssertionError: If assertions fail
        """
        pass
    
    def __post_init__(self) -> None:
        """Called after dataclass initialization to validate config"""
        self.validate()