"""Tests for Event system, async event publishing, and consumer registration"""

import pytest
import asyncio
from datetime import datetime
from enum import Enum
from unittest.mock import Mock, AsyncMock, patch
import logging

from resilience4py.core.events import Event, EventPublisher


class SampleEventType(Enum):
    """Test event types"""
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class SampleEvent(Event):
    """Test event implementation"""
    def __init__(self, name: str, event_type: SampleEventType, data: str = ""):
        super().__init__(name, event_type)
        self.data = data


class TestEventClass:
    """Test suite for Event class"""
    
    def test_event_creation(self):
        """Test creating an event"""
        event = Event("test_component", SampleEventType.STARTED)
        
        assert event.name == "test_component"
        assert event.event_type == SampleEventType.STARTED
        assert isinstance(event.creation_time, datetime)
        assert event.creation_time <= datetime.now()
    
    def test_event_string_representation(self):
        """Test event string representation"""
        event = Event("test_component", SampleEventType.STARTED)
        str_repr = str(event)
        
        assert "Event" in str_repr
        assert "test_component" in str_repr
        assert "STARTED" in str_repr
        assert "time=" in str_repr
    
    def test_custom_event_inheritance(self):
        """Test custom event inheriting from Event"""
        event = SampleEvent("custom", SampleEventType.COMPLETED, "test_data")
        
        assert event.name == "custom"
        assert event.event_type == SampleEventType.COMPLETED
        assert event.data == "test_data"
        assert isinstance(event.creation_time, datetime)
    
    def test_event_creation_time_frozen(self):
        """Test that creation time is set once and doesn't change"""
        event = Event("test", SampleEventType.STARTED)
        time1 = event.creation_time
        
        # Wait a bit
        import time
        time.sleep(0.01)
        
        time2 = event.creation_time
        assert time1 == time2  # Should be the same


class TestEventPublisher:
    """Test suite for EventPublisher"""
    
    @pytest.mark.asyncio
    async def test_publisher_creation(self):
        """Test creating an event publisher"""
        publisher = EventPublisher()
        
        assert publisher._queue.maxsize == 1000
        assert len(publisher._consumers) == 0
        assert not publisher._running
        assert publisher._task is None
    
    @pytest.mark.asyncio
    async def test_publisher_with_custom_queue_size(self):
        """Test creating publisher with custom queue size"""
        publisher = EventPublisher(queue_size=100)
        assert publisher._queue.maxsize == 100
    
    @pytest.mark.asyncio
    async def test_consumer_registration(self):
        """Test registering event consumers"""
        publisher = EventPublisher()
        
        consumer1 = Mock()
        consumer2 = Mock()
        
        publisher.on(SampleEventType.STARTED, consumer1)
        publisher.on(SampleEventType.STARTED, consumer2)
        publisher.on(SampleEventType.COMPLETED, consumer1)
        
        assert len(publisher._consumers[SampleEventType.STARTED]) == 2
        assert len(publisher._consumers[SampleEventType.COMPLETED]) == 1
        assert consumer1 in publisher._consumers[SampleEventType.STARTED]
        assert consumer2 in publisher._consumers[SampleEventType.STARTED]
        assert consumer1 in publisher._consumers[SampleEventType.COMPLETED]
    
    @pytest.mark.asyncio
    async def test_consumer_unregistration(self):
        """Test unregistering event consumers"""
        publisher = EventPublisher()
        
        consumer1 = Mock()
        consumer2 = Mock()
        
        # Register consumers
        publisher.on(SampleEventType.STARTED, consumer1)
        publisher.on(SampleEventType.STARTED, consumer2)
        
        # Unregister one
        publisher.off(SampleEventType.STARTED, consumer1)
        
        assert len(publisher._consumers[SampleEventType.STARTED]) == 1
        assert consumer2 in publisher._consumers[SampleEventType.STARTED]
        assert consumer1 not in publisher._consumers[SampleEventType.STARTED]
        
        # Unregister non-existent (should not raise)
        publisher.off(SampleEventType.STARTED, consumer1)
        publisher.off(SampleEventType.COMPLETED, consumer1)
    
    @pytest.mark.asyncio
    async def test_publish_event_async(self):
        """Test publishing events asynchronously"""
        publisher = EventPublisher()
        await publisher.start()
        
        try:
            # Register async consumer
            events_received = []
            async def async_consumer(event):
                events_received.append(event)
            
            publisher.on(SampleEventType.STARTED, async_consumer)
            
            # Publish event
            event = Event("test", SampleEventType.STARTED)
            await publisher.publish(event)
            
            # Wait for processing
            await asyncio.sleep(0.1)
            
            assert len(events_received) == 1
            assert events_received[0] is event
        finally:
            await publisher.stop()
    
    @pytest.mark.asyncio
    async def test_publish_event_sync_consumer(self):
        """Test publishing events to synchronous consumers"""
        publisher = EventPublisher()
        await publisher.start()
        
        try:
            # Register sync consumer
            mock_consumer = Mock()
            publisher.on(SampleEventType.STARTED, mock_consumer)
            
            # Publish event
            event = Event("test", SampleEventType.STARTED)
            await publisher.publish(event)
            
            # Wait for processing
            await asyncio.sleep(0.1)
            
            mock_consumer.assert_called_once_with(event)
        finally:
            await publisher.stop()
    
    @pytest.mark.asyncio
    async def test_publish_nowait(self):
        """Test publishing events without waiting"""
        publisher = EventPublisher()
        await publisher.start()
        
        try:
            events_received = []
            async def consumer(event):
                events_received.append(event)
            
            publisher.on(SampleEventType.STARTED, consumer)
            
            # Publish without waiting
            event = Event("test", SampleEventType.STARTED)
            publisher.publish_nowait(event)
            
            # Wait for processing
            await asyncio.sleep(0.1)
            
            assert len(events_received) == 1
            assert events_received[0] is event
        finally:
            await publisher.stop()
    
    @pytest.mark.asyncio
    async def test_queue_full_handling(self):
        """Test handling of full queue"""
        publisher = EventPublisher(queue_size=2)
        
        # Don't start publisher so queue won't be consumed
        
        # Fill queue
        event1 = Event("test1", SampleEventType.STARTED)
        event2 = Event("test2", SampleEventType.STARTED)
        event3 = Event("test3", SampleEventType.STARTED)
        
        await publisher.publish(event1)
        await publisher.publish(event2)
        
        # This should block, so we use nowait
        with patch('resilience4py.core.events.logger') as mock_logger:
            publisher.publish_nowait(event3)
            mock_logger.warning.assert_called_once()
            assert "queue full" in mock_logger.warning.call_args[0][0].lower()
    
    @pytest.mark.asyncio
    async def test_multiple_event_types(self):
        """Test handling multiple event types"""
        publisher = EventPublisher()
        await publisher.start()
        
        try:
            started_events = []
            completed_events = []
            
            async def started_consumer(event):
                started_events.append(event)
            
            async def completed_consumer(event):
                completed_events.append(event)
            
            publisher.on(SampleEventType.STARTED, started_consumer)
            publisher.on(SampleEventType.COMPLETED, completed_consumer)
            
            # Publish different event types
            event1 = Event("test", SampleEventType.STARTED)
            event2 = Event("test", SampleEventType.COMPLETED)
            event3 = Event("test", SampleEventType.FAILED)  # No consumer
            
            await publisher.publish(event1)
            await publisher.publish(event2)
            await publisher.publish(event3)
            
            await asyncio.sleep(0.1)
            
            assert len(started_events) == 1
            assert len(completed_events) == 1
            assert started_events[0] is event1
            assert completed_events[0] is event2
        finally:
            await publisher.stop()
    
    @pytest.mark.asyncio
    async def test_consumer_error_handling(self):
        """Test that consumer errors don't stop other consumers"""
        publisher = EventPublisher()
        await publisher.start()
        
        try:
            events_received = []
            
            def error_consumer(event):
                raise RuntimeError("Consumer error")
            
            async def good_consumer(event):
                events_received.append(event)
            
            # Register both consumers for same event type
            publisher.on(SampleEventType.STARTED, error_consumer)
            publisher.on(SampleEventType.STARTED, good_consumer)
            
            # Publish event
            event = Event("test", SampleEventType.STARTED)
            with patch('resilience4py.core.events.logger') as mock_logger:
                await publisher.publish(event)
                await asyncio.sleep(0.1)
                
                # Error should be logged
                mock_logger.error.assert_called()
                assert "Consumer error" in str(mock_logger.error.call_args)
            
            # Good consumer should still receive event
            assert len(events_received) == 1
            assert events_received[0] is event
        finally:
            await publisher.stop()
    
    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self):
        """Test publisher start/stop lifecycle"""
        publisher = EventPublisher()
        
        # Initially not running
        assert not publisher._running
        assert publisher._task is None
        
        # Start
        await publisher.start()
        assert publisher._running
        assert publisher._task is not None
        assert not publisher._task.done()
        
        # Start again (should be no-op)
        await publisher.start()
        assert publisher._running
        
        # Stop
        await publisher.stop()
        assert not publisher._running
        assert publisher._task.done()
    
    @pytest.mark.asyncio
    async def test_stop_processes_remaining_events(self):
        """Test that stop processes remaining queued events"""
        publisher = EventPublisher()
        await publisher.start()
        
        events_received = []
        async def consumer(event):
            events_received.append(event)
        
        publisher.on(SampleEventType.STARTED, consumer)
        
        # Publish several events
        for i in range(5):
            event = Event(f"test{i}", SampleEventType.STARTED)
            await publisher.publish(event)
        
        # Stop immediately (before events are processed)
        await publisher.stop()
        
        # All events should still be processed
        assert len(events_received) == 5
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test using publisher as context manager"""
        events_received = []
        
        async def consumer(event):
            events_received.append(event)
        
        async with EventPublisher() as publisher:
            publisher.on(SampleEventType.STARTED, consumer)
            
            event = Event("test", SampleEventType.STARTED)
            await publisher.publish(event)
            
            await asyncio.sleep(0.1)
            
        # Should be stopped after context
        assert not publisher._running
        assert len(events_received) == 1
    
    @pytest.mark.asyncio
    async def test_sync_context_manager(self):
        """Test using publisher as sync context manager"""
        publisher = EventPublisher()
        
        with publisher:
            # Should start the publisher
            await asyncio.sleep(0.1)  # Let start task run
            assert publisher._running
        
        # Should schedule stop
        await asyncio.sleep(0.1)  # Let stop task run
        assert not publisher._running
    
    @pytest.mark.asyncio
    async def test_process_events_error_recovery(self):
        """Test that _process_events continues after errors"""
        publisher = EventPublisher()
        
        # Mock the queue to raise an exception once
        error_count = 0
        original_get = publisher._queue.get
        
        async def mock_get():
            nonlocal error_count
            if error_count == 0:
                error_count += 1
                raise Exception("Queue error")
            return await original_get()
        
        publisher._queue.get = mock_get
        
        await publisher.start()
        
        try:
            # Despite error, publisher should keep running
            await asyncio.sleep(0.1)
            assert publisher._running
            
            # Should still be able to process events
            events_received = []
            async def consumer(event):
                events_received.append(event)
            
            publisher.on(SampleEventType.STARTED, consumer)
            
            event = Event("test", SampleEventType.STARTED)
            await publisher.publish(event)
            await asyncio.sleep(0.1)
            
            # Event should be processed despite earlier error
            assert len(events_received) == 1
        finally:
            await publisher.stop()
    
    @pytest.mark.asyncio
    async def test_concurrent_publish(self):
        """Test concurrent event publishing"""
        publisher = EventPublisher()
        await publisher.start()
        
        try:
            events_received = []
            async def consumer(event):
                events_received.append(event)
            
            publisher.on(SampleEventType.STARTED, consumer)
            
            # Publish many events concurrently
            async def publish_events(start_idx):
                for i in range(10):
                    event = Event(f"test{start_idx + i}", SampleEventType.STARTED)
                    await publisher.publish(event)
            
            tasks = [publish_events(i * 10) for i in range(10)]
            await asyncio.gather(*tasks)
            
            # Wait for all events to be processed
            await asyncio.sleep(0.2)
            
            # Should receive all 100 events
            assert len(events_received) == 100
            
            # Check all events are unique
            event_names = [e.name for e in events_received]
            assert len(set(event_names)) == 100
        finally:
            await publisher.stop()