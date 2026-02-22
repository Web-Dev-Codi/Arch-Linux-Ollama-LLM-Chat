"""Activity bar widget showing job animation and keyboard shortcut hints."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from textual.app import ComposeResult
from textual.widgets import Label, Static

LOGGER = logging.getLogger(__name__)

_ANIMATION_FRAMES: tuple[str, ...] = (
    "·······",
    "●······",
    "·●·····",
    "··●····",
    "···●···",
    "····●··",
    "·····●·",
    "······●",
)


class ActivityBar(Static):
    """Render job activity animation and shortcut hints."""

    DEFAULT_CSS = """
    ActivityBar {
        layout: horizontal;
        height: 1;
        padding: 0 1;
    }
    ActivityBar #activity_left {
        width: 1fr;
    }
    ActivityBar #activity_right {
        width: auto;
        text-align: right;
    }
    """

    def __init__(
        self,
        shortcut_hints: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._shortcut_hints = shortcut_hints
        self._animation_task: asyncio.Task[None] | None = None
        self._running = False

    def compose(self) -> ComposeResult:
        """Compose left (animation) and right (shortcuts) labels."""
        yield Label("", id="activity_left")
        yield Label(self._shortcut_hints, id="activity_right")

    def set_shortcut_hints(self, hints: str) -> None:
        """Update the right-side shortcut hint text."""
        self._shortcut_hints = hints
        try:
            self.query_one("#activity_right", Label).update(hints)
        except Exception:
            pass

    def start_activity(self, hint: str = "esc interrupt") -> None:
        """Begin the animated dots and show the interrupt hint."""
        if self._running:
            return
        self._running = True
        self._animation_task = asyncio.create_task(self._animate(hint))

    def stop_activity(self) -> None:
        """Stop the animation and clear the left label."""
        self._running = False
        task = self._animation_task
        self._animation_task = None
        if task is not None and not task.done():
            task.cancel()
        try:
            self.query_one("#activity_left", Label).update("")
        except Exception:
            pass

    async def _animate(self, hint: str) -> None:
        """Cycle through animation frames until stopped."""
        left = self.query_one("#activity_left", Label)
        frame_index = 0
        try:
            while self._running:
                frame = _ANIMATION_FRAMES[frame_index % len(_ANIMATION_FRAMES)]
                left.update(f"{frame}  {hint}")
                frame_index += 1
                await asyncio.sleep(0.12)
        except asyncio.CancelledError:
            raise
        finally:
            left.update("")
