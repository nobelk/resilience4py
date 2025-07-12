"""
Generic registry pattern for managing instances

Provides a thread-safe registry for creating and managing
instances of resilience patterns.
"""

from typing import Dict, Optional, Callable, List, TypeVar, Generic
from weakref import WeakValueDictionary
import asyncio
from abc import ABC, abstractmethod

from resilience4py.core.config import BaseConfig

T = TypeVar('T')


class Registry(Generic[T], ABC):
    """Generic registry for managing instances
    
    This registry provides a centralized way to create and manage
    instances of resilience patterns. It uses weak references to
    allow garbage collection of unused instances.
    
    Type Parameters:
        T: The type of instances managed by this registry
        
    Attributes:
        _default_config: Default configuration for new instances
        _instances: Weak references to created instances
        _configs: Stored configurations by name
        _event_consumers: List of event consumer callbacks
        _lock: Async lock for thread-safe operations
    """
    
    def __init__(self, default_config: BaseConfig):
        """Initialize registry with default configuration
        
        Args:
            default_config: Default configuration to use for new instances
        """
        self._default_config = default_config
        self._instances: WeakValueDictionary[str, T] = WeakValueDictionary()
        self._configs: Dict[str, BaseConfig] = {}
        self._event_consumers: List[Callable] = []
        self._lock = asyncio.Lock()
    
    async def get_or_create(self, name: str, config: Optional[BaseConfig] = None) -> T:
        """Get existing instance or create new one
        
        This method is thread-safe and ensures only one instance
        exists for each name.
        
        Args:
            name: Unique name for the instance
            config: Optional configuration (uses stored or default if not provided)
            
        Returns:
            The instance associated with the given name
        """
        async with self._lock:
            if name in self._instances:
                return self._instances[name]
            
            final_config = config or self._configs.get(name) or self._default_config
            instance = await self._create_instance(name, final_config)
            self._instances[name] = instance
            return instance
    
    @abstractmethod
    async def _create_instance(self, name: str, config: BaseConfig) -> T:
        """Factory method to create new instances
        
        This method must be implemented by subclasses to create
        the specific type of instance managed by the registry.
        
        Args:
            name: Unique name for the instance
            config: Configuration to use for the instance
            
        Returns:
            A new instance of type T
        """
        pass
    
    def add_configuration(self, name: str, config: BaseConfig) -> None:
        """Add a named configuration to the registry
        
        Args:
            name: Name to associate with the configuration
            config: Configuration to store
        """
        self._configs[name] = config
    
    def add_event_consumer(self, consumer: Callable) -> None:
        """Add an event consumer to receive events from all instances
        
        Args:
            consumer: Callback function to receive events
        """
        self._event_consumers.append(consumer)
    
    def get_all_instances(self) -> Dict[str, T]:
        """Get all active instances in the registry
        
        Returns:
            Dictionary mapping names to instances
        """
        return dict(self._instances)
    
    def remove(self, name: str) -> None:
        """Remove an instance from the registry
        
        Args:
            name: Name of the instance to remove
        """
        if name in self._instances:
            del self._instances[name]
        if name in self._configs:
            del self._configs[name]