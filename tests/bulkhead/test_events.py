"""Tests for bulkhead event classes."""

import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock
import asyncio

from resilience4py.bulkhead.events import (
    BulkheadEventType,
    BulkheadEvent,
    BulkheadOnCallPermittedEvent,
    BulkheadOnCallRejectedEvent,
    BulkheadOnCallFinishedEvent
)


class TestBulkheadEventType:
    """Test cases for BulkheadEventType enum."""
    
    def test_event_types_exist(self):
        """Test that all event types are defined."""
        assert BulkheadEventType.CALL_PERMITTED
        assert BulkheadEventType.CALL_REJECTED
        assert BulkheadEventType.CALL_FINISHED
    
    def test_event_types_are_unique(self):
        """Test that event types have unique values."""
        event_types = [
            BulkheadEventType.CALL_PERMITTED,
            BulkheadEventType.CALL_REJECTED,
            BulkheadEventType.CALL_FINISHED
        ]
        
        # Check that all values are unique
        assert len(event_types) == len(set(event_types))


class TestBulkheadEvent:
    """Test cases for base BulkheadEvent class."""
    
    def test_creation_with_all_fields(self):
        """Test creating event with all fields specified."""
        now = datetime.now()
        event = BulkheadEvent(
            bulkhead_name="test-bulkhead",
            event_type=BulkheadEventType.CALL_PERMITTED,
            creation_time=now,
            name="custom-name"
        )
        
        assert event.bulkhead_name == "test-bulkhead"
        assert event.event_type == BulkheadEventType.CALL_PERMITTED
        assert event.creation_time == now
        assert event.name == "custom-name"
    
    def test_auto_creation_time(self):
        """Test that creation_time is automatically set."""
        before = datetime.now()
        event = BulkheadEvent(
            bulkhead_name="test-bulkhead",
            event_type=BulkheadEventType.CALL_REJECTED,
            name="test"
        )
        after = datetime.now()
        
        assert before <= event.creation_time <= after
    
    def test_post_init_sets_name(self):
        """Test that __post_init__ sets name to bulkhead_name if not provided."""
        # BulkheadEvent is a dataclass that inherits from Event
        # Since Event requires 'name', we need to check the subclasses
        # which handle this in their __init__ methods
        
        # Test with subclasses that properly handle name setting
        permitted = BulkheadOnCallPermittedEvent("test-bulkhead")
        assert permitted.name == "test-bulkhead"
        assert permitted.bulkhead_name == "test-bulkhead"


class TestBulkheadOnCallPermittedEvent:
    """Test cases for BulkheadOnCallPermittedEvent."""
    
    def test_creation(self):
        """Test creating a call permitted event."""
        event = BulkheadOnCallPermittedEvent("my-bulkhead")
        
        assert event.bulkhead_name == "my-bulkhead"
        assert event.event_type == BulkheadEventType.CALL_PERMITTED
        assert event.name == "my-bulkhead"
        assert isinstance(event.creation_time, datetime)
    
    def test_inheritance(self):
        """Test that event inherits from BulkheadEvent."""
        event = BulkheadOnCallPermittedEvent("test")
        assert isinstance(event, BulkheadEvent)


class TestBulkheadOnCallRejectedEvent:
    """Test cases for BulkheadOnCallRejectedEvent."""
    
    def test_creation(self):
        """Test creating a call rejected event."""
        event = BulkheadOnCallRejectedEvent("my-bulkhead")
        
        assert event.bulkhead_name == "my-bulkhead"
        assert event.event_type == BulkheadEventType.CALL_REJECTED
        assert event.name == "my-bulkhead"
        assert isinstance(event.creation_time, datetime)
    
    def test_inheritance(self):
        """Test that event inherits from BulkheadEvent."""
        event = BulkheadOnCallRejectedEvent("test")
        assert isinstance(event, BulkheadEvent)


class TestBulkheadOnCallFinishedEvent:
    """Test cases for BulkheadOnCallFinishedEvent."""
    
    def test_creation(self):
        """Test creating a call finished event."""
        event = BulkheadOnCallFinishedEvent("my-bulkhead")
        
        assert event.bulkhead_name == "my-bulkhead"
        assert event.event_type == BulkheadEventType.CALL_FINISHED
        assert event.name == "my-bulkhead"
        assert isinstance(event.creation_time, datetime)
    
    def test_inheritance(self):
        """Test that event inherits from BulkheadEvent."""
        event = BulkheadOnCallFinishedEvent("test")
        assert isinstance(event, BulkheadEvent)


class TestEventHandling:
    """Test event handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_event_handler_registration(self):
        """Test that events can be handled by registered handlers."""
        # This test demonstrates how events would be used
        events_received = []
        
        def sync_handler(event):
            events_received.append(event)
        
        async def async_handler(event):
            await asyncio.sleep(0)  # Simulate async work
            events_received.append(event)
        
        # Create events
        permitted = BulkheadOnCallPermittedEvent("test")
        rejected = BulkheadOnCallRejectedEvent("test")
        finished = BulkheadOnCallFinishedEvent("test")
        
        # Simulate handling
        sync_handler(permitted)
        await async_handler(rejected)
        sync_handler(finished)
        
        assert len(events_received) == 3
        assert isinstance(events_received[0], BulkheadOnCallPermittedEvent)
        assert isinstance(events_received[1], BulkheadOnCallRejectedEvent)
        assert isinstance(events_received[2], BulkheadOnCallFinishedEvent)
    
    def test_event_equality(self):
        """Test that events with same data are not equal (different instances)."""
        event1 = BulkheadOnCallPermittedEvent("test")
        event2 = BulkheadOnCallPermittedEvent("test")
        
        # Different instances should not be equal
        assert event1 != event2
        
        # But they should have same attributes
        assert event1.bulkhead_name == event2.bulkhead_name
        assert event1.event_type == event2.event_type
    
    def test_event_creation_time_ordering(self):
        """Test that events can be ordered by creation time."""
        event1 = BulkheadOnCallPermittedEvent("test")
        # Small delay to ensure different timestamps
        import time
        time.sleep(0.001)
        event2 = BulkheadOnCallRejectedEvent("test")
        
        assert event1.creation_time < event2.creation_time