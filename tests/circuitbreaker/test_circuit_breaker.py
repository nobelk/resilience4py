"""Tests for main CircuitBreaker class."""

import asyncio
import time
from datetime import timedelta
from unittest.mock import Mock, AsyncMock, patch
import pytest

from resilience4py.circuitbreaker.circuit_breaker import (
    CircuitBreaker, CallNotPermittedException
)
from resilience4py.circuitbreaker.config import CircuitBreakerConfig, SlidingWindowType
from resilience4py.circuitbreaker.events import (
    CircuitBreakerState,
    CircuitBreakerOnSuccessEvent,
    CircuitBreakerOnErrorEvent,
    CircuitBreakerOnCallNotPermittedEvent,
    CircuitBreakerOnStateTransitionEvent,
    CircuitBreakerOnResetEvent,
    CircuitBreakerOnIgnoredErrorEvent
)


class TestCircuitBreakerInitialization:
    """Test CircuitBreaker initialization."""
    
    def test_default_initialization(self):
        """Test circuit breaker with default config."""
        cb = CircuitBreaker("test-cb")
        
        assert cb.name == "test-cb"
        assert cb.state_name == CircuitBreakerState.CLOSED
        assert isinstance(cb.config, CircuitBreakerConfig)
        assert cb.config.failure_rate_threshold == 50.0
    
    def test_custom_config_initialization(self):
        """Test circuit breaker with custom config."""
        config = CircuitBreakerConfig(
            failure_rate_threshold=75.0,
            sliding_window_size=50,
            sliding_window_type=SlidingWindowType.TIME_BASED
        )
        cb = CircuitBreaker("test-cb", config)
        
        assert cb.name == "test-cb"
        assert cb.config.failure_rate_threshold == 75.0
        assert cb.config.sliding_window_size == 50
        assert cb.config.sliding_window_type == SlidingWindowType.TIME_BASED
    
    @pytest.mark.asyncio
    async def test_get_or_create_singleton(self):
        """Test get_or_create returns same instance."""
        config = CircuitBreakerConfig(failure_rate_threshold=60.0)
        
        cb1 = await CircuitBreaker.get_or_create("singleton-test", config)
        cb2 = await CircuitBreaker.get_or_create("singleton-test")
        
        assert cb1 is cb2
        assert cb1.config.failure_rate_threshold == 60.0
    
    @pytest.mark.asyncio
    async def test_get_or_create_different_names(self):
        """Test get_or_create with different names creates different instances."""
        cb1 = await CircuitBreaker.get_or_create("cb1")
        cb2 = await CircuitBreaker.get_or_create("cb2")
        
        assert cb1 is not cb2
        assert cb1.name == "cb1"
        assert cb2.name == "cb2"


class TestCircuitBreakerDecorator:
    """Test CircuitBreaker as decorator."""
    
    @pytest.mark.asyncio
    async def test_decorate_async_function(self):
        """Test decorating async function."""
        cb = CircuitBreaker("test-cb")
        
        @cb
        async def async_function(x, y):
            return x + y
        
        result = await async_function(5, 3)
        assert result == 8
        
        # Check metrics were recorded
        metrics = await cb.get_metrics()
        assert metrics['total_calls'] == 1
        assert metrics['successful_calls'] == 1
        assert metrics['failed_calls'] == 0
    
    def test_decorate_sync_function(self):
        """Test decorating sync function."""
        cb = CircuitBreaker("test-cb")
        
        @cb
        def sync_function(x, y):
            return x * y
        
        result = sync_function(4, 7)
        assert result == 28
        
        # Check metrics were recorded
        metrics = asyncio.run(cb.get_metrics())
        assert metrics['total_calls'] == 1
        assert metrics['successful_calls'] == 1
    
    @pytest.mark.asyncio
    async def test_decorate_method(self):
        """Test decorating instance method."""
        cb = CircuitBreaker("test-cb")
        
        class TestClass:
            @cb
            async def method(self, value):
                return value * 2
        
        obj = TestClass()
        result = await obj.method(10)
        assert result == 20
    
    @pytest.mark.asyncio
    async def test_alternative_decoration_syntax(self):
        """Test using decorate() method."""
        cb = CircuitBreaker("test-cb")
        
        async def my_function():
            return "success"
        
        decorated = cb.decorate(my_function)
        result = await decorated()
        assert result == "success"


class TestCircuitBreakerExecution:
    """Test CircuitBreaker execution behavior."""
    
    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Test successful function execution."""
        cb = CircuitBreaker("test-cb")
        events = []
        
        cb.on_event(CircuitBreakerOnSuccessEvent, lambda e: events.append(e))
        
        @cb
        async def successful_function():
            await asyncio.sleep(0.01)
            return "success"
        
        result = await successful_function()
        assert result == "success"
        
        # Check event was emitted
        assert len(events) == 1
        assert isinstance(events[0], CircuitBreakerOnSuccessEvent)
        assert events[0].circuit_breaker_name == "test-cb"
        assert events[0].duration_ms > 0
    
    @pytest.mark.asyncio
    async def test_failed_execution(self):
        """Test failed function execution."""
        cb = CircuitBreaker("test-cb")
        events = []
        
        cb.on_event(CircuitBreakerOnErrorEvent, lambda e: events.append(e))
        
        @cb
        async def failing_function():
            await asyncio.sleep(0.01)
            raise RuntimeError("test error")
        
        with pytest.raises(RuntimeError, match="test error"):
            await failing_function()
        
        # Check event was emitted
        assert len(events) == 1
        assert isinstance(events[0], CircuitBreakerOnErrorEvent)
        assert events[0].circuit_breaker_name == "test-cb"
        assert events[0].duration_ms > 0
        assert isinstance(events[0].exception, RuntimeError)
    
    @pytest.mark.asyncio
    async def test_ignored_exception(self):
        """Test execution with ignored exception."""
        config = CircuitBreakerConfig(ignore_exceptions=[ValueError])
        cb = CircuitBreaker("test-cb", config)
        events = []
        
        cb.on_event(CircuitBreakerOnIgnoredErrorEvent, lambda e: events.append(e))
        
        @cb
        async def function_with_ignored_error():
            raise ValueError("ignored error")
        
        with pytest.raises(ValueError):
            await function_with_ignored_error()
        
        # Check ignored error event was emitted
        assert len(events) == 1
        assert isinstance(events[0], CircuitBreakerOnIgnoredErrorEvent)
        assert isinstance(events[0].exception, ValueError)
        
        # Check metrics - should count as success
        metrics = await cb.get_metrics()
        assert metrics['failed_calls'] == 0
        assert metrics['successful_calls'] == 1
    
    @pytest.mark.asyncio
    async def test_call_not_permitted(self):
        """Test execution when call is not permitted."""
        cb = CircuitBreaker("test-cb")
        events = []
        
        cb.on_event(CircuitBreakerOnCallNotPermittedEvent, lambda e: events.append(e))
        
        # Force circuit breaker open
        await cb.force_open()
        
        @cb
        async def blocked_function():
            return "should not execute"
        
        with pytest.raises(CallNotPermittedException) as exc_info:
            await blocked_function()
        
        assert "CircuitBreaker 'test-cb' is FORCED_OPEN" in str(exc_info.value)
        
        # Check event was emitted
        assert len(events) == 1
        assert isinstance(events[0], CircuitBreakerOnCallNotPermittedEvent)
    
    @pytest.mark.asyncio
    async def test_sync_function_in_async_context(self):
        """Test sync function execution in async context."""
        cb = CircuitBreaker("test-cb")
        
        @cb
        def sync_function():
            time.sleep(0.01)  # Blocking sleep
            return "sync result"
        
        # Should work in async context using executor
        result = await asyncio.get_event_loop().run_in_executor(
            None, sync_function
        )
        assert result == "sync result"


class TestCircuitBreakerStateManagement:
    """Test CircuitBreaker state management."""
    
    @pytest.mark.asyncio
    async def test_automatic_state_transitions(self):
        """Test automatic state transitions based on metrics."""
        config = CircuitBreakerConfig(
            failure_rate_threshold=50.0,
            minimum_number_of_calls=4,
            sliding_window_size=4,
            wait_duration_in_open_state=timedelta(milliseconds=50),
            automatic_transition_from_open_to_half_open=True,
            permitted_calls_in_half_open=2
        )
        cb = CircuitBreaker("test-cb", config)
        state_transitions = []
        
        cb.on_event(
            CircuitBreakerOnStateTransitionEvent,
            lambda e: state_transitions.append((e.from_state, e.to_state))
        )
        
        @cb
        async def unreliable_function(should_fail):
            if should_fail:
                raise RuntimeError("failure")
            return "success"
        
        # Start in CLOSED state
        assert cb.state_name == CircuitBreakerState.CLOSED
        
        # Make calls to trigger transition to OPEN (50% failure rate)
        await unreliable_function(False)
        await unreliable_function(False)
        with pytest.raises(RuntimeError):
            await unreliable_function(True)
        with pytest.raises(RuntimeError):
            await unreliable_function(True)
        
        # Should transition to OPEN
        assert cb.state_name == CircuitBreakerState.OPEN
        assert (CircuitBreakerState.CLOSED, CircuitBreakerState.OPEN) in state_transitions
        
        # Calls should be rejected
        with pytest.raises(CallNotPermittedException):
            await unreliable_function(False)
        
        # Wait for automatic transition to HALF_OPEN
        await asyncio.sleep(0.06)
        
        # Next call should be permitted (HALF_OPEN state)
        result = await unreliable_function(False)
        assert result == "success"
        assert cb.state_name == CircuitBreakerState.HALF_OPEN
        
        # One more successful call should transition back to CLOSED
        await unreliable_function(False)
        assert cb.state_name == CircuitBreakerState.CLOSED
        assert (CircuitBreakerState.HALF_OPEN, CircuitBreakerState.CLOSED) in state_transitions
    
    @pytest.mark.asyncio
    async def test_manual_state_transitions(self):
        """Test manual state transition methods."""
        cb = CircuitBreaker("test-cb")
        
        # Test reset
        await cb.reset()
        assert cb.state_name == CircuitBreakerState.CLOSED
        metrics = await cb.get_metrics()
        assert metrics['total_calls'] == 0
        
        # Test disable
        await cb.disable()
        assert cb.state_name == CircuitBreakerState.DISABLED
        
        # Test force open
        await cb.force_open()
        assert cb.state_name == CircuitBreakerState.FORCED_OPEN
        
        # Test close
        await cb.close()
        assert cb.state_name == CircuitBreakerState.CLOSED
        
        # Test metrics only
        await cb.transition_to_metrics_only()
        assert cb.state_name == CircuitBreakerState.METRICS_ONLY
    
    @pytest.mark.asyncio
    async def test_no_duplicate_state_transitions(self):
        """Test that transitioning to same state is no-op."""
        cb = CircuitBreaker("test-cb")
        transitions = []
        
        cb.on_event(
            CircuitBreakerOnStateTransitionEvent,
            lambda e: transitions.append(e)
        )
        
        # Already in CLOSED
        await cb.transition_to_state(CircuitBreakerState.CLOSED)
        assert len(transitions) == 0
        
        # Transition to OPEN
        await cb.transition_to_state(CircuitBreakerState.OPEN)
        assert len(transitions) == 1
        
        # Try to transition to OPEN again
        await cb.transition_to_state(CircuitBreakerState.OPEN)
        assert len(transitions) == 1  # No new transition


class TestCircuitBreakerMetrics:
    """Test CircuitBreaker metrics collection."""
    
    @pytest.mark.asyncio
    async def test_get_metrics(self):
        """Test getting circuit breaker metrics."""
        cb = CircuitBreaker("test-cb")
        
        @cb
        async def test_function(should_fail=False):
            await asyncio.sleep(0.01)
            if should_fail:
                raise RuntimeError("test error")
            return "success"
        
        # Make some calls
        await test_function()
        await test_function()
        with pytest.raises(RuntimeError):
            await test_function(should_fail=True)
        
        metrics = await cb.get_metrics()
        
        assert metrics['name'] == "test-cb"
        assert metrics['state'] == "CLOSED"
        assert metrics['total_calls'] == 3
        assert metrics['successful_calls'] == 2
        assert metrics['failed_calls'] == 1
        assert metrics['failure_rate'] == pytest.approx(33.33, 0.1)
        assert metrics['average_duration_ms'] > 0
    
    @pytest.mark.asyncio
    async def test_slow_call_detection(self):
        """Test slow call detection in metrics."""
        config = CircuitBreakerConfig(
            slow_call_duration_threshold=timedelta(milliseconds=50)
        )
        cb = CircuitBreaker("test-cb", config)
        
        @cb
        async def variable_speed_function(delay):
            await asyncio.sleep(delay)
            return "done"
        
        # Fast call
        await variable_speed_function(0.01)
        
        # Slow call
        await variable_speed_function(0.06)
        
        metrics = await cb.get_metrics()
        assert metrics['slow_calls'] == 1
        assert metrics['slow_call_rate'] == 50.0


class TestCircuitBreakerEvents:
    """Test CircuitBreaker event system."""
    
    @pytest.mark.asyncio
    async def test_event_listener_registration(self):
        """Test registering and removing event listeners."""
        cb = CircuitBreaker("test-cb")
        events = []
        
        def listener(event):
            events.append(event)
        
        # Register listener
        cb.on_event(CircuitBreakerOnSuccessEvent, listener)
        
        @cb
        async def test_function():
            return "success"
        
        await test_function()
        assert len(events) == 1
        
        # Remove listener
        cb.remove_event_listener(CircuitBreakerOnSuccessEvent, listener)
        
        await test_function()
        assert len(events) == 1  # No new event
    
    @pytest.mark.asyncio
    async def test_async_event_listener(self):
        """Test async event listeners."""
        cb = CircuitBreaker("test-cb")
        events = []
        
        async def async_listener(event):
            await asyncio.sleep(0.001)
            events.append(event)
        
        cb.on_event(CircuitBreakerOnSuccessEvent, async_listener)
        
        @cb
        async def test_function():
            return "success"
        
        await test_function()
        await asyncio.sleep(0.01)  # Give async listener time to complete
        
        assert len(events) == 1
    
    @pytest.mark.asyncio
    async def test_event_listener_exception_handling(self):
        """Test that exceptions in event listeners don't affect execution."""
        cb = CircuitBreaker("test-cb")
        
        def faulty_listener(event):
            raise RuntimeError("listener error")
        
        def good_listener(event):
            pass  # Should still be called
        
        cb.on_event(CircuitBreakerOnSuccessEvent, faulty_listener)
        cb.on_event(CircuitBreakerOnSuccessEvent, good_listener)
        
        @cb
        async def test_function():
            return "success"
        
        # Should not raise despite faulty listener
        result = await test_function()
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_all_event_types(self):
        """Test that all event types are emitted correctly."""
        config = CircuitBreakerConfig(
            failure_rate_threshold=50.0,
            minimum_number_of_calls=2,
            sliding_window_size=2,
            ignore_exceptions=[ValueError]
        )
        cb = CircuitBreaker("test-cb", config)
        
        events = {
            'success': [],
            'error': [],
            'ignored': [],
            'not_permitted': [],
            'state_transition': [],
            'reset': []
        }
        
        cb.on_event(CircuitBreakerOnSuccessEvent, lambda e: events['success'].append(e))
        cb.on_event(CircuitBreakerOnErrorEvent, lambda e: events['error'].append(e))
        cb.on_event(CircuitBreakerOnIgnoredErrorEvent, lambda e: events['ignored'].append(e))
        cb.on_event(CircuitBreakerOnCallNotPermittedEvent, lambda e: events['not_permitted'].append(e))
        cb.on_event(CircuitBreakerOnStateTransitionEvent, lambda e: events['state_transition'].append(e))
        cb.on_event(CircuitBreakerOnResetEvent, lambda e: events['reset'].append(e))
        
        @cb
        async def test_function(error_type=None):
            if error_type == "runtime":
                raise RuntimeError("test")
            elif error_type == "value":
                raise ValueError("ignored")
            return "success"
        
        # Success event
        await test_function()
        assert len(events['success']) == 1
        
        # Error event
        with pytest.raises(RuntimeError):
            await test_function(error_type="runtime")
        assert len(events['error']) == 1
        
        # State transition event (should open due to 50% failure)
        assert len(events['state_transition']) == 1
        assert cb.state_name == CircuitBreakerState.OPEN
        
        # Not permitted event
        with pytest.raises(CallNotPermittedException):
            await test_function()
        assert len(events['not_permitted']) == 1
        
        # Reset event
        await cb.reset()
        assert len(events['reset']) == 1
        
        # Ignored error event
        with pytest.raises(ValueError):
            await test_function(error_type="value")
        assert len(events['ignored']) == 1


class TestCircuitBreakerEdgeCases:
    """Test edge cases and special scenarios."""
    
    @pytest.mark.asyncio
    async def test_exception_in_decorated_function_init(self):
        """Test exception during function initialization."""
        cb = CircuitBreaker("test-cb")
        
        def create_function():
            @cb
            async def test_function():
                return "success"
            raise RuntimeError("init error")
        
        with pytest.raises(RuntimeError, match="init error"):
            create_function()
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_with_args_and_kwargs(self):
        """Test decorated function with various argument patterns."""
        cb = CircuitBreaker("test-cb")
        
        @cb
        async def complex_function(a, b, *args, c=3, d=4, **kwargs):
            return {
                'a': a, 'b': b, 'args': args,
                'c': c, 'd': d, 'kwargs': kwargs
            }
        
        result = await complex_function(1, 2, 5, 6, c=7, d=8, e=9, f=10)
        
        assert result == {
            'a': 1, 'b': 2, 'args': (5, 6),
            'c': 7, 'd': 8, 'kwargs': {'e': 9, 'f': 10}
        }
    
    @pytest.mark.asyncio
    async def test_very_fast_calls(self):
        """Test handling of very fast (near-zero duration) calls."""
        cb = CircuitBreaker("test-cb")
        
        @cb
        async def instant_function():
            return "instant"
        
        # Make many fast calls
        for _ in range(100):
            await instant_function()
        
        metrics = await cb.get_metrics()
        assert metrics['total_calls'] == 100
        assert metrics['average_duration_ms'] >= 0
    
    @pytest.mark.asyncio
    async def test_concurrent_calls(self):
        """Test circuit breaker with concurrent calls."""
        config = CircuitBreakerConfig(
            failure_rate_threshold=50.0,
            minimum_number_of_calls=10,
            sliding_window_size=10
        )
        cb = CircuitBreaker("test-cb", config)
        
        @cb
        async def concurrent_function(should_fail=False):
            await asyncio.sleep(0.01)
            if should_fail:
                raise RuntimeError("concurrent failure")
            return "success"
        
        # Make concurrent calls
        tasks = []
        for i in range(20):
            should_fail = i % 2 == 0  # 50% failure rate
            task = concurrent_function(should_fail)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successes and failures
        successes = sum(1 for r in results if r == "success")
        failures = sum(1 for r in results if isinstance(r, RuntimeError))
        
        assert successes + failures == 20
        
        # Circuit breaker might be open now due to failures
        metrics = await cb.get_metrics()
        if metrics['total_calls'] >= 10:
            # If we recorded enough calls, check failure rate
            assert metrics['failure_rate'] >= 40  # Should be around 50%