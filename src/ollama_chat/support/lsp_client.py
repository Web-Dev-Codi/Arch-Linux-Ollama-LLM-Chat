from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class _State:
    touched: set[str] = field(default_factory=set)
    diagnostics: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


_state = _State()


def touch_file(path: str | Path, *, notify: bool) -> None:  # noqa: ARG001 - notify kept for API compatibility
    p = str(Path(path).resolve())
    _state.touched.add(p)
    # In a full implementation, this would send didOpen/didChange/didSave notifications
    # to a running LSP server and refresh diagnostics. Here we keep a simple stub.


def get_diagnostics() -> dict[str, list[dict[str, Any]]]:
    # Return a copy to avoid external mutation
    return {k: list(v) for k, v in _state.diagnostics.items()}


def set_diagnostics(path: str | Path, messages: list[dict[str, Any]]) -> None:
    p = str(Path(path).resolve())
    _state.diagnostics[p] = list(messages)


def has_clients_for(path: str | Path) -> bool:
    # Stubbed: no language servers are wired by default in this standalone package.
    return False
