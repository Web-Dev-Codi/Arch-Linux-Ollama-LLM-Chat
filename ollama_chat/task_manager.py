"""Structured lifecycle manager for asyncio background tasks."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

LOGGER = logging.getLogger(__name__)


class TaskManager:
    """Manage named and anonymous background asyncio tasks."""

    def __init__(self) -> None:
        self._named: dict[str, asyncio.Task[Any]] = {}
        self._anonymous: set[asyncio.Task[Any]] = set()

    def add(self, task: asyncio.Task[Any], name: str | None = None) -> None:
        """Register a task, optionally under a unique name.

        Named tasks replace any prior task with the same name (the old task
        is *not* cancelled automatically).  Anonymous tasks self-clean when
        they complete.
        """
        if name is not None:
            self._named[name] = task
        else:
            self._anonymous.add(task)
            task.add_done_callback(self._anonymous.discard)
            task.add_done_callback(self._log_anonymous_exception)

    def _log_anonymous_exception(self, task: asyncio.Task[Any]) -> None:
        """Log unhandled exceptions from anonymous tasks so they are not silently lost."""
        if task.cancelled():
            return
        try:
            exc = task.exception()
        except Exception:
            return
        if exc is not None:
            LOGGER.warning(
                "task.anonymous.exception",
                extra={
                    "event": "task.anonymous.exception",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )

    def get(self, name: str) -> asyncio.Task[Any] | None:
        """Return the named task or ``None`` if not registered."""
        return self._named.get(name)

    async def cancel(self, name: str) -> None:
        """Cancel a named task and await its completion."""
        task = self._named.pop(name, None)
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def cancel_all(self) -> None:
        """Cancel every tracked task and await them all."""
        all_tasks: list[asyncio.Task[Any]] = list(self._named.values()) + [
            t for t in self._anonymous if not t.done()
        ]
        for task in all_tasks:
            if not task.done():
                task.cancel()
        for task in all_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._named.clear()
        self._anonymous.clear()

    async def await_all(self) -> None:
        """Await all tracked tasks without cancelling them."""
        all_tasks: list[asyncio.Task[Any]] = list(self._named.values()) + list(
            self._anonymous
        )
        for task in all_tasks:
            if not task.done():
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    def discard(self, name: str) -> None:
        """Remove a named task from tracking without cancelling it."""
        self._named.pop(name, None)
