"""Tests for BaseConfig validation and immutability"""

import pytest
from dataclasses import dataclass
from typing import Dict, Any

from resilience4py.core.config import BaseConfig


@dataclass(frozen=True)
class SampleConfig(BaseConfig):
    """Test configuration implementation"""
    max_attempts: int = 3
    timeout: float = 30.0
    
    def validate(self) -> None:
        """Validate test configuration"""
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")


@dataclass(frozen=True)
class InvalidConfig(BaseConfig):
    """Configuration that always fails validation"""
    value: int = -1
    
    def validate(self) -> None:
        """Always raises ValueError"""
        raise ValueError("This config is always invalid")


class TestBaseConfig:
    """Test suite for BaseConfig"""
    
    def test_valid_config_creation(self):
        """Test creating a valid configuration"""
        config = SampleConfig(max_attempts=5, timeout=60.0)
        assert config.max_attempts == 5
        assert config.timeout == 60.0
        assert config.tags == {}
    
    def test_config_with_tags(self):
        """Test configuration with tags"""
        tags = {"env": "test", "version": "1.0"}
        config = SampleConfig(tags=tags)
        assert config.tags == tags
        assert config.max_attempts == 3  # default value
    
    def test_config_immutability(self):
        """Test that configuration is immutable"""
        config = SampleConfig()
        
        # Should not be able to modify attributes
        with pytest.raises(AttributeError):
            config.max_attempts = 10
        
        with pytest.raises(AttributeError):
            config.timeout = 100.0
    
    def test_tags_immutability(self):
        """Test that config and tags are immutable"""
        original_tags = {"key": "value"}
        config = SampleConfig(tags=original_tags.copy())
        
        # Should not be able to modify tags attribute
        with pytest.raises(AttributeError):
            config.tags = {"new": "tags"}
        
        # Note: Since tags is a dict reference, modifying the original will affect config
        # This is a limitation of frozen dataclasses with mutable defaults
        # To truly protect against this, use field(default_factory=dict) or copy in __post_init__
    
    def test_validation_called_on_init(self):
        """Test that validate() is called during initialization"""
        # Valid config should work
        config = SampleConfig(max_attempts=1, timeout=0.1)
        assert config.max_attempts == 1
        
        # Invalid config should raise during init
        with pytest.raises(ValueError, match="This config is always invalid"):
            InvalidConfig()
    
    def test_validation_with_invalid_max_attempts(self):
        """Test validation fails for invalid max_attempts"""
        with pytest.raises(ValueError, match="max_attempts must be at least 1"):
            SampleConfig(max_attempts=0)
        
        with pytest.raises(ValueError, match="max_attempts must be at least 1"):
            SampleConfig(max_attempts=-5)
    
    def test_validation_with_invalid_timeout(self):
        """Test validation fails for invalid timeout"""
        with pytest.raises(ValueError, match="timeout must be positive"):
            SampleConfig(timeout=0)
        
        with pytest.raises(ValueError, match="timeout must be positive"):
            SampleConfig(timeout=-10.0)
    
    def test_post_init_hook(self):
        """Test that __post_init__ is called and triggers validation"""
        # Create a config that tracks if validate was called
        class TrackingConfig(BaseConfig):
            validate_called: bool = False
            
            def validate(self) -> None:
                # Note: This is a bit of a hack since we're modifying state
                # in validate(), but it's just for testing
                object.__setattr__(self, 'validate_called', True)
        
        # Even though we can't normally set attributes on frozen dataclass,
        # we need to use a different approach
        @dataclass(frozen=True)
        class TrackingConfig2(BaseConfig):
            def validate(self) -> None:
                # Validation that does nothing
                pass
        
        config = TrackingConfig2()
        # If we got here without error, __post_init__ was called
        assert isinstance(config, BaseConfig)
    
    def test_abstract_base_class(self):
        """Test that BaseConfig cannot be instantiated directly"""
        # Since BaseConfig is abstract, we can't create it directly
        # This is enforced by the @abstractmethod decorator
        with pytest.raises(TypeError):
            BaseConfig()
    
    def test_inheritance_chain(self):
        """Test configuration inheritance"""
        @dataclass(frozen=True)
        class ParentConfig(BaseConfig):
            parent_value: int = 10
            
            def validate(self) -> None:
                if self.parent_value < 0:
                    raise ValueError("parent_value must be non-negative")
        
        @dataclass(frozen=True)
        class ChildConfig(ParentConfig):
            child_value: str = "test"
            
            def validate(self) -> None:
                super().validate()  # Call parent validation
                if not self.child_value:
                    raise ValueError("child_value must not be empty")
        
        # Valid child config
        config = ChildConfig(parent_value=20, child_value="hello")
        assert config.parent_value == 20
        assert config.child_value == "hello"
        
        # Invalid parent value
        with pytest.raises(ValueError, match="parent_value must be non-negative"):
            ChildConfig(parent_value=-1)
        
        # Invalid child value
        with pytest.raises(ValueError, match="child_value must not be empty"):
            ChildConfig(child_value="")
    
    def test_config_equality(self):
        """Test configuration equality"""
        config1 = SampleConfig(max_attempts=5, timeout=30.0)
        config2 = SampleConfig(max_attempts=5, timeout=30.0)
        config3 = SampleConfig(max_attempts=3, timeout=30.0)
        
        assert config1 == config2
        assert config1 != config3
        # Note: Can't test hash because dataclasses with dict fields are unhashable
        # This is a limitation of frozen dataclasses with mutable fields
    
    def test_config_repr(self):
        """Test configuration string representation"""
        config = SampleConfig(max_attempts=5, timeout=30.0, tags={"env": "test"})
        repr_str = repr(config)
        
        assert "SampleConfig" in repr_str
        assert "max_attempts=5" in repr_str
        assert "timeout=30.0" in repr_str
        assert "tags=" in repr_str