"""Main Textual application for chatting with Ollama."""

from __future__ import annotations

import asyncio
from datetime import datetime
import inspect
import logging
import os
import sys
import random
import shutil
import subprocess
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.events import Key, Paste
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, OptionList, Static

from .capabilities import AttachmentState, CapabilityContext, SearchState
from .chat import CapabilityReport, OllamaChat
from .commands import parse_inline_directives
from .config import load_config
from .exceptions import (
    OllamaChatError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaStreamingError,
    OllamaToolError,
)
from .logging_utils import configure_logging
from .persistence import ConversationPersistence
from .screens import (
    ConversationPickerScreen,
    ImageAttachScreen,
    InfoScreen,
    SimplePickerScreen,
    TextPromptScreen,
)
from .state import ConnectionState, ConversationState, StateManager
from .stream_handler import StreamHandler
from .task_manager import TaskManager
from .tools import ToolRegistry, build_default_registry
from .widgets.conversation import ConversationView
from .widgets.input_box import InputBox
from .widgets.message import MessageBubble
from .widgets.activity_bar import ActivityBar
from .widgets.status_bar import StatusBar

LOGGER = logging.getLogger(__name__)

# Image file extensions accepted for vision attachments.
# Single source of truth — referenced by validation, dialog filter, and paste handler.
_IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"}
)

_STREAM_ERROR_MESSAGES: dict[type, tuple[str, str]] = {
    OllamaToolError: ("Tool error: {exc}", "Tool execution error"),
    OllamaConnectionError: ("Connection error: {exc}", "Connection error"),
    OllamaModelNotFoundError: (
        "Model not found. Verify the configured ollama.model value.",
        "Model not found",
    ),
    OllamaStreamingError: ("Streaming error: {exc}", "Streaming error"),
    OllamaChatError: (
        "Chat error. Please review settings and try again.",
        "Chat error",
    ),
}

_SlashCommand = Callable[[str], Awaitable[None]]


async def _open_native_file_dialog(
    title: str = "Open File",
    file_filter: list[tuple[str, list[str]]] | None = None,
) -> str | None:
    """Open a native Linux file picker, trying multiple backends.

    Tries xdg-desktop-portal (via gdbus), then zenity, then kdialog.
    Returns the selected file path or None if cancelled/unavailable.
    """

    # --- Portal via gdbus (Wayland/Hyprland-friendly) ---
    gdbus_bin = shutil.which("gdbus")
    if gdbus_bin is not None:
        try:
            handle_token = f"ollamaterm_{os.getpid()}"
            proc = await asyncio.create_subprocess_exec(
                gdbus_bin,
                "call",
                "--session",
                "--dest=org.freedesktop.portal.Desktop",
                "--object-path=/org/freedesktop/portal/desktop",
                "--method=org.freedesktop.portal.FileChooser.OpenFile",
                "",
                title,
                f"{{'handle_token': <'{handle_token}'>}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
            if proc.returncode == 0:
                output = stdout.decode().strip()
                if "file://" in output:
                    import urllib.parse

                    for token in output.split():
                        cleaned = token.strip("',()><[]")
                        if cleaned.startswith("file://"):
                            return urllib.parse.unquote(cleaned[len("file://") :])
        except (asyncio.TimeoutError, OSError):
            pass

    # --- zenity ---
    zenity_bin = shutil.which("zenity")
    if zenity_bin is not None:
        cmd: list[str] = [zenity_bin, "--file-selection", f"--title={title}"]
        if file_filter:
            for name, patterns in file_filter:
                cmd.append(f"--file-filter={name} | {' '.join(patterns)}")
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode == 0:
                path = stdout.decode().strip()
                if path:
                    return path
        except (asyncio.TimeoutError, OSError):
            pass

    # --- kdialog ---
    kdialog_bin = shutil.which("kdialog")
    if kdialog_bin is not None:
        cmd = [kdialog_bin, "--getopenfilename", ".", title]
        if file_filter:
            filter_str = " ".join(p for _, patterns in file_filter for p in patterns)
            cmd = [kdialog_bin, "--getopenfilename", ".", filter_str]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode == 0:
                path = stdout.decode().strip()
                if path:
                    return path
        except (asyncio.TimeoutError, OSError):
            pass

    return None


def _is_regular_file(path: Path) -> bool:
    try:
        return path.is_file() and not path.is_symlink()
    except OSError:
        return False


def _is_within_home(path: Path) -> bool:
    try:
        home = Path.home().resolve(strict=False)
        resolved = path.resolve(strict=False)
        resolved.relative_to(home)
        return True
    except Exception:
        return False


def _validate_attachment(
    raw_path: str,
    *,
    kind: str,
    max_bytes: int,
    allowed_extensions: set[str] | None = None,
    home_only: bool = False,
) -> tuple[bool, str, Path | None]:
    expanded = Path(os.path.expanduser(raw_path))
    if not _is_regular_file(expanded):
        return False, f"{kind.capitalize()} not found: {expanded}", None
    if home_only and not _is_within_home(expanded):
        return False, f"{kind.capitalize()} must be inside your home directory.", None
    if allowed_extensions is not None:
        ext = expanded.suffix.lower()
        if ext not in allowed_extensions:
            return False, f"Unsupported {kind} type: {ext}", None
    try:
        size = expanded.stat().st_size
    except OSError:
        return False, f"Unable to read {kind} size.", None
    if size > max_bytes:
        return (
            False,
            f"{kind.capitalize()} too large ({size} bytes). Max is {max_bytes} bytes.",
            None,
        )
    return True, str(expanded), expanded


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

    def compose(self) -> ComposeResult:
        with Container(id="model-picker-dialog"):
            yield Static("Select model from config", id="model-picker-title")
            yield OptionList(*self.models, id="model-picker-options")
            yield Static(
                "Enter/click to select  |  Esc to cancel", id="model-picker-help"
            )

    def on_mount(self) -> None:
        options = self.query_one("#model-picker-options", OptionList)
        selected_index = 0
        for index, model_name in enumerate(self.models):
            if OllamaChat._model_name_matches(self.active_model, model_name):
                selected_index = index
                break
        options.highlighted = selected_index

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_index = getattr(event, "option_index", None)
        if option_index is None:
            option_index = getattr(event, "index", -1)
        try:
            selected_index = int(option_index or -1)
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

    #attach_button {
        margin-left: 1;
        min-width: 10;
    }

    #file_button {
        margin-left: 1;
        min-width: 10;
    }

    #send_button {
        margin-left: 1;
        min-width: 10;
    }

    #input_row {
        height: auto;
    }

    #status_bar {
        height: auto;
        padding: 0 1;
        border-top: solid $panel;
        background: $surface;
    }

    #activity_bar {
        height: auto;
        min-height: 2;
        padding: 0 1 0 1;
        border-top: dashed $panel;
        background: $surface;
    }

    #slash_menu {
        max-height: 8;
        width: 60;
        margin-top: 1;
    }

    #slash_menu.hidden {
        display: none;
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
        "toggle_conversation_picker": "Conversations",
        "toggle_prompt_preset_picker": "Prompt",
        "interrupt_stream": "Interrupt",
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
        LOGGER.info(
            "app.python",
            extra={
                "event": "app.python",
                "executable": sys.executable,
                "version": sys.version.split()[0],
            },
        )

        # Enforce host policy defensively (config already validates, but keep
        # the boundary explicit here).
        security_cfg = self.config.get("security", {})
        host_value = str(self.config["ollama"]["host"])
        parsed = urlparse(host_value)
        hostname = (parsed.hostname or "").strip().lower()
        scheme = parsed.scheme.lower()
        allowed_hosts = {
            str(item).strip().lower()
            for item in security_cfg.get("allowed_hosts", [])
            if str(item).strip()
        }
        if scheme not in {"http", "https"} or not hostname:
            raise OllamaConnectionError(
                "ollama.host must use http(s) and include a hostname."
            )
        if (
            not bool(security_cfg.get("allow_remote_hosts", False))
            and hostname not in allowed_hosts
        ):
            raise OllamaConnectionError(
                "ollama.host is not allowed by security policy. "
                "Set security.allow_remote_hosts=true or add the hostname to security.allowed_hosts."
            )

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
        self._prompt_presets: dict[str, str] = dict(
            ollama_cfg.get("prompt_presets") or {}
        )
        self._active_prompt_preset: str = str(
            ollama_cfg.get("active_prompt_preset") or ""
        ).strip()
        self.state = StateManager()
        self._task_manager = TaskManager()
        self._connection_state = ConnectionState.UNKNOWN
        self._search = SearchState()
        self._attachments = AttachmentState()
        self._image_dialog_active = False
        self._last_prompt: str = ""

        # Cached widget references — populated in on_mount() after compose().
        # Using cached refs avoids repeated O(widget-tree) query_one() calls in
        # hot paths (every send, every connection-monitor tick, every keystroke).
        self._w_input: Input | None = None
        self._w_send: Button | None = None
        self._w_file: Button | None = None
        self._w_activity: ActivityBar | None = None
        self._w_status: StatusBar | None = None
        self._w_conversation: ConversationView | None = None

        self._slash_commands: list[tuple[str, str]] = [
            ("/image <path>", "Attach image from filesystem"),
            ("/file <path>", "Attach file as context"),
            ("/new", "Start a new conversation"),
            ("/clear", "Clear the input"),
            ("/help", "Show help"),
            ("/model <name>", "Switch active model"),
            ("/preset <name>", "Switch prompt preset"),
            ("/conversations", "Open conversation picker"),
        ]

        # Capabilities configuration (user preferences from config — the ceiling).
        self.capabilities = CapabilityContext.from_config(self.config)

        # Per-model runtime capabilities fetched from Ollama's /api/show.
        # known=False means capabilities metadata is unavailable; effective caps fall
        # back to config flags unchanged.
        self._model_caps: CapabilityReport = CapabilityReport(
            caps=frozenset(), known=False
        )

        # Effective capabilities start permissive (all auto-detected fields = True)
        # and are refined once ensure_model_ready() returns /api/show data.
        self._effective_caps: CapabilityContext = CapabilityContext(
            think=True,
            tools_enabled=True,
            vision_enabled=True,
            show_thinking=self.capabilities.show_thinking,
            web_search_enabled=self.capabilities.web_search_enabled,
            web_search_api_key=self.capabilities.web_search_api_key,
            max_tool_iterations=self.capabilities.max_tool_iterations,
        )

        # Build the tool registry unconditionally — whether tools are actually
        # used is gated at call time by _effective_caps.tools_enabled.  This
        # ensures the registry is ready when the first tool-capable model loads.
        try:
            self._tool_registry: ToolRegistry | None = build_default_registry(
                web_search_enabled=self.capabilities.web_search_enabled,
                web_search_api_key=self.capabilities.web_search_api_key,
            )
        except OllamaToolError as exc:
            LOGGER.warning(
                "app.tools.disabled",
                extra={
                    "event": "app.tools.disabled",
                    "reason": str(exc),
                },
            )
            self._tool_registry = None

        persistence_cfg = self.config["persistence"]
        self.persistence = ConversationPersistence(
            enabled=bool(persistence_cfg["enabled"]),
            directory=str(persistence_cfg["directory"]),
            metadata_path=str(persistence_cfg["metadata_path"]),
        )
        self._last_prompt_path = self.persistence.directory / "last_prompt.txt"
        self._load_last_prompt()
        self._binding_specs = self._binding_specs_from_config(self.config)
        self._apply_terminal_window_identity()
        super().__init__()

    def _load_last_prompt(self) -> None:
        try:
            if self._last_prompt_path.exists():
                self._last_prompt = self._last_prompt_path.read_text(
                    encoding="utf-8"
                ).strip()
        except Exception:
            self._last_prompt = ""

    async def _save_last_prompt(self, prompt: str) -> None:
        """Persist the last prompt asynchronously to avoid blocking the event loop."""
        try:
            self._last_prompt_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(
                self._last_prompt_path.write_text, prompt, encoding="utf-8"
            )
        except Exception:
            LOGGER.warning(
                "app.last_prompt.save_failed",
                extra={"event": "app.last_prompt.save_failed"},
            )

    @classmethod
    def _binding_specs_from_config(
        cls, config: dict[str, dict[str, Any]]
    ) -> list[Binding]:
        keybinds = config.get("keybinds", {})
        bindings: list[Binding] = []
        # Iterate over the canonical action descriptions; KEY_TO_ACTION was a
        # redundant identity map (every key mapped to itself) and has been removed.
        for action_name in cls.DEFAULT_ACTION_DESCRIPTIONS:
            binding_key = keybinds.get(action_name)
            if isinstance(binding_key, str) and binding_key.strip():
                bindings.append(
                    Binding(
                        key=binding_key.strip(),
                        action=action_name,
                        description=cls.DEFAULT_ACTION_DESCRIPTIONS[action_name],
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
            yield ActivityBar(
                shortcut_hints="ctrl+p commands",
                id="activity_bar",
            )
        yield Footer()

    async def action_command_palette(self) -> None:
        """Open a lightweight command palette (help) listing available actions."""
        lines = ["Commands:", ""]
        for cmd, desc in self._slash_commands:
            lines.append(f"{cmd} - {desc}")
        lines.append("")
        lines.append("Keybind actions:")
        for binding in self._binding_specs:
            lines.append(
                f"{binding.key.upper()} - {binding.description} ({binding.action})"
            )
        await self.push_screen(InfoScreen("\n".join(lines)))

    async def action_toggle_conversation_picker(self) -> None:
        """Open conversation quick switcher."""
        if await self.state.get_state() != ConversationState.IDLE:
            self.sub_title = "Conversation picker is available only when idle."
            return
        if not self.persistence.enabled:
            self.sub_title = "Persistence is disabled in configuration."
            return
        items = self.persistence.list_conversations()
        if not items:
            self.sub_title = "No saved conversations found."
            return
        selected = await self.push_screen_wait(ConversationPickerScreen(items))
        if not selected:
            return
        await self._load_conversation_from_path(Path(selected))

    async def action_toggle_prompt_preset_picker(self) -> None:
        """Open prompt preset picker and apply selection."""
        if await self.state.get_state() != ConversationState.IDLE:
            self.sub_title = "Prompt picker is available only when idle."
            return
        if not self._prompt_presets:
            self.sub_title = "No prompt presets configured."
            return
        options = sorted(self._prompt_presets.keys())
        selected = await self.push_screen_wait(
            SimplePickerScreen("Prompt Presets", options)
        )
        if not selected:
            return
        self._active_prompt_preset = selected
        preset_value = self._prompt_presets.get(selected, "").strip()
        if preset_value:
            self.chat.system_prompt = preset_value
            self.chat.message_store = self.chat.message_store.__class__(
                system_prompt=preset_value,
                max_history_messages=self.chat.message_store.max_history_messages,
                max_context_tokens=self.chat.message_store.max_context_tokens,
            )
        self.sub_title = f"Prompt preset set: {selected}"

    async def _load_conversation_payload(self, payload: dict[str, Any]) -> None:
        """Apply a loaded conversation payload to the chat and re-render the UI."""
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

    async def _load_conversation_from_path(self, path: Path) -> None:
        try:
            payload = self.persistence.load_conversation(path)
        except Exception:
            self.sub_title = "Failed to load conversation."
            return
        await self._load_conversation_payload(payload)

    async def _prompt_conversation_name(self) -> str:
        try:
            value = await self.push_screen_wait(
                TextPromptScreen("Conversation name", placeholder="(optional)")
            )
        except Exception:
            return ""
        if value is None:
            return ""
        return str(value).strip()

    async def on_mount(self) -> None:
        """Apply theme and register runtime keybindings."""
        self.title = self.window_title
        self._set_idle_sub_title(f"Model: {self.chat.model}")
        LOGGER.info(
            "app.state.transition",
            extra={"event": "app.state.transition", "to_state": "IDLE"},
        )
        self._apply_theme()
        for binding in self._binding_specs:
            self.bind(
                binding.key,
                binding.action,
                description=binding.description,
                show=binding.show,
                key_display=binding.key_display,
            )

        # Populate widget cache once; avoids repeated DOM traversal on hot paths.
        self._w_input = self.query_one("#message_input", Input)
        self._w_send = self.query_one("#send_button", Button)
        self._w_file = self.query_one("#file_button", Button)
        self._w_activity = self.query_one("#activity_bar", ActivityBar)
        self._w_status = self.query_one("#status_bar", StatusBar)
        self._w_conversation = self.query_one(ConversationView)

        attach_button = self.query_one("#attach_button", Button)
        self._w_input.disabled = True
        self._w_send.disabled = True
        attach_button.disabled = not self.capabilities.vision_enabled
        self._w_file.disabled = False
        self._update_status_bar()

        self._slash_registry = self._build_slash_registry()

        palette_key = self._command_palette_key_display().lower()
        self._w_activity.set_shortcut_hints(f"{palette_key} commands")

        # The connection monitor starts only after _prepare_startup_model() completes
        # so that the startup check sets _connection_state first, preventing the
        # monitor from immediately overwriting the startup result with a concurrent
        # check_connection() call.
        self._task_manager.add(
            asyncio.create_task(self._prepare_startup_model()), name="startup_model"
        )

    async def _prepare_startup_model(self) -> None:
        """Warm up model in background so UI stays responsive on launch."""
        try:
            await self._ensure_startup_model_ready()
        finally:
            if self._w_input:
                self._w_input.disabled = False
                self._w_input.focus()
            if self._w_send:
                self._w_send.disabled = False
            if self._w_file:
                self._w_file.disabled = False
            self._update_status_bar()
            # Start the connection monitor only after startup determines the initial
            # connection state, so the two tasks cannot race to write _connection_state.
            self._task_manager.add(
                asyncio.create_task(self._connection_monitor_loop()),
                name="connection_monitor",
            )

    async def _ensure_startup_model_ready(self) -> None:
        """Ensure configured model is available before interactive usage."""
        pull_on_start = bool(self.config["ollama"].get("pull_model_on_start", True))
        self.sub_title = f"Preparing model: {self.chat.model}"
        try:
            await self.chat.ensure_model_ready(pull_if_missing=pull_on_start)
            self._connection_state = ConnectionState.ONLINE
            # Detect what this model actually supports and update effective caps.
            self._model_caps = await self.chat.show_model_capabilities()
            self._update_effective_caps()
            self._set_idle_sub_title(f"Model ready: {self.chat.model}")
        except OllamaConnectionError:
            self._connection_state = ConnectionState.OFFLINE
            self.sub_title = "Cannot reach Ollama. Start ollama serve."
        except OllamaModelNotFoundError:
            self._connection_state = ConnectionState.ONLINE
            self.sub_title = (
                f"Model not available: {self.chat.model}. "
                "Enable pull_model_on_start or run ollama pull manually."
            )
        except OllamaStreamingError:
            self._connection_state = ConnectionState.OFFLINE
            self.sub_title = "Failed while preparing model."
        except OllamaChatError:
            self.sub_title = "Model preparation failed."

    def _update_effective_caps(self) -> None:
        """Recompute _effective_caps purely from Ollama's /api/show response.

        The three model-capability fields (``think``, ``tools_enabled``,
        ``vision_enabled``) are set **solely** by auto-detection — there are no
        longer config flags for them.  User preferences (``show_thinking``,
        ``web_search_*``, ``max_tool_iterations``) are always taken from
        ``self.capabilities`` which is loaded from the ``[capabilities]`` config
        section.

        When capability metadata is unknown (``show()`` unavailable or the
        response has no ``capabilities`` field — old Ollama versions, custom
        models), all three auto-detected fields default to ``True`` (permissive
        fallback) so that nothing is silently disabled.

        When metadata is known, each field is set to ``True`` only when the
        model explicitly reports that capability in its ``capabilities`` array.
        ``web_search`` additionally requires the model to support tools.
        """
        if not self._model_caps.known:
            # Unknown — permissive fallback: assume everything is supported.
            self._effective_caps = CapabilityContext(
                think=True,
                tools_enabled=True,
                vision_enabled=True,
                show_thinking=self.capabilities.show_thinking,
                web_search_enabled=self.capabilities.web_search_enabled,
                web_search_api_key=self.capabilities.web_search_api_key,
                max_tool_iterations=self.capabilities.max_tool_iterations,
            )
            return

        caps = self._model_caps.caps
        tools_supported = "tools" in caps

        self._effective_caps = CapabilityContext(
            # Auto-detected from /api/show.
            think="thinking" in caps,
            tools_enabled=tools_supported,
            # web_search requires tool-calling; disable when model can't do tools.
            vision_enabled="vision" in caps,
            # User / app preferences — always from config.
            show_thinking=self.capabilities.show_thinking,
            web_search_enabled=self.capabilities.web_search_enabled and tools_supported,
            web_search_api_key=self.capabilities.web_search_api_key,
            max_tool_iterations=self.capabilities.max_tool_iterations,
        )

        # Log which capabilities this model does not support.
        for enabled, feature in [
            (self._effective_caps.think, "thinking"),
            (self._effective_caps.tools_enabled, "tools"),
            (self._effective_caps.vision_enabled, "vision"),
        ]:
            if not enabled:
                LOGGER.info(
                    "app.capability.not_supported",
                    extra={
                        "event": "app.capability.not_supported",
                        "feature": feature,
                        "model": self.chat.model,
                    },
                )

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

    @staticmethod
    def _apply_custom_theme(
        bubble: MessageBubble, role: str, ui_cfg: dict[str, Any]
    ) -> None:
        """Apply user-configured colours and border to a message bubble."""
        if role == "user":
            bubble.styles.background = str(ui_cfg["user_message_color"])
        else:
            bubble.styles.background = str(ui_cfg["assistant_message_color"])
        bubble.styles.border = ("round", str(ui_cfg["border_color"]))

    def _style_bubble(self, bubble: MessageBubble, role: str) -> None:
        bubble.styles.align_horizontal = "right" if role == "user" else "left"
        if not self._using_theme_palette():
            self._apply_custom_theme(bubble, role, self.config["ui"])

    def _restyle_rendered_bubbles(self) -> None:
        try:
            conversation = self._w_conversation or self.query_one(ConversationView)
        except Exception:
            return
        for bubble in conversation.children:
            if isinstance(bubble, MessageBubble):
                self._style_bubble(bubble, bubble.role)

    def _using_theme_palette(self) -> bool:
        return bool(getattr(self, "theme", ""))

    def _update_status_bar(self) -> None:
        # Use non_system_count (no list copy) when the real MessageStore is available;
        # fall back to iterating the messages property for test fakes that lack it.
        ms = getattr(self.chat, "message_store", None)
        if ms is not None and hasattr(ms, "non_system_count"):
            message_count = ms.non_system_count
        else:
            message_count = sum(
                1
                for m in getattr(self.chat, "messages", [])
                if m.get("role") != "system"
            )
        status_widget = getattr(self, "_w_status", None) or self.query_one(
            "#status_bar", StatusBar
        )
        status_widget.set_status(
            connection_state=self._connection_state.value,
            model=self.chat.model,
            message_count=message_count,
            estimated_tokens=self.chat.estimated_context_tokens,
            effective_caps=getattr(self, "_effective_caps", None),
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
        self._task_manager.add(
            asyncio.create_task(self._activate_selected_model(selected_model))
        )

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
            self._connection_state = ConnectionState.ONLINE

            # Fetch this model's actual capabilities and recompute effective flags.
            self._model_caps = await self.chat.show_model_capabilities(model_name)
            self._update_effective_caps()

            # Build a subtitle reporting which capabilities this model lacks.
            # Since auto-detection is now the sole authority, we report what
            # /api/show told us rather than comparing against removed config flags.
            unsupported = [
                cap
                for enabled, cap in [
                    (self._effective_caps.think, "thinking"),
                    (self._effective_caps.tools_enabled, "tools"),
                    (self._effective_caps.vision_enabled, "vision"),
                ]
                if not enabled
            ]
            msg = f"Active model: {model_name}"
            if unsupported and self._model_caps.known:
                msg += f"  |  Not supported: {', '.join(unsupported)}"
            self._set_idle_sub_title(msg)
        except OllamaChatError as exc:  # noqa: BLE001
            self.chat.set_model(previous_model)
            LOGGER.warning(
                "app.model.switch.failed",
                extra={
                    "event": "app.model.switch.failed",
                    "error_type": type(exc).__name__,
                    "model": model_name,
                },
            )
            if isinstance(exc, OllamaConnectionError):
                self._connection_state = ConnectionState.OFFLINE
                self.sub_title = "Unable to switch model while offline."
            elif isinstance(exc, OllamaModelNotFoundError):
                self._set_idle_sub_title(
                    f"Configured model unavailable in Ollama: {model_name}"
                )
            elif isinstance(exc, OllamaStreamingError):
                self.sub_title = "Failed while validating selected model."
            else:
                self.sub_title = "Model switch failed."
        finally:
            self._update_status_bar()

    async def _connection_monitor_loop(self) -> None:
        interval = int(self.config["app"]["connection_check_interval_seconds"])
        try:
            while True:
                connected = await self.chat.check_connection()
                new_state = (
                    ConnectionState.ONLINE if connected else ConnectionState.OFFLINE
                )
                if new_state != self._connection_state:
                    self._connection_state = new_state
                    LOGGER.info(
                        "app.connection.state",
                        extra={
                            "event": "app.connection.state",
                            "connection_state": new_state.value,
                        },
                    )
                    if await self.state.get_state() == ConversationState.IDLE:
                        self._set_idle_sub_title(f"Connection: {new_state}")
                self._update_status_bar()
                await asyncio.sleep(interval * random.uniform(0.85, 1.15))
        except asyncio.CancelledError:
            LOGGER.info(
                "app.connection.monitor.stopped",
                extra={"event": "app.connection.monitor.stopped"},
            )
            raise

    async def _add_message(
        self, content: str, role: str, timestamp: str = ""
    ) -> MessageBubble:
        conversation = self._w_conversation or self.query_one(ConversationView)
        bubble = await conversation.add_message(
            content=content,
            role=role,
            timestamp=timestamp,
            show_thinking=self._effective_caps.show_thinking,
        )
        self._style_bubble(bubble, role)
        return bubble

    async def on_status_bar_model_picker_requested(
        self, _message: StatusBar.ModelPickerRequested
    ) -> None:
        """Open configured model picker from StatusBar model segment click."""
        await self._open_configured_model_picker()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle send button clicks."""
        if event.button.id == "send_button":
            await self.send_user_message()

    async def _open_attachment_dialog(self, mode: str) -> None:
        """Open a native file dialog with fallback for the given attachment mode."""
        if mode == "image":
            # Guard against double-launch before setting up other locals.
            if self._image_dialog_active:
                return
            self._image_dialog_active = True
            file_filter: list[tuple[str, list[str]]] | None = [
                ("Images", [f"*{ext}" for ext in sorted(_IMAGE_EXTENSIONS)]),
            ]
            title = "Attach image"
            callback = self._on_image_attach_dismissed
        else:
            file_filter = None
            title = "Attach file"
            callback = self._on_file_attach_dismissed

        try:
            path = await _open_native_file_dialog(title=title, file_filter=file_filter)
            if path is None:
                # Fallback to modal dialog if no native picker available.
                self.push_screen(ImageAttachScreen(), callback=callback)
                return
            callback(path)
        finally:
            if mode == "image":
                self._image_dialog_active = False

    async def on_input_box_attach_requested(
        self, _message: InputBox.AttachRequested
    ) -> None:
        """Open native image picker when attach button is clicked."""
        if not self._effective_caps.vision_enabled:
            self.sub_title = "Vision is not supported by this model."
            return
        await self._open_attachment_dialog("image")

    async def on_input_box_file_attach_requested(
        self, _message: InputBox.FileAttachRequested
    ) -> None:
        """Open native file picker when file button is clicked."""
        await self._open_attachment_dialog("file")

    def _on_image_attach_dismissed(self, path: str | None) -> None:
        self._image_dialog_active = False
        if not path:
            return
        ok, message, resolved = _validate_attachment(
            path,
            kind="image",
            max_bytes=10 * 1024 * 1024,
            allowed_extensions=_IMAGE_EXTENSIONS,
            home_only=False,
        )
        if not ok or resolved is None:
            self.sub_title = message
            return
        self._attachments.add_image(str(resolved))
        self.sub_title = (
            f"Image attached: {resolved.name} ({len(self._attachments.images)} total)"
        )

    def _on_file_attach_dismissed(self, path: str | None) -> None:
        if not path:
            return
        ok, message, resolved = _validate_attachment(
            path,
            kind="file",
            max_bytes=2 * 1024 * 1024,
            allowed_extensions=None,
            home_only=False,
        )
        if not ok or resolved is None:
            self.sub_title = message
            return
        self._attachments.add_file(str(resolved))
        self.sub_title = (
            f"File attached: {resolved.name} ({len(self._attachments.files)} total)"
        )

    @staticmethod
    def _is_image_path(path: str) -> bool:
        ext = os.path.splitext(path)[1].lower()
        return ext in _IMAGE_EXTENSIONS

    @staticmethod
    def _extract_paths_from_paste(text: str) -> list[str]:
        """Extract file paths from pasted text (common drag/drop behavior)."""
        candidates: list[str] = []
        for token in text.strip().split():
            cleaned = token.strip().strip("'\"")
            if cleaned.startswith("file://"):
                cleaned = cleaned[len("file://") :]
            if cleaned:
                candidates.append(cleaned)
        return candidates

    def on_paste(self, event: Paste) -> None:
        """Handle drag/drop style paste events to attach files/images."""
        if not event.text:
            return
        paths = self._extract_paths_from_paste(event.text)
        if not paths:
            return
        added_images = 0
        added_files = 0
        for path in paths:
            expanded = os.path.expanduser(path)
            if not os.path.isfile(expanded):
                continue
            if self._is_image_path(expanded) and self._effective_caps.vision_enabled:
                self._attachments.add_image(expanded)
                added_images += 1
            else:
                self._attachments.add_file(expanded)
                added_files += 1
        if added_images or added_files:
            self.sub_title = (
                f"Attached {added_images} image(s), {added_files} file(s) via drop"
            )
            event.stop()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submit events."""
        if event.input.id == "message_input":
            await self.send_user_message()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Toggle slash menu visibility based on input prefix."""
        if event.input.id != "message_input":
            return
        value = event.value
        if value.startswith("/"):
            self._show_slash_menu(prefix=value)
        else:
            self._hide_slash_menu()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "slash_menu":
            return
        option_text = str(event.option.prompt)
        command = option_text.split(" ", 1)[0]
        input_widget = self._w_input or self.query_one("#message_input", Input)
        input_widget.value = f"{command} "
        input_widget.cursor_position = len(input_widget.value)
        self._hide_slash_menu()
        input_widget.focus()
        event.stop()

    def on_key(self, event: Key) -> None:
        """Handle Up-arrow recall and slash quick-open."""
        if event.key == "up":
            try:
                input_widget = self._w_input or self.query_one("#message_input", Input)
            except Exception:
                return
            if input_widget.has_focus and not input_widget.value and self._last_prompt:
                input_widget.value = self._last_prompt
                input_widget.cursor_position = len(input_widget.value)
                self.sub_title = "Restored last prompt."
                event.stop()

    def _show_slash_menu(self, prefix: str) -> None:
        try:
            menu = self.query_one(
                "#slash_menu", OptionList
            )  # not cached (InputBox child)
        except Exception:
            return
        menu.clear_options()
        normalized_prefix = prefix.lower()
        for command, description in self._slash_commands:
            if command.lower().startswith(normalized_prefix):
                menu.add_option(f"{command} — {description}")
        if menu.options:
            menu.remove_class("hidden")
        else:
            menu.add_class("hidden")

    def _hide_slash_menu(self) -> None:
        try:
            menu = self.query_one("#slash_menu", OptionList)
        except Exception:
            return
        menu.add_class("hidden")
        menu.clear_options()

    async def action_send_message(self) -> None:
        """Action invoked by keybinding for sending a message."""
        await self.send_user_message()

    async def _transition_state(self, new_state: ConversationState) -> None:
        """Transition to new_state atomically (single lock acquisition)."""
        await self.state.transition_to(new_state)
        LOGGER.info(
            "app.state.transition",
            extra={
                "event": "app.state.transition",
                "to_state": new_state.value,
            },
        )

    async def _animate_response_placeholder(
        self, assistant_bubble: MessageBubble
    ) -> None:
        frame_index = 0
        while True:
            assistant_bubble.set_content(
                self.RESPONSE_PLACEHOLDER_FRAMES[
                    frame_index % len(self.RESPONSE_PLACEHOLDER_FRAMES)
                ]
            )
            frame_index += 1
            await asyncio.sleep(0.35)

    async def _stop_response_indicator_task(self) -> None:
        await self._task_manager.cancel("response_indicator")

    async def _stream_assistant_response(
        self,
        user_text: str,
        assistant_bubble: MessageBubble,
        images: list[str | bytes] | None = None,
    ) -> None:
        chunk_size = max(1, int(self.config["ui"]["stream_chunk_size"]))
        self.sub_title = "Waiting for response..."
        self._task_manager.add(
            asyncio.create_task(self._animate_response_placeholder(assistant_bubble)),
            name="response_indicator",
        )

        def _scroll() -> None:
            conv = self._w_conversation or self.query_one(ConversationView)
            conv.scroll_end(animate=False)

        handler = StreamHandler(
            bubble=assistant_bubble,
            scroll_callback=_scroll,
            chunk_size=chunk_size,
        )

        try:
            async for chunk in self.chat.send_message(
                user_text,
                images=images or None,
                # Pass tool_registry only when the *effective* caps say tools are on.
                # _effective_caps already intersects config + what Ollama reports for
                # this model, so models that don't support tools get tool_registry=None.
                tool_registry=(
                    self._tool_registry if self._effective_caps.tools_enabled else None
                ),
                think=self._effective_caps.think,
                max_tool_iterations=self._effective_caps.max_tool_iterations,
            ):
                if chunk.kind == "thinking":
                    await handler.handle_thinking(
                        chunk.text, self._stop_response_indicator_task
                    )
                elif chunk.kind == "content":
                    await handler.handle_content(
                        chunk.text, self._stop_response_indicator_task
                    )
                elif chunk.kind == "tool_call":
                    await handler.handle_tool_call(
                        chunk.tool_name,
                        chunk.tool_args,
                        self._stop_response_indicator_task,
                    )
                elif chunk.kind == "tool_result":
                    handler.handle_tool_result(chunk.tool_name, chunk.tool_result)

                if handler.status:
                    self.sub_title = handler.status

            await handler.finalize()
            self._update_status_bar()
        finally:
            await self._stop_response_indicator_task()

    async def _handle_stream_error(
        self,
        bubble: MessageBubble | None,
        message: str,
        subtitle: str,
    ) -> None:
        """Transition to ERROR state and display the error in the assistant bubble."""
        await self._transition_state(ConversationState.ERROR)
        if bubble is None:
            await self._add_message(
                content=message, role="assistant", timestamp=self._timestamp()
            )
        else:
            bubble.set_content(message)
        self.sub_title = subtitle

    async def action_interrupt_stream(self) -> None:
        """Cancel an in-flight assistant response when streaming."""
        if await self.state.get_state() != ConversationState.STREAMING:
            self.sub_title = "No response to interrupt."
            return
        await self._transition_state(ConversationState.CANCELLING)
        self.sub_title = "Interrupting response..."
        await self._task_manager.cancel("active_stream")
        self._set_idle_sub_title(f"Model: {self.chat.model}")
        self._update_status_bar()

    async def action_new_conversation(self) -> None:
        """Clear UI and in-memory conversation history."""
        active_stream = self._task_manager.get("active_stream")
        if (
            await self.state.get_state() == ConversationState.STREAMING
            and active_stream is not None
        ):
            await self._transition_state(ConversationState.CANCELLING)
            LOGGER.info(
                "chat.request.cancelling", extra={"event": "chat.request.cancelling"}
            )
            await self._task_manager.cancel("active_stream")
            LOGGER.info(
                "chat.request.cancelled", extra={"event": "chat.request.cancelled"}
            )

        self.chat.clear_history()
        self._attachments.clear()
        await self._clear_conversation_view()
        self._search.reset()
        await self._transition_state(ConversationState.IDLE)
        self._set_idle_sub_title(f"Model: {self.chat.model}")
        self._update_status_bar()

    async def _clear_conversation_view(self) -> None:
        """Remove all rendered conversation bubbles."""
        conversation = self._w_conversation or self.query_one(ConversationView)
        if hasattr(conversation, "remove_children"):
            result = conversation.remove_children()
            if inspect.isawaitable(result):
                await result
        else:
            for child in list(conversation.children):
                result = child.remove()
                if inspect.isawaitable(result):
                    await result

    async def _render_messages_from_history(
        self, messages: list[dict[str, Any]]
    ) -> None:
        """Render persisted non-system messages into the conversation view."""
        for message in messages:
            role = str(message.get("role", "")).strip().lower()
            if role == "system":
                continue
            content = str(message.get("content", ""))
            bubble = await self._add_message(
                content=content, role=role, timestamp=self._timestamp()
            )
            await bubble.finalize_content()

    def _auto_save_on_exit(self) -> None:
        """Persist conversation on exit when auto_save is enabled."""
        persistence_cfg = self.config.get("persistence", {})
        if not bool(persistence_cfg.get("enabled", False)):
            return
        if not bool(persistence_cfg.get("auto_save", True)):
            return
        non_system = [m for m in self.chat.messages if m.get("role") != "system"]
        if not non_system:
            return
        try:
            self.persistence.save_conversation(self.chat.messages, self.chat.model)
            LOGGER.info("app.auto_save", extra={"event": "app.auto_save"})
        except Exception:  # noqa: BLE001
            LOGGER.warning(
                "app.auto_save.failed", extra={"event": "app.auto_save.failed"}
            )

    async def on_unmount(self) -> None:
        """Cancel and await all background tasks during shutdown."""
        self._auto_save_on_exit()
        await self._transition_state(ConversationState.CANCELLING)
        await self._task_manager.cancel_all()
        await self._transition_state(ConversationState.IDLE)

    async def action_quit(self) -> None:
        """Exit the app."""
        self.exit()

    def action_scroll_up(self) -> None:
        """Scroll conversation up."""
        conversation = self._w_conversation or self.query_one(ConversationView)
        conversation.scroll_relative(y=-10, animate=False)

    def action_scroll_down(self) -> None:
        """Scroll conversation down."""
        conversation = self._w_conversation or self.query_one(ConversationView)
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
            name = await self._prompt_conversation_name()
            path = self.persistence.save_conversation(
                self.chat.messages, self.chat.model, name=name
            )
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
        await self._load_conversation_payload(payload)

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
        conversation = self._w_conversation or self.query_one(ConversationView)
        non_system_index = -1
        for index, message in enumerate(self.chat.messages):
            if message.get("role") == "system":
                continue
            non_system_index += 1
            if index == message_index:
                break
        bubbles = [
            child for child in conversation.children if isinstance(child, MessageBubble)
        ]
        if 0 <= non_system_index < len(bubbles):
            target = bubbles[non_system_index]
            if hasattr(target, "scroll_visible"):
                target.scroll_visible(animate=False)
            conversation.scroll_end(animate=False)

    async def action_search_messages(self) -> None:
        """Search messages using input box text and cycle through results."""
        input_widget = self._w_input or self.query_one("#message_input", Input)
        query = input_widget.value.strip().lower()

        if not query and self._search.has_results():
            current = self._search.advance()
            self._jump_to_search_result(current)
            self.sub_title = f"Search {self._search.position + 1}/{len(self._search.results)}: {self._search.query}"
            return
        if not query:
            self.sub_title = "Type search text in the input box, then press search."
            return

        self._search.query = query
        self._search.results = [
            index
            for index, message in enumerate(self.chat.messages)
            if message.get("role") != "system"
            and query in str(message.get("content", "")).lower()
        ]
        self._search.position = 0
        if not self._search.has_results():
            self.sub_title = f"No matches for '{query}'."
            return
        self._jump_to_search_result(self._search.results[self._search.position])
        self.sub_title = (
            f"Search {self._search.position + 1}/{len(self._search.results)}: {query}"
        )

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
                input_widget = self._w_input or self.query_one("#message_input", Input)
                input_widget.value = content
                self.sub_title = "Clipboard unavailable. Message placed in input box."
            return
        self.sub_title = "No assistant message available to copy."

    async def send_user_message(self) -> None:
        """Collect input text and stream the assistant response into the UI."""
        input_widget = self._w_input or self.query_one("#message_input", Input)
        send_button = self._w_send or self.query_one("#send_button", Button)
        file_button = self._w_file or self.query_one("#file_button", Button)
        raw_text = input_widget.value.strip()

        # Intercept slash commands before sending to LLM.
        if raw_text.startswith("/"):
            if await self._dispatch_slash_command(raw_text):
                return

        directives = parse_inline_directives(
            raw_text, vision_enabled=self._effective_caps.vision_enabled
        )
        user_text = directives.cleaned_text
        inline_images = directives.image_paths
        inline_files = directives.file_paths

        # Combine inline images and images attached via the attach button.
        all_images: list[str] = inline_images + self._attachments.images
        all_files: list[str] = inline_files + list(self._attachments.files)

        if not user_text and not all_images and not all_files:
            self.sub_title = "Cannot send an empty message."
            return

        # Validate image paths before sending.
        valid_images: list[str | bytes] = []
        valid_files: list[str] = []
        for img_path in all_images:
            ok, message, resolved = _validate_attachment(
                img_path,
                kind="image",
                max_bytes=10 * 1024 * 1024,
                allowed_extensions=_IMAGE_EXTENSIONS,
                home_only=False,
            )
            if ok and resolved is not None:
                valid_images.append(str(resolved))
            else:
                LOGGER.warning(
                    "app.vision.missing_image",
                    extra={"event": "app.vision.missing_image", "path": img_path},
                )
                self.sub_title = message

        for file_path in all_files:
            ok, message, resolved = _validate_attachment(
                file_path,
                kind="file",
                max_bytes=2 * 1024 * 1024,
                allowed_extensions=None,
                home_only=False,
            )
            if ok and resolved is not None:
                valid_files.append(str(resolved))
            else:
                LOGGER.warning(
                    "app.file.missing",
                    extra={"event": "app.file.missing", "path": file_path},
                )
                self.sub_title = message

        # Atomic CAS: only proceed when IDLE → STREAMING succeeds.
        # This replaces a separate can_send_message() check, eliminating
        # the TOCTOU gap between the two lock acquisitions.
        assistant_bubble: MessageBubble | None = None
        transitioned = await self.state.transition_if(
            ConversationState.IDLE, ConversationState.STREAMING
        )
        if not transitioned:
            self.sub_title = "Busy. Wait for current request to finish."
            return
        LOGGER.info(
            "app.state.transition",
            extra={
                "event": "app.state.transition",
                "from_state": "IDLE",
                "to_state": "STREAMING",
            },
        )
        input_widget.disabled = True
        send_button.disabled = True
        file_button.disabled = True
        try:
            activity = self._w_activity or self.query_one("#activity_bar", ActivityBar)
            activity.start_activity()
        except Exception:
            pass
        # Clear pending images and files now that we've consumed them.
        self._attachments.clear()
        try:
            display_text = (
                raw_text
                if raw_text
                else f"[{len(valid_images)} image(s), {len(valid_files)} file(s)]"
            )
            self.sub_title = "Sending message..."
            await self._add_message(
                content=display_text, role="user", timestamp=self._timestamp()
            )
            input_widget.value = ""
            assistant_bubble = await self._add_message(
                content="", role="assistant", timestamp=self._timestamp()
            )

            # Build file context to append to the user prompt for the API call.
            file_context_parts: list[str] = []
            for path in valid_files:
                snippet = ""
                try:
                    snippet = Path(path).read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    snippet = "<unreadable file>"
                max_chars = 4000
                if len(snippet) > max_chars:
                    snippet = snippet[:max_chars] + "\n... [truncated]"
                file_context_parts.append(
                    f"[File: {os.path.basename(path)}]\n{snippet}"
                )

            final_user_text = user_text
            if file_context_parts:
                file_context = "\n\n".join(file_context_parts)
                final_user_text = (
                    f"{user_text}\n\n{file_context}" if user_text else file_context
                )
            self._last_prompt = final_user_text
            await self._save_last_prompt(final_user_text)
            self._hide_slash_menu()

            stream_task = asyncio.create_task(
                self._stream_assistant_response(
                    final_user_text,
                    assistant_bubble,
                    images=valid_images if valid_images else None,
                )
            )
            self._task_manager.add(stream_task, name="active_stream")
            try:
                await stream_task
            finally:
                self._task_manager.discard("active_stream")
            self._set_idle_sub_title("Ready")
        except asyncio.CancelledError:
            # chat.py already logs "chat.request.cancelled"; no duplicate log here.
            self.sub_title = "Request cancelled."
            return
        except OllamaChatError as exc:  # noqa: BLE001
            msg_tpl, subtitle = _STREAM_ERROR_MESSAGES.get(
                type(exc),
                _STREAM_ERROR_MESSAGES[OllamaChatError],
            )
            await self._handle_stream_error(
                assistant_bubble, msg_tpl.format(exc=exc), subtitle
            )
        finally:
            try:
                activity = self._w_activity or self.query_one(
                    "#activity_bar", ActivityBar
                )
                activity.stop_activity()
            except Exception:
                pass
            input_widget.disabled = False
            send_button.disabled = False
            input_widget.focus()
            if await self.state.get_state() != ConversationState.CANCELLING:
                await self._transition_state(ConversationState.IDLE)
            self._update_status_bar()

    def _build_slash_registry(self) -> dict[str, _SlashCommand]:
        """Build the default mapping of slash command prefixes to async handlers."""

        async def _handle_new(_args: str) -> None:
            await self.action_new_conversation()

        async def _handle_clear(_args: str) -> None:
            self.sub_title = "Input cleared."

        async def _handle_help(_args: str) -> None:
            await self.action_command_palette()

        async def _handle_model(args: str) -> None:
            if args.strip():
                model_name = args.strip()
                self._task_manager.add(
                    asyncio.create_task(self._activate_selected_model(model_name))
                )
            else:
                await self._open_configured_model_picker()

        async def _handle_preset(args: str) -> None:
            name = args.strip()
            if not name:
                await self.action_toggle_prompt_preset_picker()
                return
            if name not in self._prompt_presets:
                self.sub_title = f"Unknown preset: {name}"
                return
            self._active_prompt_preset = name
            preset_value = self._prompt_presets.get(name, "").strip()
            if preset_value:
                self.chat.system_prompt = preset_value
            self.sub_title = f"Prompt preset set: {name}"

        async def _handle_conversations(_args: str) -> None:
            await self.action_toggle_conversation_picker()

        return {
            "/new": _handle_new,
            "/clear": _handle_clear,
            "/help": _handle_help,
            "/model": _handle_model,
            "/preset": _handle_preset,
            "/conversations": _handle_conversations,
        }

    def register_slash_command(self, prefix: str, handler: _SlashCommand) -> None:
        """Register a custom slash command handler.

        ``prefix`` should be the command word including the leading slash
        (e.g. ``"/ping"``).  ``handler`` receives the remainder of the input
        after the prefix (may be empty) and must be an async callable.
        """
        self._slash_registry[prefix.lower()] = handler

    async def _dispatch_slash_command(self, raw_text: str) -> bool:
        """Intercept and execute slash commands. Returns True if handled."""
        input_widget = self._w_input or self.query_one("#message_input", Input)
        parts = raw_text.split(maxsplit=1)
        prefix = parts[0].lower()
        args = parts[1] if len(parts) == 2 else ""

        handler = self._slash_registry.get(prefix)
        if handler is None:
            return False

        input_widget.value = ""
        self._hide_slash_menu()
        await handler(args)
        return True
