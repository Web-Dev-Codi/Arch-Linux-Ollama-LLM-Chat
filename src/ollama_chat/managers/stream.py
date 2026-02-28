"""Stream management for assistant responses.

Handles streaming responses, placeholder animation, error handling, and interruption.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ollama_chat.chat import ChatSendOptions, OllamaChat
    from ollama_chat.state import StateManager
    from ollama_chat.task_manager import TaskManager
    from ollama_chat.widgets.message import MessageBubble


class StreamManager:
    """Manages streaming responses from the LLM.

    Responsibilities:
    - Response placeholder animation
    - Streaming chunk processing
    - Error handling and recovery
    - Stream interruption/cancellation
    """

    PLACEHOLDER_FRAMES: tuple[str, ...] = (
        "🤖 Warming up the tiny token factory...",
        "🧠 Reassembling thoughts into words...",
        "🛰️ Polling satellites for better adjectives...",
        "🪄 Convincing electrons to be helpful...",
        "🐢 Racing your prompt at light-ish speed...",
    )

    def __init__(
        self,
        chat: OllamaChat,
        state_manager: StateManager,
        task_manager: TaskManager,
        *,
        chunk_size: int = 5,
    ) -> None:
        """Initialize stream manager.

        Args:
            chat: OllamaChat instance for API communication
            state_manager: StateManager for conversation state tracking
            task_manager: TaskManager for async task coordination
            chunk_size: Number of characters to process per UI update
        """
        self.chat = chat
        self.state = state_manager
        self.task_manager = task_manager
        self.chunk_size = chunk_size
        self._on_subtitle_change: Callable[[str], None] | None = None
        self._on_statusbar_update: Callable[[], None] | None = None

    def on_subtitle_change(self, callback: Callable[[str], None]) -> None:
        """Register callback for subtitle updates."""
        self._on_subtitle_change = callback

    def on_statusbar_update(self, callback: Callable[[], None]) -> None:
        """Register callback for status bar updates."""
        self._on_statusbar_update = callback

    async def animate_response_placeholder(self, bubble: MessageBubble) -> None:
        """Animate placeholder text while waiting for response.

        Runs in a background task until cancelled via stop_response_indicator().

        Args:
            bubble: MessageBubble to update with animation frames
        """
        frame_index = 0
        while True:
            bubble.set_content(
                self.PLACEHOLDER_FRAMES[frame_index % len(self.PLACEHOLDER_FRAMES)]
            )
            frame_index += 1
            await asyncio.sleep(0.35)

    async def stop_response_indicator(self) -> None:
        """Stop the response placeholder animation task."""
        await self.task_manager.cancel("response_indicator")

    async def stream_response(
        self,
        user_text: str,
        assistant_bubble: MessageBubble,
        scroll_callback: Callable[[], None],
        options: ChatSendOptions,
    ) -> None:
        """Stream assistant response with real-time UI updates.

        Args:
            user_text: User's prompt text
            assistant_bubble: MessageBubble to populate with response
            scroll_callback: Function to scroll conversation view
            options: ChatSendOptions (tools, images, thinking, etc.)

        Raises:
            OllamaChatError: On streaming errors (caught by caller)
            asyncio.CancelledError: If stream is interrupted
        """
        from ollama_chat.stream_handler import StreamHandler

        if self._on_subtitle_change:
            self._on_subtitle_change("Waiting for response...")

        # Start placeholder animation
        self.task_manager.add(
            asyncio.create_task(self.animate_response_placeholder(assistant_bubble)),
            name="response_indicator",
        )

        handler = StreamHandler(
            bubble=assistant_bubble,
            scroll_callback=scroll_callback,
            chunk_size=self.chunk_size,
        )

        try:
            async for chunk in self.chat.send(user_text, options=options):
                if chunk.kind == "thinking":
                    await handler.handle_thinking(
                        chunk.text, self.stop_response_indicator
                    )
                elif chunk.kind == "content":
                    await handler.handle_content(
                        chunk.text, self.stop_response_indicator
                    )
                elif chunk.kind == "tool_call":
                    await handler.handle_tool_call(
                        chunk.tool_name,
                        chunk.tool_args,
                        self.stop_response_indicator,
                    )
                elif chunk.kind == "tool_result":
                    handler.handle_tool_result(chunk.tool_name, chunk.tool_result)

                # Update subtitle with handler status
                if handler.status and self._on_subtitle_change:
                    self._on_subtitle_change(handler.status)

            await handler.finalize()

            # Update status bar after completion
            if self._on_statusbar_update:
                self._on_statusbar_update()
        finally:
            await self.stop_response_indicator()

    async def handle_stream_error(
        self,
        bubble: MessageBubble | None,
        message: str,
        subtitle: str,
        add_message_callback: Callable[[str, str, str], object] | None = None,
        timestamp_callback: Callable[[], str] | None = None,
    ) -> None:
        """Handle streaming errors and update UI.

        Args:
            bubble: MessageBubble to update with error (if exists)
            message: Error message to display
            subtitle: Subtitle text to set
            add_message_callback: Function to add new message if bubble is None
            timestamp_callback: Function to generate timestamp
        """
        from ollama_chat.state import ConversationState

        await self.state.transition_to(ConversationState.ERROR)

        if bubble is None and add_message_callback and timestamp_callback:
            await add_message_callback(message, "assistant", timestamp_callback())
        elif bubble is not None:
            bubble.set_content(message)

        if self._on_subtitle_change:
            self._on_subtitle_change(subtitle)

    async def interrupt_stream(self, model_name: str) -> bool:
        """Interrupt active streaming response.

        Args:
            model_name: Model name for idle subtitle

        Returns:
            True if stream was interrupted, False if no stream was active
        """
        from ollama_chat.state import ConversationState

        if await self.state.get_state() != ConversationState.STREAMING:
            return False

        await self.state.transition_to(ConversationState.CANCELLING)
        if self._on_subtitle_change:
            self._on_subtitle_change("Interrupting response...")

        await self.task_manager.cancel("active_stream")

        # Set idle subtitle
        if self._on_subtitle_change:
            self._on_subtitle_change(f"Model: {model_name}")

        return True
