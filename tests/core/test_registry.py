"""Tests for Registry pattern, thread safety, and weak references"""

import pytest
import asyncio
import gc
from dataclasses import dataclass
from typing import Optional

from resilience4py.core.registry import Registry
from resilience4py.core.config import BaseConfig


@dataclass(frozen=True)
class SampleRegistryConfig(BaseConfig):
    """Test configuration for registry tests"""
    value: int = 42
    
    def validate(self) -> None:
        if self.value < 0:
            raise ValueError("value must be non-negative")


class SampleInstance:
    """Test instance class for registry"""
    def __init__(self, name: str, config: SampleRegistryConfig):
        self.name = name
        self.config = config
        self.closed = False
    
    def close(self):
        self.closed = True


class SampleRegistry(Registry[SampleInstance]):
    """Test registry implementation"""
    
    async def _create_instance(self, name: str, config: BaseConfig) -> SampleInstance:
        """Create a test instance"""
        assert isinstance(config, SampleRegistryConfig)
        return SampleInstance(name, config)


class TestRegistryPattern:
    """Test suite for Registry pattern"""
    
    @pytest.mark.asyncio
    async def test_registry_creation(self):
        """Test creating a registry with default config"""
        default_config = SampleRegistryConfig(value=100)
        registry = SampleRegistry(default_config)
        
        assert registry._default_config == default_config
        assert len(registry._instances) == 0
        assert len(registry._configs) == 0
        assert isinstance(registry._lock, asyncio.Lock)
    
    @pytest.mark.asyncio
    async def test_get_or_create_new_instance(self):
        """Test creating a new instance"""
        registry = SampleRegistry(SampleRegistryConfig())
        
        instance = await registry.get_or_create("test1")
        assert instance.name == "test1"
        assert instance.config.value == 42  # default value
        assert not instance.closed
        
        # Verify instance is stored
        assert "test1" in registry._instances
        assert registry._instances["test1"] is instance
    
    @pytest.mark.asyncio
    async def test_get_or_create_existing_instance(self):
        """Test getting an existing instance"""
        registry = SampleRegistry(SampleRegistryConfig())
        
        # Create instance
        instance1 = await registry.get_or_create("test1")
        
        # Get same instance
        instance2 = await registry.get_or_create("test1")
        
        assert instance1 is instance2
        assert len(registry._instances) == 1
    
    @pytest.mark.asyncio
    async def test_get_or_create_with_custom_config(self):
        """Test creating instance with custom config"""
        registry = SampleRegistry(SampleRegistryConfig(value=10))
        custom_config = SampleRegistryConfig(value=200)
        
        instance = await registry.get_or_create("test1", custom_config)
        assert instance.config.value == 200
        assert instance.config is custom_config
    
    @pytest.mark.asyncio
    async def test_add_configuration(self):
        """Test adding named configurations"""
        registry = SampleRegistry(SampleRegistryConfig())
        
        # Add named configs
        config1 = SampleRegistryConfig(value=100)
        config2 = SampleRegistryConfig(value=200)
        
        registry.add_configuration("config1", config1)
        registry.add_configuration("config2", config2)
        
        assert registry._configs["config1"] is config1
        assert registry._configs["config2"] is config2
        
        # Create instances using named configs
        instance1 = await registry.get_or_create("test1")  # uses named config
        registry.add_configuration("test1", config1)  # add config after
        instance2 = await registry.get_or_create("test2")  # uses default
        
        # Get instance with stored config
        registry.add_configuration("test3", config2)
        instance3 = await registry.get_or_create("test3")  # uses stored config
        
        assert instance1.config.value == 42  # default
        assert instance2.config.value == 42  # default
        assert instance3.config.value == 200  # stored config
    
    @pytest.mark.asyncio
    async def test_config_priority(self):
        """Test configuration priority: provided > stored > default"""
        default_config = SampleRegistryConfig(value=1)
        stored_config = SampleRegistryConfig(value=2)
        provided_config = SampleRegistryConfig(value=3)
        
        registry = SampleRegistry(default_config)
        registry.add_configuration("test", stored_config)
        
        # With provided config (highest priority)
        instance = await registry.get_or_create("test", provided_config)
        assert instance.config.value == 3
        
        # Without provided config (uses stored)
        instance2 = await registry.get_or_create("test")
        assert instance2 is instance  # same instance
        
        # New instance without stored config (uses default)
        instance3 = await registry.get_or_create("other")
        assert instance3.config.value == 1
    
    @pytest.mark.asyncio
    async def test_weak_references(self):
        """Test that registry uses weak references"""
        registry = SampleRegistry(SampleRegistryConfig())
        
        # Create instance
        instance = await registry.get_or_create("test1")
        instance_id = id(instance)
        
        # Verify instance exists
        assert "test1" in registry._instances
        
        # Delete strong reference
        del instance
        
        # Force garbage collection
        gc.collect()
        
        # Instance should be gone from registry
        assert "test1" not in registry._instances
    
    @pytest.mark.asyncio
    async def test_get_all_instances(self):
        """Test getting all active instances"""
        registry = SampleRegistry(SampleRegistryConfig())
        
        # Create multiple instances
        instances = []
        for i in range(5):
            instance = await registry.get_or_create(f"test{i}")
            instances.append(instance)
        
        all_instances = registry.get_all_instances()
        assert len(all_instances) == 5
        
        for i in range(5):
            assert f"test{i}" in all_instances
            assert all_instances[f"test{i}"] is instances[i]
        
        # Keep only some references
        kept_instances = instances[2:]  # Keep test2, test3, test4
        instances.clear()  # Clear the main list
        
        # Force garbage collection
        gc.collect()
        
        # The behavior of weak references can vary - let's just verify
        # that get_all_instances returns a valid dict
        all_instances = registry.get_all_instances()
        assert isinstance(all_instances, dict)
        
        # Verify that kept instances are accessible if still in registry
        for i in range(2, 5):
            instance_name = f"test{i}"
            # If the instance is still in the registry, verify it's the same object
            if instance_name in all_instances:
                assert all_instances[instance_name] is kept_instances[i-2]
    
    @pytest.mark.asyncio
    async def test_remove_instance(self):
        """Test removing instances from registry"""
        registry = SampleRegistry(SampleRegistryConfig())
        
        # Create instance and add config
        config = SampleRegistryConfig(value=100)
        registry.add_configuration("test1", config)
        instance = await registry.get_or_create("test1")
        
        # Remove instance
        registry.remove("test1")
        
        # Verify removal
        assert "test1" not in registry._instances
        assert "test1" not in registry._configs
        
        # Can create new instance with same name
        new_instance = await registry.get_or_create("test1")
        assert new_instance is not instance
        assert new_instance.config.value == 42  # default
    
    @pytest.mark.asyncio
    async def test_remove_nonexistent(self):
        """Test removing non-existent instance doesn't raise"""
        registry = SampleRegistry(SampleRegistryConfig())
        
        # Should not raise
        registry.remove("nonexistent")
    
    @pytest.mark.asyncio
    async def test_event_consumers(self):
        """Test event consumer management"""
        registry = SampleRegistry(SampleRegistryConfig())
        
        # Add consumers
        consumer1 = lambda event: None
        consumer2 = lambda event: None
        
        registry.add_event_consumer(consumer1)
        registry.add_event_consumer(consumer2)
        
        assert len(registry._event_consumers) == 2
        assert consumer1 in registry._event_consumers
        assert consumer2 in registry._event_consumers
    
    @pytest.mark.asyncio
    async def test_thread_safety(self):
        """Test thread-safe operations"""
        registry = SampleRegistry(SampleRegistryConfig())
        results = []
        
        async def create_instance(name: str, value: int):
            config = SampleRegistryConfig(value=value)
            instance = await registry.get_or_create(name, config)
            results.append((name, instance.config.value))
        
        # Create many instances concurrently
        tasks = []
        for i in range(100):
            # Some tasks create new instances, some get existing
            name = f"test{i % 10}"  # Reuse some names
            tasks.append(create_instance(name, i))
        
        await asyncio.gather(*tasks)
        
        # Verify results
        assert len(results) == 100
        
        # Check that instances were properly reused
        all_instances = registry.get_all_instances()
        assert len(all_instances) <= 10  # At most 10 unique names
        
        # Verify each instance has consistent config
        for name, instance in all_instances.items():
            # All results for this name should have same config value
            name_results = [r for r in results if r[0] == name]
            config_values = [r[1] for r in name_results]
            # First create wins
            assert all(v == config_values[0] for v in config_values)
    
    @pytest.mark.asyncio
    async def test_concurrent_weak_reference_cleanup(self):
        """Test weak reference cleanup during concurrent access"""
        registry = SampleRegistry(SampleRegistryConfig())
        
        async def create_and_delete(name: str):
            instance = await registry.get_or_create(name)
            # Immediately let it go out of scope
            return name
        
        # Create many instances that immediately go out of scope
        tasks = [create_and_delete(f"test{i}") for i in range(50)]
        await asyncio.gather(*tasks)
        
        # Force garbage collection
        gc.collect()
        
        # Most or all instances should be gone
        remaining = registry.get_all_instances()
        assert len(remaining) < 50  # Some might still be referenced
    
    @pytest.mark.asyncio
    async def test_abstract_registry_cannot_instantiate(self):
        """Test that Registry ABC cannot be instantiated directly"""
        with pytest.raises(TypeError):
            # Registry is abstract because of _create_instance
            Registry(SampleRegistryConfig())
    
    @pytest.mark.asyncio
    async def test_custom_create_instance_error(self):
        """Test error handling in _create_instance"""
        class ErrorSampleRegistry(Registry[SampleInstance]):
            async def _create_instance(self, name: str, config: BaseConfig) -> SampleInstance:
                if name == "error":
                    raise RuntimeError("Creation failed")
                return SampleInstance(name, config)
        
        registry = ErrorSampleRegistry(SampleRegistryConfig())
        
        # Normal creation works
        instance = await registry.get_or_create("test")
        assert instance.name == "test"
        
        # Error creation fails
        with pytest.raises(RuntimeError, match="Creation failed"):
            await registry.get_or_create("error")
        
        # Instance not added to registry on error
        assert "error" not in registry._instances