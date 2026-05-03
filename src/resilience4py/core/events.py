"""
Event system infrastructure for resilience patterns

Provides an async event publishing system for monitoring
and reacting to resilience pattern events.
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Callable, Any, Dict
import asyncio
import logging

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Base event class for all resilience pattern events
    
    All events in the system should inherit from this base class.
    
    Attributes:
        name: Name of the component that generated the event
        event_type: Type of event (should be an Enum)
        creation_time: Timestamp when the event was created
    """
    name: str
    event_type: Enum
    creation_time: datetime = field(default_factory=datetime.now)
    
    def __str__(self) -> str:
        """String representation of the event"""
        return f"{self.__class__.__name__}(name={self.name}, type={self.event_type.name}, time={self.creation_time})"


class EventPublisher:
    """Async event publisher for distributing events to consumers
    
    This publisher uses an async queue to decouple event production
    from consumption, allowing for non-blocking event publishing.
    
    Attributes:
        _consumers: Dictionary mapping event types to consumer callbacks
        _queue: Async queue for event processing
        _running: Flag indicating if the publisher is running
        _task: Background task for processing events
    """
    
    def __init__(self, queue_size: int = 1000):
        """Initialize event publisher
        
        Args:
            queue_size: Maximum number of events to queue (default: 1000)
        """
        self._consumers: Dict[Enum, List[Callable]] = {}
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    def on(self, event_type: Enum, consumer: Callable[[Event], None]) -> None:
        """Register event consumer for specific event type
        
        Args:
            event_type: Type of events to consume
            consumer: Callback function (can be sync or async)
        """
        if event_type not in self._consumers:
            self._consumers[event_type] = []
        self._consumers[event_type].append(consumer)
    
    def off(self, event_type: Enum, consumer: Callable[[Event], None]) -> None:
        """Unregister event consumer
        
        Args:
            event_type: Type of events to stop consuming
            consumer: Callback function to remove
        """
        if event_type in self._consumers:
            try:
                self._consumers[event_type].remove(consumer)
            except ValueError:
                pass  # Consumer not in list
    
    async def publish(self, event: Event) -> None:
        """Publish event asynchronously
        
        Events are queued and processed by a background task.
        If the queue is full, this method will block until space
        is available.
        
        Args:
            event: Event to publish
        """
        try:
            await self._queue.put(event)
        except asyncio.QueueFull:
            logger.warning(f"Event queue full, dropping event: {event}")
    
    def publish_nowait(self, event: Event) -> None:
        """Publish event without waiting
        
        If the queue is full, the event will be dropped.
        
        Args:
            event: Event to publish
        """
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(f"Event queue full, dropping event: {event}")
    
    async def start(self) -> None:
        """Start event processing
        
        This method starts a background task that processes events
        from the queue and distributes them to consumers.
        """
        if self._running:
            return
            
        self._running = True
        self._task = asyncio.create_task(self._process_events())
    
    async def stop(self) -> None:
        """Stop event processing
        
        This method stops the background processing task and waits
        for all queued events to be processed.
        """
        self._running = False
        if self._task:
            # Process remaining events in queue
            while not self._queue.empty():
                try:
                    event = self._queue.get_nowait()
                    await self._process_event(event)
                except asyncio.QueueEmpty:
                    break
            
            # Cancel the background task
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _process_events(self) -> None:
        """Background task for processing events"""
        while self._running:
            try:
                # Wait for event with timeout to allow checking _running flag
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._process_event(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing events: {e}", exc_info=True)
    
    async def _process_event(self, event: Event) -> None:
        """Process single event by distributing to consumers
        
        Args:
            event: Event to process
        """
        consumers = self._consumers.get(event.event_type, [])
        for consumer in consumers:
            try:
                if asyncio.iscoroutinefunction(consumer):
                    await consumer(event)
                else:
                    # Run sync consumer in thread pool to avoid blocking
                    await asyncio.get_event_loop().run_in_executor(
                        None, consumer, event
                    )
            except Exception as e:
                # Log error but don't stop processing other consumers
                logger.error(
                    f"Error in event consumer {consumer.__name__}: {e}",
                    exc_info=True
                )
    
    def __enter__(self) -> "EventPublisher":
        """Context manager entry"""
        asyncio.create_task(self.start())
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit"""
        asyncio.create_task(self.stop())

    async def __aenter__(self) -> "EventPublisher":
        """Async context manager entry"""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit"""
        await self.stop()