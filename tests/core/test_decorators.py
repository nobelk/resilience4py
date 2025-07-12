"""Tests for BaseDecorator with sync/async functions and CompositeDecorator"""

import pytest
import asyncio
from functools import wraps
from typing import Any, Callable
from unittest.mock import Mock, AsyncMock, patch

from resilience4py.core.decorators import BaseDecorator, CompositeDecorator


class SampleDecorator(BaseDecorator):
    """Test implementation of BaseDecorator"""
    
    def __init__(self, name: str, prefix: str = "test"):
        super().__init__(name)
        self.prefix = prefix
        self.call_count = 0
    
    async def _execute_async(self, func: Callable, *args, **kwargs) -> Any:
        """Add prefix to result"""
        self.call_count += 1
        
        # Call the function
        if asyncio.iscoroutinefunction(func):
            result = await func(*args, **kwargs)
        else:
            result = func(*args, **kwargs)
        
        # Modify result
        return f"{self.prefix}:{result}"


class ErrorDecorator(BaseDecorator):
    """Decorator that raises errors"""
    
    def __init__(self, name: str, error_msg: str = "Decorator error"):
        super().__init__(name)
        self.error_msg = error_msg
    
    async def _execute_async(self, func: Callable, *args, **kwargs) -> Any:
        """Always raises an error"""
        raise RuntimeError(self.error_msg)


class TestBaseDecorator:
    """Test suite for BaseDecorator"""
    
    def test_decorator_creation(self):
        """Test creating a decorator"""
        decorator = SampleDecorator("my_decorator", "prefix")
        assert decorator.name == "my_decorator"
        assert decorator.prefix == "prefix"
        assert decorator.call_count == 0
    
    def test_decorate_sync_function(self):
        """Test decorating a synchronous function"""
        decorator = SampleDecorator("test")
        
        @decorator
        def sync_func(x: int) -> str:
            return f"result_{x}"
        
        # Call decorated function
        result = sync_func(42)
        
        assert result == "test:result_42"
        assert decorator.call_count == 1
    
    @pytest.mark.asyncio
    async def test_decorate_async_function(self):
        """Test decorating an asynchronous function"""
        decorator = SampleDecorator("test")
        
        @decorator
        async def async_func(x: int) -> str:
            await asyncio.sleep(0.01)
            return f"result_{x}"
        
        # Call decorated function
        result = await async_func(42)
        
        assert result == "test:result_42"
        assert decorator.call_count == 1
    
    def test_multiple_decorations(self):
        """Test using same decorator on multiple functions"""
        decorator = SampleDecorator("shared", "shared")
        
        @decorator
        def func1():
            return "one"
        
        @decorator
        def func2():
            return "two"
        
        assert func1() == "shared:one"
        assert func2() == "shared:two"
        assert decorator.call_count == 2
    
    def test_decorator_preserves_function_metadata(self):
        """Test that decorator preserves function metadata"""
        decorator = SampleDecorator("test")
        
        def original_func(x: int, y: str = "default") -> str:
            """Original function docstring"""
            return f"{x}:{y}"
        
        decorated_func = decorator(original_func)
        
        # Check metadata is preserved
        assert decorated_func.__name__ == "original_func"
        assert decorated_func.__doc__ == "Original function docstring"
        assert decorated_func.__module__ == original_func.__module__
    
    def test_sync_function_with_args_kwargs(self):
        """Test sync function with various arguments"""
        decorator = SampleDecorator("test")
        
        @decorator
        def func(a, b, c=3, *args, **kwargs):
            result = f"a={a}, b={b}, c={c}, args={args}, kwargs={kwargs}"
            return result
        
        result = func(1, 2, 4, 5, 6, x=7, y=8)
        expected = "test:a=1, b=2, c=4, args=(5, 6), kwargs={'x': 7, 'y': 8}"
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_async_function_with_args_kwargs(self):
        """Test async function with various arguments"""
        decorator = SampleDecorator("test")
        
        @decorator
        async def func(a, b, c=3, *args, **kwargs):
            await asyncio.sleep(0.01)
            result = f"a={a}, b={b}, c={c}, args={args}, kwargs={kwargs}"
            return result
        
        result = await func(1, 2, 4, 5, 6, x=7, y=8)
        expected = "test:a=1, b=2, c=4, args=(5, 6), kwargs={'x': 7, 'y': 8}"
        assert result == expected
    
    def test_sync_function_exception_propagation(self):
        """Test that exceptions are propagated from sync functions"""
        decorator = SampleDecorator("test")
        
        @decorator
        def func():
            raise ValueError("Function error")
        
        with pytest.raises(ValueError, match="Function error"):
            func()
    
    @pytest.mark.asyncio
    async def test_async_function_exception_propagation(self):
        """Test that exceptions are propagated from async functions"""
        decorator = SampleDecorator("test")
        
        @decorator
        async def func():
            raise ValueError("Async function error")
        
        with pytest.raises(ValueError, match="Async function error"):
            await func()
    
    def test_decorator_exception_propagation(self):
        """Test that decorator exceptions are propagated"""
        decorator = ErrorDecorator("error")
        
        @decorator
        def func():
            return "never reached"
        
        with pytest.raises(RuntimeError, match="Decorator error"):
            func()
    
    def test_sync_in_event_loop(self):
        """Test sync function when event loop is already running"""
        decorator = SampleDecorator("test")
        
        @decorator
        def sync_func():
            return "sync_result"
        
        async def run_in_loop():
            # When called from within an event loop, should use thread pool
            result = sync_func()
            return result
        
        # Run the test in an event loop
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(run_in_loop())
        loop.close()
        
        assert result == "test:sync_result"
    
    def test_repr(self):
        """Test string representation"""
        decorator = SampleDecorator("my_test_decorator")
        assert repr(decorator) == "SampleDecorator(name='my_test_decorator')"
    
    def test_abstract_base_class(self):
        """Test that BaseDecorator cannot be instantiated directly"""
        with pytest.raises(TypeError):
            BaseDecorator("test")
    
    def test_nested_decoration(self):
        """Test nested decorators of same type"""
        decorator1 = SampleDecorator("outer", "OUTER")
        decorator2 = SampleDecorator("inner", "INNER")
        
        @decorator1
        @decorator2
        def func():
            return "result"
        
        # Inner decorator applies first, then outer
        result = func()
        assert result == "OUTER:INNER:result"
        assert decorator1.call_count == 1
        assert decorator2.call_count == 1


class TestCompositeDecorator:
    """Test suite for CompositeDecorator"""
    
    @pytest.mark.asyncio
    async def test_composite_creation(self):
        """Test creating a composite decorator"""
        dec1 = SampleDecorator("dec1", "A")
        dec2 = SampleDecorator("dec2", "B")
        
        composite = CompositeDecorator("composite", [dec1, dec2])
        
        assert composite.name == "composite"
        assert composite.decorators == [dec1, dec2]
    
    @pytest.mark.asyncio
    async def test_composite_execution_order(self):
        """Test that decorators execute in the correct order"""
        dec1 = SampleDecorator("dec1", "FIRST")
        dec2 = SampleDecorator("dec2", "SECOND")
        dec3 = SampleDecorator("dec3", "THIRD")
        
        composite = CompositeDecorator("composite", [dec1, dec2, dec3])
        
        @composite
        async def func():
            return "RESULT"
        
        result = await func()
        
        # Decorators should apply in order: first, second, third
        assert result == "FIRST:SECOND:THIRD:RESULT"
        
        # Each decorator should be called once
        assert dec1.call_count == 1
        assert dec2.call_count == 1
        assert dec3.call_count == 1
    
    def test_composite_with_sync_function(self):
        """Test composite decorator with sync function"""
        dec1 = SampleDecorator("dec1", "X")
        dec2 = SampleDecorator("dec2", "Y")
        
        composite = CompositeDecorator("composite", [dec1, dec2])
        
        @composite
        def func(value):
            return f"value={value}"
        
        result = func(42)
        assert result == "X:Y:value=42"
    
    @pytest.mark.asyncio
    async def test_composite_error_handling(self):
        """Test error handling in composite decorators"""
        dec1 = SampleDecorator("dec1", "A")
        dec2 = ErrorDecorator("error", "Middle error")
        dec3 = SampleDecorator("dec3", "C")
        
        composite = CompositeDecorator("composite", [dec1, dec2, dec3])
        
        @composite
        async def func():
            return "result"
        
        # Error from middle decorator should propagate
        with pytest.raises(RuntimeError, match="Middle error"):
            await func()
        
        # First decorator should have been called
        assert dec1.call_count == 1
        # Third decorator should not have been called
        assert dec3.call_count == 0
    
    @pytest.mark.asyncio
    async def test_empty_composite(self):
        """Test composite with no decorators"""
        composite = CompositeDecorator("empty", [])
        
        @composite
        async def func(x):
            return x * 2
        
        result = await func(21)
        assert result == 42  # Function executes normally
    
    @pytest.mark.asyncio
    async def test_composite_with_single_decorator(self):
        """Test composite with single decorator"""
        dec = SampleDecorator("single", "ONLY")
        composite = CompositeDecorator("composite", [dec])
        
        @composite
        async def func():
            return "value"
        
        result = await func()
        assert result == "ONLY:value"
    
    def test_composite_repr(self):
        """Test composite string representation"""
        dec1 = SampleDecorator("dec1")
        dec2 = SampleDecorator("dec2")
        composite = CompositeDecorator("my_composite", [dec1, dec2])
        
        assert repr(composite) == "CompositeDecorator(name='my_composite')"
    
    @pytest.mark.asyncio
    async def test_nested_composites(self):
        """Test composites containing other composites"""
        # Create individual decorators
        dec1 = SampleDecorator("dec1", "A")
        dec2 = SampleDecorator("dec2", "B")
        dec3 = SampleDecorator("dec3", "C")
        dec4 = SampleDecorator("dec4", "D")
        
        # Create nested composites
        inner_composite = CompositeDecorator("inner", [dec2, dec3])
        outer_composite = CompositeDecorator("outer", [dec1, inner_composite, dec4])
        
        @outer_composite
        async def func():
            return "RESULT"
        
        result = await func()
        
        # Should apply all decorators in order
        assert result == "A:B:C:D:RESULT"
    
    @pytest.mark.asyncio
    async def test_composite_with_stateful_decorators(self):
        """Test composite with decorators that maintain state"""
        # Create decorators that count calls
        decorators = [SampleDecorator(f"dec{i}", f"D{i}") for i in range(3)]
        composite = CompositeDecorator("composite", decorators)
        
        @composite
        async def func(x):
            return x
        
        # Call multiple times
        for i in range(5):
            result = await func(i)
            expected = f"D0:D1:D2:{i}"
            assert result == expected
        
        # Each decorator should have been called 5 times
        for dec in decorators:
            assert dec.call_count == 5
    
    @pytest.mark.asyncio
    async def test_composite_preserves_function_metadata(self):
        """Test that composite preserves function metadata"""
        composite = CompositeDecorator("comp", [SampleDecorator("test")])
        
        async def original(x: int) -> int:
            """Original docstring"""
            return x * 2
        
        decorated = composite(original)
        
        assert decorated.__name__ == "original"
        assert decorated.__doc__ == "Original docstring"