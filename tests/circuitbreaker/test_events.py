"""Tests for Circuit Breaker events."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock
import pytest

from resilience4py.circuitbreaker.circuit_breaker import CircuitBreaker
from resilience4py.circuitbreaker.config import CircuitBreakerConfig
from resilience4py.circuitbreaker.events import (
    CircuitBreakerEventType,
    CircuitBreakerState,
    CircuitBreakerEvent,
    CircuitBreakerOnSuccessEvent,
    CircuitBreakerOnErrorEvent,
    CircuitBreakerOnCallNotPermittedEvent,
    CircuitBreakerOnStateTransitionEvent,
    CircuitBreakerOnResetEvent,
    CircuitBreakerOnIgnoredErrorEvent,
    CircuitBreakerOnSlowCallRateExceededEvent,
    CircuitBreakerOnFailureRateExceededEvent,
    CircuitBreakerOnManualStateTransitionEvent
)


class TestEventTypes:
    """Test CircuitBreakerEventType enum."""
    
    def test_event_type_values(self):
        """Test that all event types are defined."""
        assert CircuitBreakerEventType.SUCCESS
        assert CircuitBreakerEventType.ERROR
        assert CircuitBreakerEventType.NOT_PERMITTED
        assert CircuitBreakerEventType.STATE_TRANSITION
        assert CircuitBreakerEventType.RESET
        assert CircuitBreakerEventType.IGNORED_ERROR
        assert CircuitBreakerEventType.SLOW_CALL_RATE_EXCEEDED
        assert CircuitBreakerEventType.FAILURE_RATE_EXCEEDED
        assert CircuitBreakerEventType.MANUAL_STATE_TRANSITION


class TestCircuitBreakerStates:
    """Test CircuitBreakerState enum."""
    
    def test_state_values(self):
        """Test that all states have correct string values."""
        assert CircuitBreakerState.CLOSED.value == "CLOSED"
        assert CircuitBreakerState.OPEN.value == "OPEN"
        assert CircuitBreakerState.HALF_OPEN.value == "HALF_OPEN"
        assert CircuitBreakerState.DISABLED.value == "DISABLED"
        assert CircuitBreakerState.FORCED_OPEN.value == "FORCED_OPEN"
        assert CircuitBreakerState.METRICS_ONLY.value == "METRICS_ONLY"


class TestBaseEvent:
    """Test base CircuitBreakerEvent class."""
    
    def test_base_event_creation(self):
        """Test creating base event."""
        event = CircuitBreakerEvent(
            circuit_breaker_name="test-cb",
            event_type=CircuitBreakerEventType.SUCCESS
        )
        
        assert event.circuit_breaker_name == "test-cb"
        assert event.event_type == CircuitBreakerEventType.SUCCESS
        assert isinstance(event.creation_time, datetime)
        assert event.creation_time <= datetime.now()
    
    def test_base_event_with_custom_time(self):
        """Test creating event with custom timestamp."""
        custom_time = datetime(2023, 1, 1, 12, 0, 0)
        event = CircuitBreakerEvent(
            circuit_breaker_name="test-cb",
            event_type=CircuitBreakerEventType.ERROR,
            creation_time=custom_time
        )
        
        assert event.creation_time == custom_time


class TestSuccessEvent:
    """Test CircuitBreakerOnSuccessEvent."""
    
    def test_success_event_creation(self):
        """Test creating success event."""
        event = CircuitBreakerOnSuccessEvent.create(
            circuit_breaker_name="test-cb",
            duration_ms=150.5
        )
        
        assert event.circuit_breaker_name == "test-cb"
        assert event.event_type == CircuitBreakerEventType.SUCCESS
        assert event.duration_ms == 150.5
        assert isinstance(event.creation_time, datetime)
    
    def test_success_event_direct_creation(self):
        """Test direct creation of success event."""
        event = CircuitBreakerOnSuccessEvent(
            circuit_breaker_name="test-cb",
            event_type=CircuitBreakerEventType.SUCCESS,
            duration_ms=200.0
        )
        
        assert event.duration_ms == 200.0


class TestErrorEvent:
    """Test CircuitBreakerOnErrorEvent."""
    
    def test_error_event_creation(self):
        """Test creating error event."""
        exception = RuntimeError("test error")
        event = CircuitBreakerOnErrorEvent.create(
            circuit_breaker_name="test-cb",
            duration_ms=75.3,
            exception=exception
        )
        
        assert event.circuit_breaker_name == "test-cb"
        assert event.event_type == CircuitBreakerEventType.ERROR
        assert event.duration_ms == 75.3
        assert event.exception is exception
        assert isinstance(event.exception, RuntimeError)
    
    def test_error_event_with_different_exceptions(self):
        """Test error event with various exception types."""
        exceptions = [
            ValueError("value error"),
            TypeError("type error"),
            Exception("base exception"),
            KeyError("key error")
        ]
        
        for exc in exceptions:
            event = CircuitBreakerOnErrorEvent.create(
                circuit_breaker_name="test-cb",
                duration_ms=100.0,
                exception=exc
            )
            assert event.exception is exc
            assert type(event.exception) is type(exc)


class TestCallNotPermittedEvent:
    """Test CircuitBreakerOnCallNotPermittedEvent."""
    
    def test_call_not_permitted_event_creation(self):
        """Test creating call not permitted event."""
        event = CircuitBreakerOnCallNotPermittedEvent.create(
            circuit_breaker_name="test-cb"
        )
        
        assert event.circuit_breaker_name == "test-cb"
        assert event.event_type == CircuitBreakerEventType.NOT_PERMITTED
        assert isinstance(event.creation_time, datetime)


class TestStateTransitionEvent:
    """Test CircuitBreakerOnStateTransitionEvent."""
    
    def test_state_transition_event_creation(self):
        """Test creating state transition event."""
        event = CircuitBreakerOnStateTransitionEvent.create(
            circuit_breaker_name="test-cb",
            from_state=CircuitBreakerState.CLOSED,
            to_state=CircuitBreakerState.OPEN
        )
        
        assert event.circuit_breaker_name == "test-cb"
        assert event.event_type == CircuitBreakerEventType.STATE_TRANSITION
        assert event.from_state == CircuitBreakerState.CLOSED
        assert event.to_state == CircuitBreakerState.OPEN
    
    def test_all_state_transitions(self):
        """Test events for all possible state transitions."""
        states = list(CircuitBreakerState)
        
        for from_state in states:
            for to_state in states:
                if from_state != to_state:
                    event = CircuitBreakerOnStateTransitionEvent.create(
                        circuit_breaker_name="test-cb",
                        from_state=from_state,
                        to_state=to_state
                    )
                    assert event.from_state == from_state
                    assert event.to_state == to_state


class TestResetEvent:
    """Test CircuitBreakerOnResetEvent."""
    
    def test_reset_event_creation(self):
        """Test creating reset event."""
        event = CircuitBreakerOnResetEvent.create(
            circuit_breaker_name="test-cb"
        )
        
        assert event.circuit_breaker_name == "test-cb"
        assert event.event_type == CircuitBreakerEventType.RESET
        assert isinstance(event.creation_time, datetime)


class TestIgnoredErrorEvent:
    """Test CircuitBreakerOnIgnoredErrorEvent."""
    
    def test_ignored_error_event_creation(self):
        """Test creating ignored error event."""
        exception = ValueError("ignored error")
        event = CircuitBreakerOnIgnoredErrorEvent.create(
            circuit_breaker_name="test-cb",
            exception=exception
        )
        
        assert event.circuit_breaker_name == "test-cb"
        assert event.event_type == CircuitBreakerEventType.IGNORED_ERROR
        assert event.exception is exception
        assert isinstance(event.exception, ValueError)


class TestSlowCallRateExceededEvent:
    """Test CircuitBreakerOnSlowCallRateExceededEvent."""
    
    def test_slow_call_rate_exceeded_event_creation(self):
        """Test creating slow call rate exceeded event."""
        event = CircuitBreakerOnSlowCallRateExceededEvent.create(
            circuit_breaker_name="test-cb",
            slow_call_rate=75.5
        )
        
        assert event.circuit_breaker_name == "test-cb"
        assert event.event_type == CircuitBreakerEventType.SLOW_CALL_RATE_EXCEEDED
        assert event.slow_call_rate == 75.5
    
    def test_slow_call_rate_edge_values(self):
        """Test slow call rate with edge values."""
        for rate in [0.0, 50.0, 100.0]:
            event = CircuitBreakerOnSlowCallRateExceededEvent.create(
                circuit_breaker_name="test-cb",
                slow_call_rate=rate
            )
            assert event.slow_call_rate == rate


class TestFailureRateExceededEvent:
    """Test CircuitBreakerOnFailureRateExceededEvent."""
    
    def test_failure_rate_exceeded_event_creation(self):
        """Test creating failure rate exceeded event."""
        event = CircuitBreakerOnFailureRateExceededEvent.create(
            circuit_breaker_name="test-cb",
            failure_rate=60.25
        )
        
        assert event.circuit_breaker_name == "test-cb"
        assert event.event_type == CircuitBreakerEventType.FAILURE_RATE_EXCEEDED
        assert event.failure_rate == 60.25
    
    def test_failure_rate_precision(self):
        """Test failure rate with various precision levels."""
        rates = [33.33333333, 66.66666667, 12.345678]
        
        for rate in rates:
            event = CircuitBreakerOnFailureRateExceededEvent.create(
                circuit_breaker_name="test-cb",
                failure_rate=rate
            )
            assert event.failure_rate == rate


class TestManualStateTransitionEvent:
    """Test CircuitBreakerOnManualStateTransitionEvent."""
    
    def test_manual_state_transition_event_creation(self):
        """Test creating manual state transition event."""
        event = CircuitBreakerOnManualStateTransitionEvent.create(
            circuit_breaker_name="test-cb",
            from_state=CircuitBreakerState.OPEN,
            to_state=CircuitBreakerState.CLOSED
        )
        
        assert event.circuit_breaker_name == "test-cb"
        assert event.event_type == CircuitBreakerEventType.MANUAL_STATE_TRANSITION
        assert event.from_state == CircuitBreakerState.OPEN
        assert event.to_state == CircuitBreakerState.CLOSED


class TestEventEmissionIntegration:
    """Test event emission in real circuit breaker scenarios."""
    
    @pytest.mark.asyncio
    async def test_success_event_emission(self):
        """Test that success events are emitted correctly."""
        cb = CircuitBreaker("test-cb")
        received_events = []
        
        def capture_event(event):
            received_events.append(event)
        
        cb.on_event(CircuitBreakerOnSuccessEvent, capture_event)
        
        @cb
        async def successful_function():
            await asyncio.sleep(0.05)  # 50ms
            return "success"
        
        result = await successful_function()
        
        assert len(received_events) == 1
        event = received_events[0]
        assert isinstance(event, CircuitBreakerOnSuccessEvent)
        assert event.circuit_breaker_name == "test-cb"
        assert event.duration_ms >= 50.0  # At least 50ms
        assert event.duration_ms < 100.0  # But not too long
    
    @pytest.mark.asyncio
    async def test_error_event_emission(self):
        """Test that error events are emitted correctly."""
        cb = CircuitBreaker("test-cb")
        received_events = []
        
        def capture_event(event):
            received_events.append(event)
        
        cb.on_event(CircuitBreakerOnErrorEvent, capture_event)
        
        @cb
        async def failing_function():
            await asyncio.sleep(0.02)  # 20ms
            raise ValueError("test error message")
        
        with pytest.raises(ValueError):
            await failing_function()
        
        assert len(received_events) == 1
        event = received_events[0]
        assert isinstance(event, CircuitBreakerOnErrorEvent)
        assert event.circuit_breaker_name == "test-cb"
        assert event.duration_ms >= 20.0
        assert isinstance(event.exception, ValueError)
        assert str(event.exception) == "test error message"
    
    @pytest.mark.asyncio
    async def test_threshold_exceeded_events(self):
        """Test that threshold exceeded events are emitted."""
        config = CircuitBreakerConfig(
            failure_rate_threshold=50.0,
            slow_call_rate_threshold=50.0,
            slow_call_duration_threshold=timedelta(milliseconds=50),
            minimum_number_of_calls=4,
            sliding_window_size=4
        )
        cb = CircuitBreaker("test-cb", config)
        
        failure_rate_events = []
        slow_call_rate_events = []
        
        cb.on_event(
            CircuitBreakerOnFailureRateExceededEvent,
            lambda e: failure_rate_events.append(e)
        )
        cb.on_event(
            CircuitBreakerOnSlowCallRateExceededEvent,
            lambda e: slow_call_rate_events.append(e)
        )
        
        @cb
        async def test_function(should_fail=False, delay=0.01):
            await asyncio.sleep(delay)
            if should_fail:
                raise RuntimeError("failure")
            return "success"
        
        # Test failure rate exceeded
        await test_function()
        await test_function()
        with pytest.raises(RuntimeError):
            await test_function(should_fail=True)
        with pytest.raises(RuntimeError):
            await test_function(should_fail=True)
        
        assert len(failure_rate_events) == 1
        assert failure_rate_events[0].failure_rate == 50.0
        
        # Reset for slow call test
        await cb.reset()
        
        # Test slow call rate exceeded
        await test_function(delay=0.01)  # Fast
        await test_function(delay=0.01)  # Fast
        await test_function(delay=0.06)  # Slow
        await test_function(delay=0.06)  # Slow
        
        assert len(slow_call_rate_events) == 1
        assert slow_call_rate_events[0].slow_call_rate == 50.0
    
    @pytest.mark.asyncio
    async def test_multiple_event_listeners(self):
        """Test multiple listeners for same event type."""
        cb = CircuitBreaker("test-cb")
        
        listener1_events = []
        listener2_events = []
        listener3_events = []
        
        cb.on_event(CircuitBreakerOnSuccessEvent, lambda e: listener1_events.append(e))
        cb.on_event(CircuitBreakerOnSuccessEvent, lambda e: listener2_events.append(e))
        cb.on_event(CircuitBreakerOnSuccessEvent, lambda e: listener3_events.append(e))
        
        @cb
        async def test_function():
            return "success"
        
        await test_function()
        
        # All listeners should receive the event
        assert len(listener1_events) == 1
        assert len(listener2_events) == 1
        assert len(listener3_events) == 1
        
        # Should be the same event instance
        assert listener1_events[0] is listener2_events[0]
        assert listener2_events[0] is listener3_events[0]
    
    @pytest.mark.asyncio
    async def test_event_listener_removal(self):
        """Test removing specific event listeners."""
        cb = CircuitBreaker("test-cb")
        
        events1 = []
        events2 = []
        
        def listener1(event):
            events1.append(event)
        
        def listener2(event):
            events2.append(event)
        
        cb.on_event(CircuitBreakerOnSuccessEvent, listener1)
        cb.on_event(CircuitBreakerOnSuccessEvent, listener2)
        
        @cb
        async def test_function():
            return "success"
        
        # Both listeners should work
        await test_function()
        assert len(events1) == 1
        assert len(events2) == 1
        
        # Remove listener1
        cb.remove_event_listener(CircuitBreakerOnSuccessEvent, listener1)
        
        # Only listener2 should work now
        await test_function()
        assert len(events1) == 1  # No new event
        assert len(events2) == 2  # New event received
    
    @pytest.mark.asyncio
    async def test_event_timing_accuracy(self):
        """Test that event timestamps are accurate."""
        cb = CircuitBreaker("test-cb")
        events = []
        
        cb.on_event(CircuitBreakerOnSuccessEvent, lambda e: events.append(e))
        
        @cb
        async def test_function():
            return "success"
        
        before = datetime.now()
        await test_function()
        after = datetime.now()
        
        assert len(events) == 1
        event = events[0]
        
        # Event creation time should be between before and after
        assert before <= event.creation_time <= after