"""Message bubble widget for conversation rendering."""

from __future__ import annotations

from typing import Any

from rich.markdown import Markdown
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class MessageBubble(Vertical):
    """Render a single chat message with role, optional timestamp, thinking, and tool traces."""

    DEFAULT_CSS = """
    MessageBubble {
        height: auto;
    }
    MessageBubble > #thinking-block {
        color: $text-muted;
        padding: 0 1;
        border-left: solid $panel;
        margin-bottom: 1;
    }
    MessageBubble > #tool-trace {
        color: $text-muted;
        padding: 0 1;
        border-left: solid $warning;
        margin-bottom: 1;
    }
    MessageBubble > #content-block {
        height: auto;
    }
    """

    def __init__(
        self,
        content: str,
        role: str,
        timestamp: str = "",
        show_thinking: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.message_content = content
        self.role = role
        self.timestamp = timestamp
        self.show_thinking = show_thinking
        self._thinking_buffer = ""
        self._tool_trace_lines: list[str] = []
        self.add_class(f"role-{role}")

        # Direct references to inner widgets, set in compose() / on_mount().
        self._thinking_widget: Static | None = None
        self._tool_widget: Static | None = None
        self._content_widget: Static | None = None

    @property
    def role_prefix(self) -> str:
        """Return a human-friendly role label."""
        return "You" if self.role == "user" else "Assistant"

    def _compose_header(self) -> str:
        if self.timestamp:
            return f"**{self.role_prefix}**  _{self.timestamp}_\n\n"
        return f"**{self.role_prefix}**\n\n"

    def compose(self) -> ComposeResult:
        """Compose the bubble layout with optional thinking/tool sections."""
        self._thinking_widget = Static("", id="thinking-block")
        self._tool_widget = Static("", id="tool-trace")
        self._content_widget = Static("", id="content-block")
        if self.show_thinking:
            yield self._thinking_widget
        yield self._tool_widget
        yield self._content_widget

    def on_mount(self) -> None:
        """Perform initial render after mount."""
        self._refresh_content()

    def _refresh_content(self) -> None:
        if self._content_widget is None:
            return
        full_text = f"{self._compose_header()}{self.message_content}".rstrip()
        self._content_widget.update(Markdown(full_text))

    def _refresh_thinking(self) -> None:
        if not self.show_thinking or self._thinking_widget is None:
            return
        if self._thinking_buffer:
            self._thinking_widget.update(
                Text(f"Thinking:\n{self._thinking_buffer}", style="dim italic")
            )
            self._thinking_widget.display = True
        else:
            self._thinking_widget.display = False

    def _refresh_tool_trace(self) -> None:
        if self._tool_widget is None:
            return
        if self._tool_trace_lines:
            self._tool_widget.update(
                Text("\n".join(self._tool_trace_lines), style="dim")
            )
            self._tool_widget.display = True
        else:
            self._tool_widget.display = False

    def set_content(self, content: str) -> None:
        """Update message content and rerender."""
        self.message_content = content
        self._refresh_content()

    def append_content(self, content_chunk: str) -> None:
        """Append streamed content and rerender once per batch."""
        self.message_content += content_chunk
        self._refresh_content()

    def append_thinking(self, thinking_chunk: str) -> None:
        """Accumulate a streamed thinking token and rerender the thinking block."""
        self._thinking_buffer += thinking_chunk
        self._refresh_thinking()

    def finalize_thinking(self) -> None:
        """Seal the thinking block with a final label (called when content starts)."""
        if (
            not self.show_thinking
            or not self._thinking_buffer
            or self._thinking_widget is None
        ):
            return
        self._thinking_widget.update(
            Text(f"Thought:\n{self._thinking_buffer}", style="dim italic")
        )

    def append_tool_call(self, name: str, args: dict[str, Any]) -> None:
        """Add a tool-call line to the tool trace block."""
        args_repr = ", ".join(f"{k}={v!r}" for k, v in args.items())
        self._tool_trace_lines.append(f"> Calling: {name}({args_repr})")
        self._refresh_tool_trace()

    def append_tool_result(self, name: str, result: str) -> None:
        """Add a tool-result line to the tool trace block."""
        # Truncate very long results in the UI display.
        preview = result[:200] + "..." if len(result) > 200 else result
        self._tool_trace_lines.append(f"< {name}: {preview}")
        self._refresh_tool_trace()
