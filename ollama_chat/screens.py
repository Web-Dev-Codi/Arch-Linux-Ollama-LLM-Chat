"""Reusable modal screens for pickers and info dialogs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, Static


class InfoScreen(ModalScreen[None]):
    """Modal that shows a block of text and closes on Escape/OK."""

    CSS = """
    InfoScreen {
        align: center middle;
    }

    #info-dialog {
        width: 80;
        max-width: 120;
        max-height: 28;
        padding: 1 2;
        border: round $panel;
        background: $surface;
    }

    #info-body {
        height: auto;
    }

    #info-actions {
        dock: bottom;
        height: 3;
        align: right middle;
    }
    """

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def compose(self) -> ComposeResult:
        with Container(id="info-dialog"):
            yield Static(self._text, id="info-body")
            with Container(id="info-actions"):
                yield Button("OK", id="info-ok", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "info-ok":
            event.stop()
            self.dismiss(None)

    def on_key(self, event: Any) -> None:  # noqa: ANN401
        key = str(getattr(event, "key", "")).lower()
        if key in {"escape", "enter"}:
            self.dismiss(None)


class SimplePickerScreen(ModalScreen[str | None]):
    """Modal picker for selecting from a list of strings."""

    CSS = """
    SimplePickerScreen {
        align: center middle;
    }

    #picker-dialog {
        width: 60;
        max-height: 24;
        padding: 1 2;
        border: round $panel;
        background: $surface;
    }

    #picker-title {
        padding-bottom: 1;
        text-style: bold;
    }

    #picker-help {
        padding-top: 1;
    }
    """

    def __init__(self, title: str, options: list[str]) -> None:
        super().__init__()
        self._title = title
        self._options = options

    def compose(self) -> ComposeResult:
        with Container(id="picker-dialog"):
            yield Static(self._title, id="picker-title")
            yield OptionList(*self._options, id="picker-options")
            yield Static("Enter/click to select | Esc to cancel", id="picker-help")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = getattr(event, "option_index", None)
        if idx is None:
            idx = getattr(event, "index", -1)
        try:
            selected = int(idx or -1)
        except (TypeError, ValueError):
            selected = -1
        if 0 <= selected < len(self._options):
            self.dismiss(self._options[selected])

    def on_key(self, event: Any) -> None:  # noqa: ANN401
        if str(getattr(event, "key", "")).lower() == "escape":
            self.dismiss(None)


class TextPromptScreen(ModalScreen[str | None]):
    """Modal screen to prompt for a single line of text."""

    CSS = """
    TextPromptScreen {
        align: center middle;
    }

    #text-prompt-dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        border: round $panel;
        background: $surface;
    }

    #text-prompt-title {
        padding-bottom: 1;
        text-style: bold;
    }

    #text-prompt-input {
        width: 100%;
        margin-bottom: 1;
    }
    """

    def __init__(self, title: str, placeholder: str = "") -> None:
        super().__init__()
        self._title = title
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Container(id="text-prompt-dialog"):
            yield Static(self._title, id="text-prompt-title")
            yield Input(
                placeholder=self._placeholder,
                id="text-prompt-input",
            )
            yield Static("Enter to confirm | Esc to cancel", id="picker-help")

    def on_mount(self) -> None:
        self.query_one("#text-prompt-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "text-prompt-input":
            return
        value = event.value.strip()
        self.dismiss(value if value else "")

    def on_key(self, event: Any) -> None:  # noqa: ANN401
        if str(getattr(event, "key", "")).lower() == "escape":
            self.dismiss(None)


@dataclass(frozen=True)
class ConversationListItem:
    """Item shown in the conversation picker."""

    label: str
    path: str


class ConversationPickerScreen(ModalScreen[str | None]):
    """Picker for saved conversations from persistence index."""

    CSS = """
    ConversationPickerScreen {
        align: center middle;
    }

    #conv-dialog {
        width: 80;
        max-height: 26;
        padding: 1 2;
        border: round $panel;
        background: $surface;
    }

    #conv-title {
        padding-bottom: 1;
        text-style: bold;
    }

    #conv-help {
        padding-top: 1;
    }
    """

    def __init__(self, items: list[dict[str, str]]) -> None:
        super().__init__()
        self._items: list[ConversationListItem] = []
        for row in items:
            path = str(row.get("path", "")).strip()
            created_at = str(row.get("created_at", "")).strip()
            name = str(row.get("name", "")).strip()
            if not path:
                continue
            if name and created_at:
                label = f"{name}  —  {created_at}"
            elif name:
                label = name
            else:
                label = created_at if created_at else path
            self._items.append(ConversationListItem(label=label, path=path))

    def compose(self) -> ComposeResult:
        with Container(id="conv-dialog"):
            yield Static("Conversations", id="conv-title")
            yield OptionList(*(item.label for item in self._items), id="conv-options")
            yield Static("Enter/click to load | Esc to cancel", id="conv-help")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = getattr(event, "option_index", None)
        if idx is None:
            idx = getattr(event, "index", -1)
        try:
            selected = int(idx or -1)
        except (TypeError, ValueError):
            selected = -1
        if 0 <= selected < len(self._items):
            self.dismiss(self._items[selected].path)

    def on_key(self, event: Any) -> None:  # noqa: ANN401
        if str(getattr(event, "key", "")).lower() == "escape":
            self.dismiss(None)
