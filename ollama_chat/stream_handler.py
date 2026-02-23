"""Stream chunk handler that processes streaming response chunks into a MessageBubble."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class StreamHandler:
    """Processes streaming chunks and renders them into a MessageBubble.

    Accepts a bubble and a scroll callback to decouple from direct UI references.
    """

    def __init__(
        self,
        bubble: Any,
        scroll_callback: Callable[[], None],
        chunk_size: int = 1,
    ) -> None:
        self._bubble = bubble
        self._scroll = scroll_callback
        self._chunk_size = max(1, chunk_size)
        self.response_started: bool = False
        self.thinking_started: bool = False
        self._content_buffer: list[str] = []
        self._status: str = ""

    @property
    def status(self) -> str:
        """Return the latest status text set during chunk processing."""
        return self._status

    async def handle_thinking(
        self,
        text: str,
        stop_indicator: Callable[[], Any],
    ) -> None:
        """Process a thinking chunk."""
        if not self.response_started:
            await stop_indicator()
            self._bubble.set_content("")
            self.response_started = True
        if not self.thinking_started:
            self.thinking_started = True
            self._status = "Thinking..."
        self._bubble.append_thinking(text)
        self._scroll()

    async def handle_content(
        self,
        text: str,
        stop_indicator: Callable[[], Any],
    ) -> None:
        """Process a content chunk with batched rendering."""
        if not self.response_started:
            await stop_indicator()
            self._bubble.set_content("")
            self.response_started = True
        if self.thinking_started:
            self._bubble.finalize_thinking()
            self.thinking_started = False
            self._status = "Streaming response..."
        self._content_buffer.append(text)
        if len(self._content_buffer) >= self._chunk_size:
            self.flush_buffer()

    async def handle_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        stop_indicator: Callable[[], Any],
    ) -> None:
        """Process a tool_call chunk."""
        if not self.response_started:
            await stop_indicator()
            self._bubble.set_content("")
            self.response_started = True
        self.flush_buffer()
        self._bubble.append_tool_call(tool_name, tool_args)
        self._status = f"Calling tool: {tool_name}..."
        self._scroll()

    def handle_tool_result(self, tool_name: str, tool_result: str) -> None:
        """Process a tool_result chunk."""
        self._bubble.append_tool_result(tool_name, tool_result)
        self._status = "Processing tool result..."
        self._scroll()

    def flush_buffer(self) -> None:
        """Flush any buffered content text into the bubble."""
        if self._content_buffer:
            self._bubble.append_content("".join(self._content_buffer))
            self._content_buffer.clear()
            self._scroll()

    async def finalize(self) -> None:
        """Flush remaining buffer and finalize the bubble content."""
        self.flush_buffer()
        if not self.response_started:
            self._bubble.set_content("(No response from model.)")
        await self._bubble.finalize_content()
