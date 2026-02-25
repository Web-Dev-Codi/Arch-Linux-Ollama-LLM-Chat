from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class _Subscriber:
    callback: Callable[[str, dict[str, Any]], None]


class Bus:
    """Very small in-process pub/sub bus.

    This is intentionally minimal; it is enough for tools to notify the UI or
    observers during tests without introducing external dependencies.
    """

    def __init__(self) -> None:
        self._subscribers: defaultdict[str, list[_Subscriber]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, event: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            for sub in list(self._subscribers.get(event, [])):
                try:
                    sub.callback(event, payload)
                except Exception:
                    continue

    def publish_nowait(self, event: str, payload: dict[str, Any]) -> None:
        for sub in list(self._subscribers.get(event, [])):
            try:
                sub.callback(event, payload)
            except Exception:
                continue

    def subscribe(self, event: str, callback: Callable[[str, dict[str, Any]], None]) -> None:
        self._subscribers[event].append(_Subscriber(callback))

    def unsubscribe(self, event: str, callback: Callable[[str, dict[str, Any]], None]) -> None:
        items = self._subscribers.get(event, [])
        self._subscribers[event] = [s for s in items if s.callback is not callback]


# Global bus instance convenient for modules
bus = Bus()
