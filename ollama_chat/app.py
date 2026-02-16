"""Main Textual application for chatting with Ollama."""

from __future__ import annotations

import asyncio
from datetime import datetime
import inspect
import logging
import os
import shutil
import subprocess
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, OptionList, Static

from .chat import OllamaChat
from .config import load_config
from .exceptions import (
    OllamaChatError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaStreamingError,
)
from .logging_utils import configure_logging
from .persistence import ConversationPersistence
from .state import ConversationState, StateManager
from .widgets.conversation import ConversationView
from .widgets.input_box import InputBox
from .widgets.message import MessageBubble
from .widgets.status_bar import StatusBar

LOGGER = logging.getLogger(__name__)


class ModelPickerScreen(ModalScreen[str | None]):
    """Modal picker for selecting a configured Ollama model."""

    CSS = """
    ModelPickerScreen {
        align: center middle;
    }

    #model-picker-dialog {
        width: 50;
        max-height: 22;
        padding: 1 2;
        border: round $panel;
        background: $surface;
    }

    #model-picker-title {
        padding-bottom: 1;
        text-style: bold;
    }

    #model-picker-help {
        padding-top: 1;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "Close", show=False)]

    def __init__(self, models: list[str], active_model: str) -> None:
        super().__init__()
        self.models = models
        self.active_model = active_model

    @staticmethod
    def _name_matches(requested_model: str, candidate_model: str) -> bool:
        requested = requested_model.strip().lower()
        candidate = candidate_model.strip().lower()
        if requested == candidate:
            return True
        if ":" not in requested and candidate.startswith(f"{requested}:"):
            return True
        return False

    def compose(self) -> ComposeResult:
        with Container(id="model-picker-dialog"):
            yield Static("Select model from config", id="model-picker-title")
            yield OptionList(*self.models, id="model-picker-options")
            yield Static("Enter/click to select  |  Esc to cancel", id="model-picker-help")

    def on_mount(self) -> None:
        options = self.query_one("#model-picker-options", OptionList)
        selected_index = 0
        for index, model_name in enumerate(self.models):
            if self._name_matches(self.active_model, model_name):
                selected_index = index
                break
        options.highlighted = selected_index

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_index = getattr(event, "option_index", None)
        if option_index is None:
            option_index = getattr(event, "index", -1)
        try:
            selected_index = int(option_index)
        except (TypeError, ValueError):
            selected_index = -1
        if 0 <= selected_index < len(self.models):
            self.dismiss(self.models[selected_index])

    def action_cancel(self) -> None:
        self.dismiss(None)


class OllamaChatApp(App[None]):
    """ChatGPT-style TUI app powered by local Ollama models."""

    CSS = """
    Screen {
        layout: vertical;
        background: $background;
    }

    #app-root {
        layout: vertical;
        width: 100%;
        height: 1fr;
        background: $background;
    }

    Header {
        border-bottom: solid $panel;
        background: $surface;
    }

    Footer {
        border-top: solid $panel;
        background: $surface;
    }

    #conversation {
        height: 1fr;
        padding: 1;
    }

    InputBox {
        height: auto;
        padding: 0 1 1 1;
        border-top: solid $panel;
        background: $surface;
    }

    #message_input {
        width: 1fr;
    }

    #send_button {
        margin-left: 1;
        min-width: 10;
    }

    #status_bar {
        height: auto;
        padding: 0 1;
        border-top: solid $panel;
        background: $surface;
    }

    MessageBubble {
        width: 85%;
        margin: 1 0;
        padding: 1 2;
        border: round $panel;
    }

    .message-user {
        align-horizontal: right;
        background: $primary;
    }

    .message-assistant {
        align-horizontal: left;
        background: $surface;
    }
    """

    DEFAULT_ACTION_DESCRIPTIONS: dict[str, str] = {
        "send_message": "Send",
        "new_conversation": "New Chat",
        "quit": "Quit",
        "scroll_up": "Scroll Up",
        "scroll_down": "Scroll Down",
        "command_palette": "🧭 Palette",
        "toggle_model_picker": "Model",
        "save_conversation": "Save",
        "load_conversation": "Load",
        "export_conversation": "Export",
        "search_messages": "Search",
        "copy_last_message": "Copy Last",
    }

    KEY_TO_ACTION: dict[str, str] = {
        "send_message": "send_message",
        "new_conversation": "new_conversation",
        "quit": "quit",
        "scroll_up": "scroll_up",
        "scroll_down": "scroll_down",
        "command_palette": "command_palette",
        "toggle_model_picker": "toggle_model_picker",
        "save_conversation": "save_conversation",
        "load_conversation": "load_conversation",
        "export_conversation": "export_conversation",
        "search_messages": "search_messages",
        "copy_last_message": "copy_last_message",
    }

    RESPONSE_PLACEHOLDER_FRAMES: tuple[str, ...] = (
        "🤖 Warming up the tiny token factory...",
        "🧠 Reassembling thoughts into words...",
        "🛰️ Polling satellites for better adjectives...",
        "🪄 Convincing electrons to be helpful...",
        "🐢 Racing your prompt at light-ish speed...",
    )

    def __init__(self) -> None:
        self.config = load_config()
        self.window_title = str(self.config["app"]["title"])
        self.window_class = str(self.config["app"]["class"])
        configure_logging(self.config["logging"])

        ollama_cfg = self.config["ollama"]
        configured_default_model = str(ollama_cfg["model"])
        self._configured_models = self._normalize_configured_models(
            raw_models=ollama_cfg.get("models"),
            default_model=configured_default_model,
        )
        self.chat = OllamaChat(
            host=str(ollama_cfg["host"]),
            model=configured_default_model,
            system_prompt=str(ollama_cfg["system_prompt"]),
            timeout=int(ollama_cfg["timeout"]),
            max_history_messages=int(ollama_cfg["max_history_messages"]),
            max_context_tokens=int(ollama_cfg["max_context_tokens"]),
        )
        self.state = StateManager()
        self._active_stream_task: asyncio.Task[None] | None = None
        self._connection_monitor_task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._connection_state = "unknown"
        self._search_query = ""
        self._search_results: list[int] = []
        self._search_position = -1
        self._startup_model_task: asyncio.Task[None] | None = None
        self._response_indicator_task: asyncio.Task[None] | None = None
        persistence_cfg = self.config["persistence"]
        self.persistence = ConversationPersistence(
            enabled=bool(persistence_cfg["enabled"]),
            directory=str(persistence_cfg["directory"]),
            metadata_path=str(persistence_cfg["metadata_path"]),
        )
        self._binding_specs = self._binding_specs_from_config(self.config)
        self._apply_terminal_window_identity()
        super().__init__()

    @classmethod
    def _binding_specs_from_config(cls, config: dict[str, dict[str, Any]]) -> list[Binding]:
        keybinds = config.get("keybinds", {})
        bindings: list[Binding] = []
        for key, action_name in cls.KEY_TO_ACTION.items():
            binding_key = keybinds.get(key)
            if isinstance(binding_key, str) and binding_key.strip():
                bindings.append(
                    Binding(
                        key=binding_key.strip(),
                        action=action_name,
                        description=cls.DEFAULT_ACTION_DESCRIPTIONS.get(key, action_name),
                        show=True,
                    )
                )
        return bindings

    @staticmethod
    def _normalize_configured_models(raw_models: Any, default_model: str) -> list[str]:
        configured: list[str] = []
        if isinstance(raw_models, list):
            for item in raw_models:
                if not isinstance(item, str):
                    continue
                candidate = item.strip()
                if candidate and candidate not in configured:
                    configured.append(candidate)

        normalized_default = default_model.strip()
        if not configured:
            configured = [normalized_default]
        if normalized_default and normalized_default not in configured:
            configured.insert(0, normalized_default)
        return configured

    def _command_palette_key_display(self) -> str:
        for binding in self._binding_specs:
            if binding.action == "command_palette":
                return binding.key.upper()
        return "CTRL+P"

    def _set_idle_sub_title(self, prefix: str) -> None:
        palette_hint = f"🧭 Palette: {self._command_palette_key_display()}"
        self.sub_title = f"{prefix}  |  {palette_hint}"

    def _apply_terminal_window_identity(self) -> None:
        """Best-effort terminal identity setup for title and class."""
        self._emit_osc("0", self.window_title)
        self._emit_osc("2", self.window_title)
        if self.window_class.strip():
            self._emit_osc("1", self.window_class.strip())
        self._set_window_class_best_effort()

    @staticmethod
    def _emit_osc(code: str, value: str) -> None:
        if not value.strip():
            return
        print(f"\033]{code};{value}\007", end="", flush=True)

    def _discover_window_id(self) -> str | None:
        window_id = os.environ.get("WINDOWID", "").strip()
        if window_id:
            return window_id
        return None

    def _set_window_class_best_effort(self) -> None:
        class_name = self.window_class.strip()
        if not class_name:
            return
        xprop_bin = shutil.which("xprop")
        if xprop_bin is None:
            return

        window_id = self._discover_window_id()
        if window_id is None:
            return

        try:
            subprocess.run(
                [
                    xprop_bin,
                    "-id",
                    window_id,
                    "-f",
                    "WM_CLASS",
                    "8s",
                    "-set",
                    "WM_CLASS",
                    f"{class_name},{class_name}",
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=0.2,
            )
        except Exception:
            return

    def _build_header(self) -> Header:
        """Return header with visual hamburger icon when supported."""
        try:
            return Header(name=self.window_title, icon="☰")
        except TypeError:
            return Header(name=self.window_title)

    def compose(self) -> ComposeResult:
        """Compose app widgets."""
        yield self._build_header()
        with Container(id="app-root"):
            yield ConversationView(id="conversation")
            yield InputBox()
            yield StatusBar(id="status_bar")
        yield Footer()

    async def on_mount(self) -> None:
        """Apply theme and register runtime keybindings."""
        self.title = self.window_title
        self._set_idle_sub_title(f"Model: {self.chat.model}")
        LOGGER.info("app.state.transition", extra={"event": "app.state.transition", "to_state": "IDLE"})
        self._apply_theme()
        for binding in self._binding_specs:
            self.bind(
                binding.key,
                binding.action,
                description=binding.description,
                show=binding.show,
                key_display=binding.key_display,
            )

        input_widget = self.query_one("#message_input", Input)
        send_button = self.query_one("#send_button", Button)
        input_widget.disabled = True
        send_button.disabled = True
        self._update_status_bar()

        self._startup_model_task = asyncio.create_task(self._prepare_startup_model())
        self._background_tasks.add(self._startup_model_task)
        self._startup_model_task.add_done_callback(self._background_tasks.discard)

        self._connection_monitor_task = asyncio.create_task(self._connection_monitor_loop())
        self._background_tasks.add(self._connection_monitor_task)

    async def _prepare_startup_model(self) -> None:
        """Warm up model in background so UI stays responsive on launch."""
        input_widget = self.query_one("#message_input", Input)
        send_button = self.query_one("#send_button", Button)
        try:
            await self._ensure_startup_model_ready()
        finally:
            input_widget.disabled = False
            send_button.disabled = False
            input_widget.focus()
            self._update_status_bar()

    async def _ensure_startup_model_ready(self) -> None:
        """Ensure configured model is available before interactive usage."""
        pull_on_start = bool(self.config["ollama"].get("pull_model_on_start", True))
        self.sub_title = f"Preparing model: {self.chat.model}"
        try:
            await self.chat.ensure_model_ready(pull_if_missing=pull_on_start)
            self._connection_state = "online"
            self._set_idle_sub_title(f"Model ready: {self.chat.model}")
        except OllamaConnectionError:
            self._connection_state = "offline"
            self.sub_title = "Cannot reach Ollama. Start ollama serve."
        except OllamaModelNotFoundError:
            self._connection_state = "online"
            self.sub_title = (
                f"Model not available: {self.chat.model}. "
                "Enable pull_model_on_start or run ollama pull manually."
            )
        except OllamaStreamingError:
            self._connection_state = "offline"
            self.sub_title = "Failed while preparing model."
        except OllamaChatError:
            self.sub_title = "Model preparation failed."

    def _apply_theme(self) -> None:
        """Apply fallback theme settings and restyle mounted widgets."""
        ui_cfg = self.config["ui"]
        use_theme_palette = self._using_theme_palette()
        if hasattr(self, "theme_variables") and isinstance(self.theme_variables, dict):
            fallback_variables = {
                "fallback_background": str(ui_cfg["background_color"]),
                "fallback_panel": str(ui_cfg["border_color"]),
                "fallback_user_message": str(ui_cfg["user_message_color"]),
                "fallback_assistant_message": str(ui_cfg["assistant_message_color"]),
            }
            for key, value in fallback_variables.items():
                self.theme_variables.setdefault(key, value)

        try:
            root = self.query_one("#app-root", Container)
            if not use_theme_palette:
                root.styles.background = str(ui_cfg["background_color"])
        except Exception:
            pass

        self._restyle_rendered_bubbles()

    def watch_theme(self, *_args: str) -> None:
        """Ensure all widgets react when a Textual theme changes."""
        self._apply_theme()

    @property
    def show_timestamps(self) -> bool:
        return bool(self.config["ui"]["show_timestamps"])

    def _timestamp(self) -> str:
        if not self.show_timestamps:
            return ""
        return datetime.now().strftime("%H:%M:%S")

    def _style_bubble(self, bubble: MessageBubble, role: str) -> None:
        use_theme_palette = self._using_theme_palette()
        ui_cfg = self.config["ui"]
        if role == "user":
            bubble.styles.align_horizontal = "right"
            if not use_theme_palette:
                bubble.styles.background = str(ui_cfg["user_message_color"])
        else:
            bubble.styles.align_horizontal = "left"
            if not use_theme_palette:
                bubble.styles.background = str(ui_cfg["assistant_message_color"])
        if not use_theme_palette:
            bubble.styles.border = ("round", str(ui_cfg["border_color"]))

    def _restyle_rendered_bubbles(self) -> None:
        try:
            conversation = self.query_one(ConversationView)
        except Exception:
            return
        for bubble in conversation.children:
            if isinstance(bubble, MessageBubble):
                self._style_bubble(bubble, bubble.role)

    def _using_theme_palette(self) -> bool:
        return bool(getattr(self, "theme", ""))

    def _update_status_bar(self) -> None:
        message_count = sum(1 for message in self.chat.messages if message.get("role") != "system")
        status_widget = self.query_one("#status_bar", StatusBar)
        status_widget.set_status(
            connection_state=self._connection_state,
            model=self.chat.model,
            message_count=message_count,
            estimated_tokens=self.chat.estimated_context_tokens,
        )

    async def _open_configured_model_picker(self) -> None:
        if await self.state.get_state() != ConversationState.IDLE:
            self.sub_title = "Model switch is available only when idle."
            return
        configured_models = list(self._configured_models)
        if not configured_models:
            self.sub_title = "No configured models found in config."
            return
        self.push_screen(
            ModelPickerScreen(configured_models, self.chat.model),
            callback=self._on_model_picker_dismissed,
        )

    def _on_model_picker_dismissed(self, selected_model: str | None) -> None:
        if selected_model is None:
            return
        task = asyncio.create_task(self._activate_selected_model(selected_model))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _activate_selected_model(self, model_name: str) -> None:
        if await self.state.get_state() != ConversationState.IDLE:
            self.sub_title = "Model switch is available only when idle."
            return
        if model_name not in self._configured_models:
            self.sub_title = f"Model is not configured: {model_name}"
            return

        previous_model = self.chat.model
        self.chat.set_model(model_name)
        self.sub_title = f"Switching model: {model_name}"
        try:
            await self.chat.ensure_model_ready(pull_if_missing=False)
            self._connection_state = "online"
            self._set_idle_sub_title(f"Active model: {model_name}")
        except OllamaConnectionError:
            self.chat.set_model(previous_model)
            self._connection_state = "offline"
            self.sub_title = "Unable to switch model while offline."
        except OllamaModelNotFoundError:
            self.chat.set_model(previous_model)
            self._set_idle_sub_title(
                f"Configured model unavailable in Ollama: {model_name}"
            )
        except OllamaStreamingError:
            self.chat.set_model(previous_model)
            self.sub_title = "Failed while validating selected model."
        except OllamaChatError:
            self.chat.set_model(previous_model)
            self.sub_title = "Model switch failed."
        finally:
            self._update_status_bar()

    async def _connection_monitor_loop(self) -> None:
        interval = int(self.config["app"]["connection_check_interval_seconds"])
        try:
            while True:
                connected = await self.chat.check_connection()
                new_state = "online" if connected else "offline"
                if new_state != self._connection_state:
                    self._connection_state = new_state
                    LOGGER.info(
                        "app.connection.state",
                        extra={"event": "app.connection.state", "connection_state": new_state},
                    )
                    if await self.state.get_state() == ConversationState.IDLE:
                        self._set_idle_sub_title(f"Connection: {new_state}")
                self._update_status_bar()
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            LOGGER.info("app.connection.monitor.stopped", extra={"event": "app.connection.monitor.stopped"})
            raise

    async def _add_message(self, content: str, role: str, timestamp: str = "") -> MessageBubble:
        conversation = self.query_one(ConversationView)
        bubble = await conversation.add_message(content=content, role=role, timestamp=timestamp)
        self._style_bubble(bubble, role)
        return bubble

    async def on_status_bar_model_picker_requested(self, _message: StatusBar.ModelPickerRequested) -> None:
        """Open configured model picker from StatusBar model segment click."""
        await self._open_configured_model_picker()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle send button clicks."""
        if event.button.id == "send_button":
            await self.send_user_message()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submit events."""
        if event.input.id == "message_input":
            await self.send_user_message()

    async def action_send_message(self) -> None:
        """Action invoked by keybinding for sending a message."""
        await self.send_user_message()

    async def _transition_state(self, new_state: ConversationState) -> None:
        previous = await self.state.get_state()
        await self.state.transition_to(new_state)
        LOGGER.info(
            "app.state.transition",
            extra={
                "event": "app.state.transition",
                "from_state": previous.value,
                "to_state": new_state.value,
            },
        )

    async def _animate_response_placeholder(self, assistant_bubble: MessageBubble) -> None:
        frame_index = 0
        while True:
            assistant_bubble.set_content(
                self.RESPONSE_PLACEHOLDER_FRAMES[frame_index % len(self.RESPONSE_PLACEHOLDER_FRAMES)]
            )
            frame_index += 1
            await asyncio.sleep(0.35)

    async def _stop_response_indicator_task(self) -> None:
        task = self._response_indicator_task
        self._response_indicator_task = None
        if task is None:
            return
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _stream_assistant_response(self, user_text: str, assistant_bubble: MessageBubble) -> None:
        chunk_size = max(1, int(self.config["ui"]["stream_chunk_size"]))
        display_buffer: list[str] = []
        response_chunks: list[str] = []
        self.sub_title = "Waiting for response..."
        self._response_indicator_task = asyncio.create_task(self._animate_response_placeholder(assistant_bubble))

        try:
            async for chunk in self.chat.send_message(user_text):
                if not response_chunks:
                    self.sub_title = "Streaming response..."
                    await self._stop_response_indicator_task()
                    assistant_bubble.set_content("")
                response_chunks.append(chunk)
                display_buffer.append(chunk)
                if len(display_buffer) >= chunk_size:
                    assistant_bubble.append_content("".join(display_buffer))
                    display_buffer.clear()
                    self.query_one(ConversationView).scroll_end(animate=False)

            if display_buffer:
                assistant_bubble.append_content("".join(display_buffer))
                self.query_one(ConversationView).scroll_end(animate=False)

            if not response_chunks:
                assistant_bubble.set_content("(No response from model.)")
            self._update_status_bar()
        finally:
            await self._stop_response_indicator_task()

    async def send_user_message(self) -> None:
        """Collect input text and stream the assistant response into the UI."""
        if not await self.state.can_send_message():
            self.sub_title = "Busy. Wait for current request to finish."
            return

        input_widget = self.query_one("#message_input", Input)
        send_button = self.query_one("#send_button", Button)
        user_text = input_widget.value.strip()
        if not user_text:
            self.sub_title = "Cannot send an empty message."
            return

        assistant_bubble: MessageBubble | None = None
        transitioned = await self.state.transition_if(ConversationState.IDLE, ConversationState.STREAMING)
        if not transitioned:
            self.sub_title = "Busy. Wait for current request to finish."
            return
        LOGGER.info(
            "app.state.transition",
            extra={"event": "app.state.transition", "from_state": "IDLE", "to_state": "STREAMING"},
        )
        input_widget.disabled = True
        send_button.disabled = True
        try:
            self.sub_title = "Sending message..."
            await self._add_message(content=user_text, role="user", timestamp=self._timestamp())
            input_widget.value = ""
            assistant_bubble = await self._add_message(content="", role="assistant", timestamp=self._timestamp())

            self._active_stream_task = asyncio.create_task(self._stream_assistant_response(user_text, assistant_bubble))
            self._background_tasks.add(self._active_stream_task)
            try:
                await self._active_stream_task
            finally:
                self._background_tasks.discard(self._active_stream_task)
                self._active_stream_task = None
            self._set_idle_sub_title("Ready")
        except asyncio.CancelledError:
            self.sub_title = "Request cancelled."
            LOGGER.info("chat.request.cancelled", extra={"event": "chat.request.cancelled"})
            return
        except OllamaConnectionError:
            await self._transition_state(ConversationState.ERROR)
            error_message = "Connection error. Verify Ollama service and host configuration."
            if assistant_bubble is None:
                assistant_bubble = await self._add_message(content=error_message, role="assistant", timestamp=self._timestamp())
            else:
                assistant_bubble.set_content(error_message)
            self.sub_title = "Connection error"
        except OllamaModelNotFoundError:
            await self._transition_state(ConversationState.ERROR)
            error_message = "Model not found. Verify the configured ollama.model value."
            if assistant_bubble is None:
                assistant_bubble = await self._add_message(content=error_message, role="assistant", timestamp=self._timestamp())
            else:
                assistant_bubble.set_content(error_message)
            self.sub_title = "Model not found"
        except OllamaStreamingError:
            await self._transition_state(ConversationState.ERROR)
            error_message = "Streaming error. Please retry your message."
            if assistant_bubble is None:
                assistant_bubble = await self._add_message(content=error_message, role="assistant", timestamp=self._timestamp())
            else:
                assistant_bubble.set_content(error_message)
            self.sub_title = "Streaming error"
        except OllamaChatError:
            await self._transition_state(ConversationState.ERROR)
            error_message = "Chat error. Please review settings and try again."
            if assistant_bubble is None:
                assistant_bubble = await self._add_message(content=error_message, role="assistant", timestamp=self._timestamp())
            else:
                assistant_bubble.set_content(error_message)
            self.sub_title = "Chat error"
        finally:
            input_widget.disabled = False
            send_button.disabled = False
            input_widget.focus()
            if await self.state.get_state() != ConversationState.CANCELLING:
                await self._transition_state(ConversationState.IDLE)
            self._update_status_bar()

    async def action_new_conversation(self) -> None:
        """Clear UI and in-memory conversation history."""
        if await self.state.get_state() == ConversationState.STREAMING and self._active_stream_task is not None:
            task = self._active_stream_task
            await self._transition_state(ConversationState.CANCELLING)
            LOGGER.info("chat.request.cancelling", extra={"event": "chat.request.cancelling"})
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                LOGGER.info("chat.request.cancelled", extra={"event": "chat.request.cancelled"})
            finally:
                self._background_tasks.discard(task)
                self._active_stream_task = None

        self.chat.clear_history()
        await self._clear_conversation_view()
        self._search_query = ""
        self._search_results = []
        self._search_position = -1
        await self._transition_state(ConversationState.IDLE)
        self._set_idle_sub_title(f"Model: {self.chat.model}")
        self._update_status_bar()

    async def _clear_conversation_view(self) -> None:
        """Remove all rendered conversation bubbles."""
        conversation = self.query_one(ConversationView)
        if hasattr(conversation, "remove_children"):
            result = conversation.remove_children()
            if inspect.isawaitable(result):
                await result
        else:
            for child in list(conversation.children):
                result = child.remove()
                if inspect.isawaitable(result):
                    await result

    async def _render_messages_from_history(self, messages: list[dict[str, str]]) -> None:
        """Render persisted non-system messages into the conversation view."""
        for message in messages:
            role = str(message.get("role", "")).strip().lower()
            if role == "system":
                continue
            content = str(message.get("content", ""))
            await self._add_message(content=content, role=role, timestamp=self._timestamp())

    async def on_unmount(self) -> None:
        """Cancel and await all background tasks during shutdown."""
        await self._transition_state(ConversationState.CANCELLING)
        await self._stop_response_indicator_task()
        tasks: set[asyncio.Task[Any]] = {task for task in self._background_tasks if not task.done()}
        if self._active_stream_task is not None and not self._active_stream_task.done():
            tasks.add(self._active_stream_task)
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._active_stream_task = None
        self._connection_monitor_task = None
        self._background_tasks.clear()
        await self._transition_state(ConversationState.IDLE)

    async def action_quit(self) -> None:
        """Exit the app."""
        self.exit()

    def action_scroll_up(self) -> None:
        """Scroll conversation up."""
        conversation = self.query_one(ConversationView)
        conversation.scroll_relative(y=-10, animate=False)

    def action_scroll_down(self) -> None:
        """Scroll conversation down."""
        conversation = self.query_one(ConversationView)
        conversation.scroll_relative(y=10, animate=False)

    async def action_toggle_model_picker(self) -> None:
        """Open configured model picker while in IDLE state."""
        await self._open_configured_model_picker()

    async def action_save_conversation(self) -> None:
        """Persist the current conversation to disk."""
        if await self.state.get_state() != ConversationState.IDLE:
            self.sub_title = "Save is available only when idle."
            return
        if not self.persistence.enabled:
            self.sub_title = "Persistence is disabled in configuration."
            return
        try:
            path = self.persistence.save_conversation(self.chat.messages, self.chat.model)
            self.sub_title = f"Conversation saved: {path}"
        except Exception:
            self.sub_title = "Failed to save conversation."

    async def action_load_conversation(self) -> None:
        """Load the most recently saved conversation."""
        if await self.state.get_state() != ConversationState.IDLE:
            self.sub_title = "Load is available only when idle."
            return
        if not self.persistence.enabled:
            self.sub_title = "Persistence is disabled in configuration."
            return
        try:
            payload = self.persistence.load_latest_conversation()
        except Exception:
            self.sub_title = "Failed to read saved conversations."
            return
        if payload is None:
            self.sub_title = "No saved conversation found."
            return

        messages = payload.get("messages", [])
        model = payload.get("model", self.chat.model)
        if not isinstance(messages, list):
            self.sub_title = "Saved conversation format is invalid."
            return

        self.chat.load_history(messages)  # type: ignore[arg-type]
        if isinstance(model, str) and model.strip():
            self.chat.set_model(model.strip())
        await self._clear_conversation_view()
        await self._render_messages_from_history(self.chat.messages)
        self._set_idle_sub_title(f"Loaded conversation for model: {self.chat.model}")
        self._update_status_bar()

    async def action_export_conversation(self) -> None:
        """Export current conversation to markdown."""
        if await self.state.get_state() != ConversationState.IDLE:
            self.sub_title = "Export is available only when idle."
            return
        if not self.persistence.enabled:
            self.sub_title = "Persistence is disabled in configuration."
            return
        try:
            path = self.persistence.export_markdown(self.chat.messages, self.chat.model)
            self.sub_title = f"Exported markdown: {path}"
        except Exception:
            self.sub_title = "Failed to export conversation."

    def _jump_to_search_result(self, message_index: int) -> None:
        conversation = self.query_one(ConversationView)
        non_system_index = -1
        for index, message in enumerate(self.chat.messages):
            if message.get("role") == "system":
                continue
            non_system_index += 1
            if index == message_index:
                break
        bubbles = [child for child in conversation.children if isinstance(child, MessageBubble)]
        if 0 <= non_system_index < len(bubbles):
            target = bubbles[non_system_index]
            if hasattr(target, "scroll_visible"):
                target.scroll_visible(animate=False)
            conversation.scroll_end(animate=False)

    async def action_search_messages(self) -> None:
        """Search messages using input box text and cycle through results."""
        input_widget = self.query_one("#message_input", Input)
        query = input_widget.value.strip().lower()

        if not query and self._search_results:
            self._search_position = (self._search_position + 1) % len(self._search_results)
            current = self._search_results[self._search_position]
            self._jump_to_search_result(current)
            self.sub_title = f"Search {self._search_position + 1}/{len(self._search_results)}: {self._search_query}"
            return
        if not query:
            self.sub_title = "Type search text in the input box, then press search."
            return

        self._search_query = query
        self._search_results = [
            index
            for index, message in enumerate(self.chat.messages)
            if message.get("role") != "system" and query in str(message.get("content", "")).lower()
        ]
        self._search_position = 0
        if not self._search_results:
            self.sub_title = f"No matches for '{query}'."
            return
        self._jump_to_search_result(self._search_results[self._search_position])
        self.sub_title = f"Search {self._search_position + 1}/{len(self._search_results)}: {query}"

    async def action_copy_last_message(self) -> None:
        """Copy the latest assistant reply to clipboard when available."""
        for message in reversed(self.chat.messages):
            if message.get("role") != "assistant":
                continue
            content = str(message.get("content", "")).strip()
            if not content:
                continue
            if hasattr(self, "copy_to_clipboard"):
                self.copy_to_clipboard(content)  # type: ignore[attr-defined]
                self.sub_title = "Copied latest assistant message."
            else:
                input_widget = self.query_one("#message_input", Input)
                input_widget.value = content
                self.sub_title = "Clipboard unavailable. Message placed in input box."
            return
        self.sub_title = "No assistant message available to copy."
