"""Event bus for decoupled component communication.

Usage:
    bus = EventBus()

    # Subscribe to events
    async def on_file_changed(event):
        print(f"File changed: {event.data['file']}")

    bus.subscribe("file.changed", on_file_changed)

    # Publish events
    await bus.publish("file.changed", {"file": "/path/to/file"})
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any

LOGGER = logging.getLogger(__name__)


@dataclass
class Event:
    """Event data container."""

    name: str
    data: dict[str, Any]
    source: str | None = None


class EventBus:
    """Simple event bus for publish/subscribe pattern.

    Enables loose coupling between components by allowing them to
    communicate via events rather than direct method calls.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, event_name: str, handler: Callable) -> None:
        """Subscribe to an event.

        Args:
            event_name: Event to listen for (e.g., "file.changed")
            handler: Async function called when event is published
        """
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        self._subscribers[event_name].append(handler)
        LOGGER.debug(f"Subscribed to event: {event_name}")

    def unsubscribe(self, event_name: str, handler: Callable) -> None:
        """Unsubscribe from an event.

        Args:
            event_name: Event to stop listening to
            handler: Handler function to remove
        """
        if event_name in self._subscribers:
            try:
                self._subscribers[event_name].remove(handler)
                LOGGER.debug(f"Unsubscribed from event: {event_name}")
            except ValueError:
                pass

    async def publish(
        self, event_name: str, data: dict[str, Any], source: str | None = None
    ) -> None:
        """Publish an event to all subscribers.

        Args:
            event_name: Event name
            data: Event data
            source: Optional source identifier
        """
        event = Event(name=event_name, data=data, source=source)
        handlers = self._subscribers.get(event_name, [])

        if not handlers:
            LOGGER.debug(f"No subscribers for event: {event_name}")
            return

        # Call all handlers
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                LOGGER.error(f"Event handler failed for {event_name}: {e}")

    def clear(self, event_name: str | None = None) -> None:
        """Clear subscribers.

        Args:
            event_name: Specific event to clear, or None for all
        """
        if event_name:
            self._subscribers.pop(event_name, None)
        else:
            self._subscribers.clear()


# Global event bus instance
event_bus = EventBus()
