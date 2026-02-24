# AGENTS.md — Coding Agent Reference

This file documents build commands, style conventions, and architectural patterns
for the **OllamaTerm** project. It is intended as the authoritative guide for
agentic coding assistants working in this repository.

---

## Project Overview

OllamaTerm is a terminal chat TUI (using [Textual](https://github.com/Textualize/textual))
that interfaces with local [Ollama](https://ollama.com) models. The package name
is `ollamaterm`; the importable package is `ollama_chat`.

- **Entry point**: `ollama_chat/__main__.py` → `ollamaterm` CLI
- **Python**: `>=3.11` (uses `tomllib`, `|` union types, `match`)
- **Config file**: `~/.config/ollamaterm/config.toml`

---

## Environment Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'   # editable install with all dev tools
```

Editable installs mean source changes take effect immediately — no reinstall needed.

---

## Build / Lint / Format / Type-check / Test Commands

| Task | Command |
|------|---------|
| Install (dev) | `pip install -e '.[dev]'` |
| Lint | `ruff check .` |
| Format (apply) | `black .` |
| Format (check) | `black --check .` |
| Type-check | `mypy ollama_chat/` |
| Run all tests | `pytest -q` |
| Run single test file | `pytest tests/test_config.py -q` |
| Run single test case | `pytest tests/test_config.py::ConfigTests::test_missing_config_uses_defaults -q` |
| Run single async test | `pytest tests/test_chat.py::StreamTests::test_basic_stream -q` |
| CI check (full) | `ruff check . && black --check . && mypy ollama_chat/ && pytest -q` |

> **Note**: All four CI steps must pass before merging. GitHub Actions runs them
> on every push and pull request (see `.github/workflows/ci.yml`).

---

## Code Style Guidelines

### Module Structure

Every source file follows this order:

```python
"""Module docstring."""

from __future__ import annotations  # ALWAYS first — enables PEP 563 deferred eval

# 1. stdlib imports (alphabetical within each group)
import asyncio
import logging
from pathlib import Path
from typing import Any

# 2. third-party imports
from textual.app import App

# 3. local/relative imports
from .exceptions import OllamaChatError
from .config import load_config

LOGGER = logging.getLogger(__name__)  # module-level logger, always present
```

### Imports

- Always use `from __future__ import annotations` as the very first import.
- Follow the stdlib → third-party → local ordering separated by blank lines.
- Use relative imports (`.module`) for all intra-package references.
- Prefer `from collections.abc import ...` over `from typing import` for
  `Callable`, `Generator`, `AsyncGenerator`, etc. (stdlib since 3.10+).
- Avoid wildcard imports (`from x import *`).
- Lazy/deferred imports inside functions are acceptable only for optional
  dependencies (e.g., `import urllib.parse` inside a try block).

### Formatting

- **Indentation**: 4 spaces (no tabs).
- **Line ending**: LF.
- **Trailing newline**: always present (enforced by `.editorconfig`).
- **Line length**: Black's default (88 chars); Ruff enforces the same.
- Black is the formatter of record — do not hand-format around it.

### Types and Annotations

- Annotate every function signature (parameters and return type). No bare `def`.
- Use the `|` union syntax (`str | None`, not `Optional[str]`).
- Use `list[str]`, `dict[str, Any]`, `tuple[str, ...]` (lowercase generics).
- Use `from typing import Any, Literal` for special forms.
- Use `from collections.abc import Callable, AsyncGenerator` for callable types.
- Mark Pydantic models with `model_config = ConfigDict(populate_by_name=True)`
  where alias fields are needed.
- Prefer `@dataclass` for lightweight value objects (`ChatChunk`, etc.).
- Prefer `frozenset[str]` for immutable sets of capabilities.

### Naming Conventions

| Kind | Convention | Example |
|------|-----------|---------|
| Module | `snake_case` | `message_store.py` |
| Class | `PascalCase` | `OllamaChat`, `StatusBar` |
| Function / method | `snake_case` | `load_config`, `send_user_message` |
| Private helper | `_snake_case` | `_validate_attachment`, `_deep_merge` |
| Module-private constant | `_UPPER_SNAKE_CASE` | `_IMAGE_EXTENSIONS` |
| Public constant | `UPPER_SNAKE_CASE` | `DEFAULT_CONFIG`, `LOGGER` |
| Widget CSS IDs | `kebab-case` | `#app-root`, `#send_button` |
| Widget CSS classes | `kebab-case` | `.message-user`, `.message-assistant` |

### Error Handling

- Define all domain errors in `ollama_chat/exceptions.py`, rooted at `OllamaChatError`.
- Catch the *most specific* exception class available; avoid `except Exception` in
  business logic.
- When a broad catch is unavoidable, annotate with `# noqa: BLE001` and add a
  comment explaining the rationale.
- Always re-raise `asyncio.CancelledError` — never swallow it.
- Use `LOGGER.warning(...)` with structured `extra={"event": "..."}` when
  catching and suppressing expected errors.

### Logging

- Use `LOGGER = logging.getLogger(__name__)` at module scope in every file.
- Log calls use structured extras: `extra={"event": "app.something", "key": val}`.
- Do not use `print()` for diagnostic output; use `LOGGER`.
- Log levels: `DEBUG` for verbose tracing, `INFO` for state transitions,
  `WARNING` for recoverable failures, `ERROR`/`CRITICAL` reserved for unrecoverable states.

### Async Patterns

- Prefer `asyncio.create_task(...)` for fire-and-forget background work.
- Track tasks via `TaskManager` (see `ollama_chat/task_manager.py`) — never
  let tasks become un-referenced garbage.
- Use `await asyncio.to_thread(fn, ...)` for blocking I/O (file writes, etc.).
- Never block the event loop with synchronous I/O inside `async def`.
- Always `await asyncio.wait_for(...)` on subprocess calls with an explicit timeout.

### Pydantic Config Models

- All config sections live in `ollama_chat/config.py` as `BaseModel` subclasses.
- Use `@field_validator` (not deprecated `@validator`) with `mode="before"` to
  normalise and validate raw TOML values.
- Use `@model_validator(mode="after")` for cross-field validation.
- Expose config to the rest of the app as `dict[str, dict[str, Any]]` via
  `Config.model_dump(by_alias=True)`.

---

## Testing Conventions

- All tests live in `tests/`, named `test_*.py`.
- Test classes inherit `unittest.TestCase`; pytest discovers and runs them.
- Use `pytest-asyncio` for async test methods (mark with `@pytest.mark.asyncio`
  or configure `asyncio_mode = "auto"` if needed).
- Use `pytest-mock` (`mocker` fixture) for patching; avoid `unittest.mock` patches
  left active across test boundaries.
- Prefer **fake objects** over `MagicMock` for complex collaborators — see
  `FakeClient` in `tests/test_chat.py` as the canonical example.
- Tests must be hermetic: use `tempfile.TemporaryDirectory()` for any file I/O.
- Do not depend on a running Ollama instance in unit tests.

### Running a Single Test

```bash
# By file
pytest tests/test_chat.py -q

# By class
pytest tests/test_chat.py::StreamTests -q

# By exact method
pytest "tests/test_chat.py::StreamTests::test_basic_stream" -q

# With verbose output
pytest "tests/test_config.py::ConfigTests::test_missing_config_uses_defaults" -v
```

---

## Textual Widget Conventions

- Embed widget CSS directly in the class body as a `CSS = """..."""` string.
- Use `query_one("#id", WidgetType)` to retrieve widgets; cache references in
  `on_mount()` to avoid repeated DOM traversal on hot paths.
- Textual messages (custom events) are inner classes of the widget that emits them.
- Never call `query_one` in tight loops or per-keystroke handlers — use the
  cached `_w_*` attributes set in `on_mount`.

---

## Security Notes

- The Ollama host URL is validated against `security.allowed_hosts` at startup.
- Never relax the host policy without updating both `config.py` (Pydantic model)
  and the runtime check in `app.py`.
- Config files are chmod'd `0600` on POSIX at load time — do not widen permissions.
