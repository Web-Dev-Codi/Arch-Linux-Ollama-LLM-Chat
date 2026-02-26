"""Activity bar widget showing job animation and keyboard shortcut hints."""

from __future__ import annotations

import logging
from typing import Any

from textual.app import ComposeResult
from textual.timer import Timer
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
        self._animation_timer: Timer | None = None
        self._running = False
        self._frame_index = 0
        self._hint = "esc interrupt"
        self._left_label: Label | None = None

    def compose(self) -> ComposeResult:
        """Compose left (animation) and right (shortcuts) labels."""
        yield Label("", id="activity_left")
        yield Label(self._shortcut_hints, id="activity_right")

    def on_mount(self) -> None:
        self._left_label = self.query_one("#activity_left", Label)

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
        self._hint = hint
        self._frame_index = 0
        self._update_left()
        self._animation_timer = self.set_interval(0.12, self._advance_frame)

    def stop_activity(self) -> None:
        """Stop the animation and clear the left label."""
        self._running = False
        if self._animation_timer is not None:
            self._animation_timer.stop()
            self._animation_timer = None
        if self._left_label is not None:
            self._left_label.update("")

    def _advance_frame(self) -> None:
        if not self._running:
            return
        self._frame_index = (self._frame_index + 1) % len(_ANIMATION_FRAMES)
        self._update_left()

    def _update_left(self) -> None:
        if self._left_label is None:
            return
        frame = _ANIMATION_FRAMES[self._frame_index % len(_ANIMATION_FRAMES)]
        self._left_label.update(f"{frame}  {self._hint}")
