"""Code block widget with a copy-to-clipboard button."""

from __future__ import annotations

import logging
import re
from typing import Any

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Label, Static

LOGGER = logging.getLogger(__name__)

_FENCE_RE = re.compile(
    r"```(?P<lang>[^\n`]*)\n(?P<code>.*?)```",
    re.DOTALL,
)


def split_message(text: str) -> list[tuple[str, str | None]]:
    """Split *text* into alternating prose and code-block segments.

    Returns a list of ``(content, lang)`` tuples where ``lang`` is ``None``
    for prose segments and the fence language string (possibly empty) for
    code blocks.
    """
    segments: list[tuple[str, str | None]] = []
    cursor = 0
    for match in _FENCE_RE.finditer(text):
        start, end = match.span()
        if start > cursor:
            prose = text[cursor:start]
            if prose.strip():
                segments.append((prose, None))
        lang = match.group("lang").strip()
        code = match.group("code")
        segments.append((code, lang if lang else ""))
        cursor = end
    tail = text[cursor:]
    if tail.strip():
        segments.append((tail, None))
    return segments


class CodeBlock(Vertical):
    """Render a fenced code block with a copy button in the top-right corner."""

    DEFAULT_CSS = """
    CodeBlock {
        height: auto;
        margin: 1 0;
        border: solid $panel;
        background: $surface-darken-1;
    }
    CodeBlock > #code-header {
        height: 1;
        padding: 0 1;
        background: $panel;
    }
    CodeBlock > #code-header > #lang-label {
        width: 1fr;
        color: $text-muted;
    }
    CodeBlock > #code-header > #copy-btn {
        width: auto;
        min-width: 6;
        height: 1;
        border: none;
        background: $panel;
        color: $text;
        padding: 0 1;
    }
    CodeBlock > #code-header > #copy-btn:hover {
        background: $accent;
        color: $text;
    }
    CodeBlock > #code-body {
        height: auto;
        padding: 0 1;
    }
    """

    class CopyRequested(Message):
        """Posted when the user clicks the copy button."""

        def __init__(self, code: str) -> None:
            super().__init__()
            self.code = code

    def __init__(self, code: str, lang: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._code = code
        self._lang = lang

    def compose(self) -> ComposeResult:
        """Compose header (lang label + copy button) and syntax-highlighted body."""
        with Horizontal(id="code-header"):
            yield Label(self._lang or "code", id="lang-label")
            yield Button("⎘ copy", id="copy-btn")
        syntax = Syntax(
            self._code,
            self._lang or "text",
            theme="monokai",
            line_numbers=False,
            word_wrap=True,
        )
        yield Static(syntax, id="code-body")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle copy button click."""
        if event.button.id == "copy-btn":
            event.stop()
            self.post_message(self.CopyRequested(self._code))
