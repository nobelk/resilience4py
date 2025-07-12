"""Tests for rate limiter events."""

from datetime import datetime
from unittest.mock import patch

import pytest

from resilience4py.ratelimiter.events import (
    RateLimiterEvent, RateLimiterEventType,
    RateLimiterOnSuccessEvent, RateLimiterOnFailureEvent
)


class TestRateLimiterEventType:
    """Test cases for RateLimiterEventType enum."""
    
    def test_event_types(self):
        """Test that all event types are defined."""
        assert RateLimiterEventType.SUCCESS
        assert RateLimiterEventType.FAILURE
        
        # Test enum values
        assert RateLimiterEventType.SUCCESS.name == "SUCCESS"
        assert RateLimiterEventType.FAILURE.name == "FAILURE"


class TestRateLimiterEvent:
    """Test cases for the base RateLimiterEvent class."""
    
    def test_initialization(self):
        """Test event initialization."""
        event = RateLimiterEvent(
            name="test-limiter",
            event_type=RateLimiterEventType.SUCCESS
        )
        
        assert event.name == "test-limiter"
        assert event.event_type == RateLimiterEventType.SUCCESS
        assert isinstance(event.creation_time, datetime)
    
    def test_creation_time_auto_set(self):
        """Test that creation time is automatically set."""
        # Create two events in sequence
        event1 = RateLimiterEvent("test", RateLimiterEventType.SUCCESS)
        # Small delay to ensure different timestamps
        import time
        time.sleep(0.001)
        event2 = RateLimiterEvent("test", RateLimiterEventType.SUCCESS)
        
        # Timestamps should be different
        assert event2.creation_time > event1.creation_time
    
    def test_string_representation(self):
        """Test string representation of events."""
        # Create event with explicit timestamp to avoid mocking issues
        mock_time = datetime(2024, 1, 1, 12, 0, 0)
        event = RateLimiterEvent("my-limiter", RateLimiterEventType.SUCCESS, mock_time)
        
        expected = "SUCCESS event for rate limiter 'my-limiter' at 2024-01-01 12:00:00"
        assert str(event) == expected


class TestRateLimiterOnSuccessEvent:
    """Test cases for RateLimiterOnSuccessEvent."""
    
    def test_initialization(self):
        """Test success event initialization."""
        event = RateLimiterOnSuccessEvent("test-limiter")
        
        assert event.name == "test-limiter"
        assert event.event_type == RateLimiterEventType.SUCCESS
        assert isinstance(event.creation_time, datetime)
    
    def test_inheritance(self):
        """Test that success event inherits from base event."""
        event = RateLimiterOnSuccessEvent("test")
        assert isinstance(event, RateLimiterEvent)
    
    def test_string_representation(self):
        """Test string representation."""
        event = RateLimiterOnSuccessEvent("api-limiter")
        assert "SUCCESS" in str(event)
        assert "api-limiter" in str(event)


class TestRateLimiterOnFailureEvent:
    """Test cases for RateLimiterOnFailureEvent."""
    
    def test_initialization_without_wait_time(self):
        """Test failure event initialization without wait time."""
        event = RateLimiterOnFailureEvent("test-limiter")
        
        assert event.name == "test-limiter"
        assert event.event_type == RateLimiterEventType.FAILURE
        assert event.wait_time_nanos is None
        assert isinstance(event.creation_time, datetime)
    
    def test_initialization_with_wait_time(self):
        """Test failure event initialization with wait time."""
        wait_time = 1_000_000_000  # 1 second in nanoseconds
        event = RateLimiterOnFailureEvent("test-limiter", wait_time)
        
        assert event.name == "test-limiter"
        assert event.event_type == RateLimiterEventType.FAILURE
        assert event.wait_time_nanos == wait_time
    
    def test_inheritance(self):
        """Test that failure event inherits from base event."""
        event = RateLimiterOnFailureEvent("test")
        assert isinstance(event, RateLimiterEvent)
    
    def test_string_representation(self):
        """Test string representation."""
        event = RateLimiterOnFailureEvent("db-limiter", 500_000_000)
        assert "FAILURE" in str(event)
        assert "db-limiter" in str(event)
    
    def test_wait_time_in_different_units(self):
        """Test wait time conversion to different units."""
        nanos = 1_234_567_890  # 1.234567890 seconds
        event = RateLimiterOnFailureEvent("test", nanos)
        
        # Test conversions
        assert event.wait_time_nanos == nanos
        
        # Convert to other units for verification
        micros = nanos / 1_000
        millis = nanos / 1_000_000
        seconds = nanos / 1_000_000_000
        
        assert micros == 1_234_567.89
        assert millis == 1_234.56789
        assert seconds == 1.23456789


class TestEventComparison:
    """Test event comparison and equality."""
    
    def test_event_equality_by_content(self):
        """Test that events with same content are not equal (different instances)."""
        event1 = RateLimiterOnSuccessEvent("test")
        event2 = RateLimiterOnSuccessEvent("test")
        
        # Different instances should not be equal
        assert event1 != event2
        assert event1 is not event2
    
    def test_event_type_comparison(self):
        """Test comparing different event types."""
        success = RateLimiterOnSuccessEvent("test")
        failure = RateLimiterOnFailureEvent("test")
        
        assert success.event_type != failure.event_type
        assert type(success) != type(failure)


class TestEventSerialization:
    """Test event serialization scenarios."""
    
    def test_event_attributes_accessible(self):
        """Test that all event attributes are accessible."""
        event = RateLimiterOnFailureEvent("limiter", 1000)
        
        # All attributes should be accessible
        assert hasattr(event, 'name')
        assert hasattr(event, 'event_type')
        assert hasattr(event, 'creation_time')
        assert hasattr(event, 'wait_time_nanos')
        
        # Test accessing all attributes
        _ = event.name
        _ = event.event_type
        _ = event.creation_time
        _ = event.wait_time_nanos
    
    def test_event_as_dict(self):
        """Test converting event to dictionary for logging/serialization."""
        event = RateLimiterOnFailureEvent("test-limiter", 5_000_000_000)
        
        # Manual dict creation (since dataclass should support this)
        event_dict = {
            'name': event.name,
            'event_type': event.event_type.name,
            'creation_time': event.creation_time.isoformat(),
            'wait_time_nanos': event.wait_time_nanos
        }
        
        assert event_dict['name'] == "test-limiter"
        assert event_dict['event_type'] == "FAILURE"
        assert event_dict['wait_time_nanos'] == 5_000_000_000


@pytest.mark.asyncio
async def test_event_usage_in_async_context():
    """Test that events can be used in async contexts."""
    events_received = []
    
    async def async_event_handler(event):
        """Async event handler."""
        events_received.append(event)
    
    # Create events
    success_event = RateLimiterOnSuccessEvent("async-test")
    failure_event = RateLimiterOnFailureEvent("async-test", 1000)
    
    # Process events asynchronously
    await async_event_handler(success_event)
    await async_event_handler(failure_event)
    
    assert len(events_received) == 2
    assert isinstance(events_received[0], RateLimiterOnSuccessEvent)
    assert isinstance(events_received[1], RateLimiterOnFailureEvent)