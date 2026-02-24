# AGENTS.md — Developer & AI Agent Guide

This document provides context and conventions for AI coding agents and human
developers working in this repository.

---

## Project Overview

**OllamTerm** is a terminal UI chat application built on
[Textual](https://github.com/Textualize/textual) that connects to a locally
running [Ollama](https://ollama.com/) instance. Key design goals are async
streaming with batched rendering, a lock-protected state machine, Pydantic
config validation, and a clean domain exception hierarchy.

- **Language:** Python 3.11+ (local venv uses 3.14)
- **TUI framework:** Textual >=7.5.0
- **LLM client:** ollama Python SDK >=0.1.0 (AsyncClient)
- **Config validation:** Pydantic v2 >=2.0.0
- **Config format:** TOML (stdlib `tomllib`)

---

## Environment Setup

```bash
# Create and activate the virtual environment
python -m venv .venv
source .venv/bin/activate

# Install runtime + dev dependencies
pip install -e '.[dev]'

# Run the application
ollamaterm
# or
python -m ollama_chat
```

---

## Build / Lint / Test Commands

### Testing

```bash
# Run the full test suite (quiet mode, default)
pytest -q

# Run a single test file
pytest tests/test_chat.py -q

# Run a single test class
pytest tests/test_chat.py::ChatTests -q

# Run a single test method
pytest tests/test_chat.py::ChatTests::test_streaming_yields_chunks_and_persists_history -q

# Run with coverage report
pytest --cov=ollama_chat --cov-report=term-missing -q
```

pytest is configured in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
python_files = ["test_*.py"]
addopts = "-q"
```

### Linting and Formatting

```bash
# Lint (Ruff — runs with defaults, no project-level ruff config)
ruff check .

# Format (Black — default 88-char line length)
black .

# Type-check
mypy ollama_chat/
```

mypy is configured in `pyproject.toml`:
```toml
[tool.mypy]
python_version = "3.13"
ignore_missing_imports = true
warn_return_any = true
warn_unused_configs = true
```

### Arch Linux Package

```bash
# Build a wheel for PKGBUILD
python -m build --wheel --no-isolation
```

---

## Code Style Guidelines

### Imports

- Always start every module with `from __future__ import annotations` to enable
  PEP 563 postponed evaluation of type hints.
- Import order: stdlib → third-party → relative package imports.
- Use relative imports within the package (`from .exceptions import ...`).
- Wrap optional/fallback imports in `try/except ModuleNotFoundError` with a
  `None` sentinel and a `# type: ignore` comment on the import line.

```python
from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel
from textual.app import App

from .exceptions import OllamaChatError
```

### Type Annotations

- Annotate **all** function parameters and return types, including `-> None`.
- Use lowercase built-in generics: `dict[str, Any]`, `list[str]`,
  `tuple[str, ...]`, `set[asyncio.Task[Any]]`.
- Use `X | None` union syntax (safe because of `from __future__ import
  annotations`).
- Use `# type: ignore[<code>]` with a specific error code for known edge cases;
  never use a bare `# type: ignore`.

### Naming Conventions

| Construct | Convention | Example |
|---|---|---|
| Classes | `PascalCase` | `OllamaChatApp`, `MessageBubble` |
| Functions / methods | `snake_case` | `load_config`, `on_mount` |
| Private methods | `_snake_case` | `_stream_once`, `_map_exception` |
| Constants | `UPPER_SNAKE_CASE` | `LOGGER`, `DEFAULT_CONFIG` |
| Module-level logger | `LOGGER` | `LOGGER = logging.getLogger(__name__)` |
| Pydantic validators | `_validate_*` / `_normalize_*` | `_validate_hex_color` |

### Formatting

- Line length: **88 characters** (Black default).
- Black is the canonical formatter — do not add `fmt: off` blocks without a
  clear, documented reason.
- Ruff is the linter with default settings. Use `# noqa: <CODE>` inline
  suppressions only when intentional (e.g., `# noqa: BLE001` for deliberate
  broad-catch clauses).

### Error Handling

- Use the domain exception hierarchy rooted at `OllamaChatError(RuntimeError)`
  in `ollama_chat/exceptions.py`. Add new subclasses there; never raise raw
  `RuntimeError` from within the package.
- Translate third-party library exceptions at the boundary via a
  `_map_exception()` helper (see `chat.py`). Inner layers raise domain
  exceptions; callers handle domain exceptions.
- `asyncio.CancelledError` must always be **re-raised** after logging — never
  swallowed.
- Intentional broad catches (`except Exception`) must be annotated with
  `# noqa: BLE001` and followed immediately by a `return` or explicit fallback,
  not silent suppression.
- Config `ValidationError` should fall back to safe defaults; unexpected errors
  should raise `ConfigValidationError`.

### Async Patterns

- Store background tasks in a `set[asyncio.Task[Any]]` and register
  `.add_done_callback(set.discard)` immediately after creation so tasks
  self-clean on completion.
- Protect shared mutable state with `asyncio.Lock`.
- Use `transition_if(expected, new)` atomic helpers for state machine
  transitions (see `state.py`).
- Cancel and `await` all background tasks in `on_unmount` before shutdown.
- Streaming: iterate with `async for chunk in async_generator`.

### Docstrings

- Every module, class, and public method should have a **one-line docstring**.
- No multi-line docstring format is enforced (no Google / NumPy / Sphinx style
  required). Keep them terse and accurate.

### Textual / UI Conventions

- Textual CSS is defined as a class-level `CSS = """..."""` string on the
  widget or app class — not in separate `.tcss` files.
- Widget names follow Textual conventions (`PascalCase`), inheriting from the
  appropriate Textual base class (`Static`, `VerticalScroll`, `Horizontal`,
  etc.).

---

## Testing Conventions

- Test files live in `tests/`, named `test_*.py`.
- Sync tests use `unittest.TestCase`; async tests use
  `unittest.IsolatedAsyncioTestCase`.
- There is **no `conftest.py`** — no shared pytest fixtures. Set up test
  doubles inline or as module-level classes.
- Test doubles are inner classes or module-level classes named `Fake*` or
  `_Fake*` (e.g., `FakeClient`, `_FakeChat`).
- Use assertion methods from `unittest.TestCase` (`assertEqual`, `assertTrue`,
  `assertRaises`, etc.), not bare `assert` statements.
- Guard tests that require optional deps with
  `@unittest.skipIf(Symbol is None, "reason")`.
- Do not use `pytest` fixtures or `pytest.mark` decorators — stay within the
  `unittest` style already established.

---

## Project Layout

```
ollama_chat/          # Main package
  __init__.py         # Lazy re-exports
  __main__.py         # CLI entry point (main())
  app.py              # OllamaChatApp + ModelPickerScreen
  chat.py             # OllamaChat async client wrapper
  config.py           # Pydantic config models + load_config()
  exceptions.py       # Domain exception hierarchy
  logging_utils.py    # Structured JSON logging bootstrap
  message_store.py    # Bounded history + token trimming
  persistence.py      # Conversation save/load/export
  state.py            # Async state machine
  widgets/            # Textual widget components
tests/                # All test files (no conftest.py)
pyproject.toml        # Build, deps, pytest, mypy config
config.example.toml   # Annotated user config template
```

---

## No CI/CD

There is currently no CI pipeline (no `.github/workflows/`, no Makefile).
Before submitting changes, run the following manually:

```bash
ruff check .
black --check .
mypy ollama_chat/
pytest -q
```
