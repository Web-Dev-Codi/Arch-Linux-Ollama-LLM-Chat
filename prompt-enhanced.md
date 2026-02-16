# Ollama Chat TUI - Production Specification (Enhanced)

Version: 0.3.0  
Status: Active specification  
Target runtime: Python 3.11+

This document supersedes the previous enhanced draft and is intended to be directly executable as an engineering specification.

## 1) Goals and Non-Goals

### Goals

- Deliver a robust terminal chat UI for local Ollama models.
- Prevent race conditions and memory growth under long-running sessions.
- Provide deterministic error handling and clear user feedback.
- Keep install/run workflow simple for Arch Linux and generic Linux users.
- Ensure every required behavior is verifiable via explicit pass/fail checks.

### Non-Goals (Tier 1)

- Multi-user collaboration.
- Cloud-hosted model APIs.
- Agentic tool orchestration inside chat responses.
- Plugin ecosystem.

## 2) Delivery Tiers

All requirements in this document are assigned to exactly one tier.

## Tier 1 - MVP (Required for release)

- State machine and request cancellation safety.
- Bounded in-memory message storage and API context trimming.
- Typed exception hierarchy with explicit user-facing mapping.
- Validated configuration model (Pydantic v2) with safe defaults.
- Streaming response rendering with batching (anti-thrash).
- Structured logging with sane defaults.
- Core TUI interactions (send, new conversation, scroll, quit).
- Deterministic tests and baseline quality gates.

## Tier 2 - Post-MVP (Required for 1.x hardening)

- Conversation persistence (save/load/export).
- Model switching picker and model list refresh.
- Status bar with connection/model/stats state.
- Background connection monitoring task.

## Tier 3 - Optional Enhancements

- In-conversation search with highlight navigation.
- Copy-last-assistant-message helper.
- Additional UX polish animations and richer status telemetry.

## 3) System Architecture Contract

This is the canonical module ownership map.

| Module | Responsibility | Primary dependencies |
| --- | --- | --- |
| `ollama_chat/config.py` | Load, merge, and validate app config | `tomllib`/`tomli`, `pydantic` |
| `ollama_chat/state.py` | Conversation state transitions, lock semantics | `asyncio`, `enum` |
| `ollama_chat/message_store.py` | Bounded message store and context trimming | `collections`, `typing` |
| `ollama_chat/exceptions.py` | Domain exception taxonomy | stdlib only |
| `ollama_chat/chat.py` | Ollama client calls, retries, stream parsing | `ollama`, `httpx` (if surfaced) |
| `ollama_chat/app.py` | UI orchestration, key actions, lifecycle tasks | `textual`, internal modules |
| `ollama_chat/widgets/*` | Message/input/conversation/status widgets | `textual`, `rich` |
| `tests/*` | Unit/integration tests mapped to requirements | `pytest`, `pytest-asyncio` |

## 4) Functional Requirements (Normative)

The following statements are mandatory unless marked Tier 2 or Tier 3.

### 4.1 State and Concurrency (Tier 1)

- The app must expose a finite conversation state machine:
  - `IDLE`, `STREAMING`, `ERROR`, `CANCELLING`.
- Message submission must be rejected unless state is `IDLE`.
- State transitions must be lock-protected.
- `new_conversation` during streaming must:
  - transition to `CANCELLING`,
  - cancel the active task,
  - await cancellation completion,
  - clear history/UI,
  - transition back to `IDLE`.
- App shutdown must cancel and await all background tasks.

### 4.2 Message Storage and Context Limits (Tier 1)

- Conversation history must be bounded (`max_history_messages`).
- API context construction must preserve any system message.
- If estimated context exceeds `max_context_tokens`, trim oldest non-system messages first.
- Token estimation heuristic may be approximate, but must be deterministic.
- Export path must serialize messages in stable JSON order.

### 4.3 Exceptions and Error Mapping (Tier 1)

Use explicit domain exceptions:

- `OllamaChatError` (base)
- `OllamaConnectionError`
- `OllamaModelNotFoundError`
- `OllamaStreamingError`
- `ConfigValidationError`

Rules:

- Do not use ambiguous names like `ConnectionError` that collide semantically with built-ins.
- `chat.py` must convert transport/client errors into domain exceptions.
- `app.py` must map domain exceptions to user-safe UI notifications and structured logs.

### 4.4 Configuration Model and Validation (Tier 1)

- Config source: `~/.config/ollama-chat/config.toml`
- Merge order: defaults -> file overrides.
- Validation backend: Pydantic v2 APIs and syntax.
- Validation failure behavior:
  - emit actionable error,
  - continue with safe defaults where possible,
  - fail fast only when required fields are irrecoverable.

Required config sections:

- `[app]`
- `[ollama]`
- `[ui]`
- `[keybinds]`
- `[security]`
- `[logging]`
- `[persistence]` (Tier 2 behavior may be disabled)

### 4.5 Streaming Render Performance (Tier 1)

- UI updates must be batched (`stream_chunk_size >= 1`).
- Message widget updates should use reactive or append-buffer pattern.
- Remaining buffered chunks must flush at stream completion.
- Rendering loop must avoid per-token full widget recompose.

### 4.6 Keyboard Contract (Tier 1 + Tier 2/3)

Terminal-safe defaults:

- `send_message`: `ctrl+enter`
- `new_conversation`: `ctrl+n`
- `quit`: `ctrl+q`
- `scroll_up`: `ctrl+k`
- `scroll_down`: `ctrl+j`
- `toggle_model_picker` (Tier 2): `ctrl+m`
- `save_conversation` (Tier 2): `ctrl+s`
- `load_conversation` (Tier 2): `ctrl+l`
- `export_conversation` (Tier 2): `ctrl+e`
- `search_messages` (Tier 3): `ctrl+f`
- `copy_last_message` (Tier 3): `ctrl+y`

Notes:

- Do not use `ctrl+c` for app copy action by default (reserved SIGINT behavior in terminals).
- All bindings must be configurable via TOML.

### 4.7 Window Class and Title Contract (Tier 1)

- App sets terminal title via ANSI escape sequence.
- App does not attempt to set terminal window class.
- Terminal launcher defines class, for example:
  - `ghostty --class=ollama-chat-tui -e ollama-chat`

## 5) Security and Operations Policy

### 5.1 Host Access Policy (Tier 1)

`[security]` section must control outbound host validation:

- `allow_remote_hosts = false` (default)
- `allowed_hosts = ["localhost", "127.0.0.1", "::1"]` (default)

Behavior:

- If `allow_remote_hosts = false`, `ollama.host` must resolve to a host in `allowed_hosts`.
- If `allow_remote_hosts = true`, any valid `http`/`https` host is allowed.
- Invalid schemes must be rejected.

### 5.2 Config File Permissions (Tier 1)

- On POSIX: enforce `0o600` best-effort for config and persistence metadata.
- On non-POSIX or permission errors: log warning and continue.
- Permission hard-failure is not allowed unless explicit strict mode is added.

### 5.3 Logging Policy (Tier 1)

`[logging]` section:

- `level = "INFO"` default
- `structured = true` default
- `log_to_file = false` default
- `log_file_path = "~/.local/state/ollama-chat/app.log"` default

Rules:

- Redact sensitive values (for example full auth headers if ever introduced).
- Log state transitions, retries, cancellations, and exception categories.
- Do not log full user messages at INFO by default.

## 6) Tier 2 and Tier 3 Requirements

### 6.1 Tier 2 - Required for hardening release

- Conversation persistence:
  - save current conversation,
  - list and load prior conversations,
  - export markdown transcript.
- Model switching:
  - query available models,
  - update active model safely in `IDLE` state.
- Status bar:
  - connection state,
  - active model,
  - message count and estimated context tokens.
- Connection monitor task:
  - periodic check interval configurable,
  - transition-safe notifications on connectivity changes.

### 6.2 Tier 3 - Optional enhancements

- Message search with highlight and jump navigation.
- Copy helper for latest assistant message.
- Additional UI polish and optional animation tuning.

## 7) Requirement-to-Test Traceability

Each Tier 1 requirement must map to at least one deterministic test.

| Requirement ID | Requirement summary | Minimum tests |
| --- | --- | --- |
| `R-STATE-001` | Single in-flight request enforced | unit: state gate check |
| `R-STATE-002` | Cancel stream on reset/shutdown | integration: cancel mid-stream |
| `R-STORE-001` | Bounded history | unit: message maxlen |
| `R-STORE-002` | System message preservation | unit: trim retains system role |
| `R-ERR-001` | Domain exception mapping | unit: transport/model errors mapped |
| `R-CONF-001` | Pydantic v2 validation | unit: invalid config rejected/normalized |
| `R-RENDER-001` | Batched rendering | unit/integration: update call count bounded |
| `R-KEY-001` | Safe default keybind set | unit: generated bindings exclude `ctrl+c` copy |
| `R-SEC-001` | Host policy enforcement | unit: local-only and remote-enabled cases |
| `R-LOG-001` | Structured logging events emitted | unit: transition/retry/cancel logs |

## 8) Quality Gates (Pass/Fail)

These checks are mandatory for Tier 1 readiness.

1. **Static checks**
   - Command: `ruff check .`
   - Pass: zero errors.
2. **Type checks**
   - Command: `mypy ollama_chat`
   - Pass: zero errors in package modules.
3. **Unit + integration tests**
   - Command: `pytest -q`
   - Pass: all tests pass, no unexpected skips.
4. **Coverage**
   - Command: `pytest --cov=ollama_chat --cov-report=term-missing`
   - Pass: line coverage >= 80% for Tier 1 modules.
5. **Stress smoke (manual)**
   - Procedure: run 100+ message interaction with streaming enabled.
   - Pass: no crash, stable responsiveness, bounded memory trend.
6. **Failure-mode validation (manual + automated)**
   - Cases: Ollama down, unknown model, malformed TOML, cancel mid-stream.
   - Pass: user-facing error is clear and app remains usable.

## 9) Implementation Phases

### Phase A - Tier 1 core

- Implement `state.py`, `message_store.py`, `exceptions.py`.
- Upgrade `config.py` to Pydantic v2 validation + policy sections.
- Wire `chat.py` error mapping and retry semantics.
- Add batched rendering and cancellation-safe lifecycle in `app.py`.
- Add structured logging bootstrap.

### Phase B - Tier 1 validation

- Build test matrix for `R-STATE-*`, `R-STORE-*`, `R-ERR-*`, `R-CONF-*`, `R-RENDER-*`, `R-SEC-*`.
- Execute quality gates and fix regressions.

### Phase C - Tier 2 hardening

- Add persistence, model switcher, status bar, connection monitor.
- Add tests for persistence workflows and model-switch safety.

### Phase D - Tier 3 optional

- Add search/copy UX helpers and optional polish.

## 10) Dependency and Tooling Contract

`pyproject.toml` baseline:

- Runtime:
  - `textual>=0.50.0`
  - `ollama>=0.1.0`
  - `pydantic>=2.0.0`
  - `rich>=13.0.0`
- Dev:
  - `pytest>=7.0.0`
  - `pytest-asyncio>=0.21.0`
  - `pytest-mock>=3.10.0`
  - `pytest-cov>=4.0.0`
  - `ruff>=0.1.0`
  - `mypy>=1.0.0`
  - `black>=23.0.0`

## 11) Release Readiness Checklist

Tier 1 release requires all items checked:

- [ ] All Tier 1 requirements implemented.
- [ ] All quality gates pass.
- [ ] README updated with config and keybind policy.
- [ ] `config.example.toml` includes security and logging sections.
- [ ] Hyprland/Ghostty instructions use terminal-controlled class model.

Tier 2 release requires:

- [ ] Persistence/model switching/status monitor complete.
- [ ] Tier 2 tests pass.

## 12) Changelog from Base Prompt

Key deltas from `prompt.md`:

- Added explicit delivery tiers and non-goals.
- Added strict concurrency/state and cancellation contract.
- Added bounded message store and context trimming contract.
- Added domain exception naming and mapping rules.
- Standardized on Pydantic v2 validation model.
- Added host security policy and logging policy sections.
- Added requirement-to-test traceability and pass/fail quality gates.

## Appendix A - Illustrative Snippets (Non-Normative)

These snippets are examples only; requirements above are authoritative.

### A.1 Pydantic v2 field validator pattern

```python
from pydantic import BaseModel, Field, field_validator
from urllib.parse import urlparse

class OllamaConfig(BaseModel):
    host: str = "http://localhost:11434"
    timeout: int = Field(default=120, gt=0, le=600)

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Unsupported host scheme")
        return value
```

### A.2 Exception mapping sketch

```python
class OllamaChatError(Exception):
    pass

class OllamaConnectionError(OllamaChatError):
    pass

class OllamaModelNotFoundError(OllamaChatError):
    pass
```

### A.3 Batched stream append sketch

```python
buffer = []
for chunk in stream:
    buffer.append(chunk)
    if len(buffer) >= stream_chunk_size:
        bubble.append_chunk("".join(buffer))
        buffer.clear()
if buffer:
    bubble.append_chunk("".join(buffer))
```
# Ollama Chat TUI - Production Specification (Enhanced)

Version: 0.3.0  
Status: Active specification  
Target runtime: Python 3.11+

This document supersedes the previous enhanced draft and is intended to be directly executable as an engineering specification.

## 1) Goals and Non-Goals

### Goals

- Deliver a robust terminal chat UI for local Ollama models.
- Prevent race conditions and memory growth under long-running sessions.
- Provide deterministic error handling and clear user feedback.
- Keep install/run workflow simple for Arch Linux and generic Linux users.
- Ensure every required behavior is verifiable via explicit pass/fail checks.

### Non-Goals (Tier 1)

- Multi-user collaboration.
- Cloud-hosted model APIs.
- Agentic tool orchestration inside chat responses.
- Plugin ecosystem.

## 2) Delivery Tiers

All requirements in this document are assigned to exactly one tier.

## Tier 1 - MVP (Required for release)

- State machine and request cancellation safety.
- Bounded in-memory message storage and API context trimming.
- Typed exception hierarchy with explicit user-facing mapping.
- Validated configuration model (Pydantic v2) with safe defaults.
- Streaming response rendering with batching (anti-thrash).
- Structured logging with sane defaults.
- Core TUI interactions (send, new conversation, scroll, quit).
- Deterministic tests and baseline quality gates.

## Tier 2 - Post-MVP (Required for 1.x hardening)

- Conversation persistence (save/load/export).
- Model switching picker and model list refresh.
- Status bar with connection/model/stats state.
- Background connection monitoring task.

## Tier 3 - Optional Enhancements

- In-conversation search with highlight navigation.
- Copy-last-assistant-message helper.
- Additional UX polish animations and richer status telemetry.

## 3) System Architecture Contract

This is the canonical module ownership map.

| Module | Responsibility | Primary dependencies |
|---|---|---|
| `ollama_chat/config.py` | Load, merge, and validate app config | `tomllib`/`tomli`, `pydantic` |
| `ollama_chat/state.py` | Conversation state transitions, lock semantics | `asyncio`, `enum` |
| `ollama_chat/message_store.py` | Bounded message store and context trimming | `collections`, `typing` |
| `ollama_chat/exceptions.py` | Domain exception taxonomy | stdlib only |
| `ollama_chat/chat.py` | Ollama client calls, retries, stream parsing | `ollama`, `httpx` (if surfaced) |
| `ollama_chat/app.py` | UI orchestration, key actions, lifecycle tasks | `textual`, internal modules |
| `ollama_chat/widgets/*` | Message/input/conversation/status widgets | `textual`, `rich` |
| `tests/*` | Unit/integration tests mapped to requirements | `pytest`, `pytest-asyncio` |

## 4) Functional Requirements (Normative)

The following statements are mandatory unless marked Tier 2 or Tier 3.

### 4.1 State and Concurrency (Tier 1)

- The app must expose a finite conversation state machine:
  - `IDLE`, `STREAMING`, `ERROR`, `CANCELLING`.
- Message submission must be rejected unless state is `IDLE`.
- State transitions must be lock-protected.
- `new_conversation` during streaming must:
  - transition to `CANCELLING`,
  - cancel the active task,
  - await cancellation completion,
  - clear history/UI,
  - transition back to `IDLE`.
- App shutdown must cancel and await all background tasks.

### 4.2 Message Storage and Context Limits (Tier 1)

- Conversation history must be bounded (`max_history_messages`).
- API context construction must preserve any system message.
- If estimated context exceeds `max_context_tokens`, trim oldest non-system messages first.
- Token estimation heuristic may be approximate, but must be deterministic.
- Export path must serialize messages in stable JSON order.

### 4.3 Exceptions and Error Mapping (Tier 1)

Use explicit domain exceptions:

- `OllamaChatError` (base)
- `OllamaConnectionError`
- `OllamaModelNotFoundError`
- `OllamaStreamingError`
- `ConfigValidationError`

Rules:

- Do not use ambiguous names like `ConnectionError` that collide semantically with built-ins.
- `chat.py` must convert transport/client errors into domain exceptions.
- `app.py` must map domain exceptions to user-safe UI notifications and structured logs.

### 4.4 Configuration Model and Validation (Tier 1)

- Config source: `~/.config/ollama-chat/config.toml`
- Merge order: defaults -> file overrides.
- Validation backend: Pydantic v2 APIs and syntax.
- Validation failure behavior:
  - emit actionable error,
  - continue with safe defaults where possible,
  - fail fast only when required fields are irrecoverable.

Required config sections:

- `[app]`
- `[ollama]`
- `[ui]`
- `[keybinds]`
- `[security]`
- `[logging]`
- `[persistence]` (Tier 2 behavior may be disabled)

### 4.5 Streaming Render Performance (Tier 1)

- UI updates must be batched (`stream_chunk_size >= 1`).
- Message widget updates should use reactive or append-buffer pattern.
- Remaining buffered chunks must flush at stream completion.
- Rendering loop must avoid per-token full widget recompose.

### 4.6 Keyboard Contract (Tier 1 + Tier 2/3)

Terminal-safe defaults:

- `send_message`: `ctrl+enter`
- `new_conversation`: `ctrl+n`
- `quit`: `ctrl+q`
- `scroll_up`: `ctrl+k`
- `scroll_down`: `ctrl+j`
- `toggle_model_picker` (Tier 2): `ctrl+m`
- `save_conversation` (Tier 2): `ctrl+s`
- `load_conversation` (Tier 2): `ctrl+l`
- `export_conversation` (Tier 2): `ctrl+e`
- `search_messages` (Tier 3): `ctrl+f`
- `copy_last_message` (Tier 3): `ctrl+y`

Notes:

- Do not use `ctrl+c` for app copy action by default (reserved SIGINT behavior in terminals).
- All bindings must be configurable via TOML.

### 4.7 Window Class and Title Contract (Tier 1)

- App sets terminal title via ANSI escape sequence.
- App does not attempt to set terminal window class.
- Terminal launcher defines class, for example:
  - `ghostty --class=ollama-chat-tui -e ollama-chat`

## 5) Security and Operations Policy

### 5.1 Host Access Policy (Tier 1)

`[security]` section must control outbound host validation:

- `allow_remote_hosts = false` (default)
- `allowed_hosts = ["localhost", "127.0.0.1", "::1"]` (default)

Behavior:

- If `allow_remote_hosts = false`, `ollama.host` must resolve to a host in `allowed_hosts`.
- If `allow_remote_hosts = true`, any valid `http`/`https` host is allowed.
- Invalid schemes must be rejected.

### 5.2 Config File Permissions (Tier 1)

- On POSIX: enforce `0o600` best-effort for config and persistence metadata.
- On non-POSIX or permission errors: log warning and continue.
- Permission hard-failure is not allowed unless explicit strict mode is added.

### 5.3 Logging Policy (Tier 1)

`[logging]` section:

- `level = "INFO"` default
- `structured = true` default
- `log_to_file = false` default
- `log_file_path = "~/.local/state/ollama-chat/app.log"` default

Rules:

- Redact sensitive values (for example full auth headers if ever introduced).
- Log state transitions, retries, cancellations, and exception categories.
- Do not log full user messages at INFO by default.

## 6) Tier 2 and Tier 3 Requirements

### 6.1 Tier 2 - Required for hardening release

- Conversation persistence:
  - save current conversation,
  - list and load prior conversations,
  - export markdown transcript.
- Model switching:
  - query available models,
  - update active model safely in `IDLE` state.
- Status bar:
  - connection state,
  - active model,
  - message count and estimated context tokens.
- Connection monitor task:
  - periodic check interval configurable,
  - transition-safe notifications on connectivity changes.

### 6.2 Tier 3 - Optional enhancements

- Message search with highlight and jump navigation.
- Copy helper for latest assistant message.
- Additional UI polish and optional animation tuning.

## 7) Requirement-to-Test Traceability

Each Tier 1 requirement must map to at least one deterministic test.

| Requirement ID | Requirement summary | Minimum tests |
|---|---|---|
| `R-STATE-001` | Single in-flight request enforced | unit: state gate check |
| `R-STATE-002` | Cancel stream on reset/shutdown | integration: cancel mid-stream |
| `R-STORE-001` | Bounded history | unit: message maxlen |
| `R-STORE-002` | System message preservation | unit: trim retains system role |
| `R-ERR-001` | Domain exception mapping | unit: transport/model errors mapped |
| `R-CONF-001` | Pydantic v2 validation | unit: invalid config rejected/normalized |
| `R-RENDER-001` | Batched rendering | unit/integration: update call count bounded |
| `R-KEY-001` | Safe default keybind set | unit: generated bindings exclude `ctrl+c` copy |
| `R-SEC-001` | Host policy enforcement | unit: local-only and remote-enabled cases |
| `R-LOG-001` | Structured logging events emitted | unit: transition/retry/cancel logs |

## 8) Quality Gates (Pass/Fail)

These checks are mandatory for Tier 1 readiness.

1. **Static checks**
   - Command: `ruff check .`
   - Pass: zero errors.
2. **Type checks**
   - Command: `mypy ollama_chat`
   - Pass: zero errors in package modules.
3. **Unit + integration tests**
   - Command: `pytest -q`
   - Pass: all tests pass, no unexpected skips.
4. **Coverage**
   - Command: `pytest --cov=ollama_chat --cov-report=term-missing`
   - Pass: line coverage >= 80% for Tier 1 modules.
5. **Stress smoke (manual)**
   - Procedure: run 100+ message interaction with streaming enabled.
   - Pass: no crash, stable responsiveness, bounded memory trend.
6. **Failure-mode validation (manual + automated)**
   - Cases: Ollama down, unknown model, malformed TOML, cancel mid-stream.
   - Pass: user-facing error is clear and app remains usable.

## 9) Implementation Phases

### Phase A - Tier 1 core

- Implement `state.py`, `message_store.py`, `exceptions.py`.
- Upgrade `config.py` to Pydantic v2 validation + policy sections.
- Wire `chat.py` error mapping and retry semantics.
- Add batched rendering and cancellation-safe lifecycle in `app.py`.
- Add structured logging bootstrap.

### Phase B - Tier 1 validation

- Build test matrix for `R-STATE-*`, `R-STORE-*`, `R-ERR-*`, `R-CONF-*`, `R-RENDER-*`, `R-SEC-*`.
- Execute quality gates and fix regressions.

### Phase C - Tier 2 hardening

- Add persistence, model switcher, status bar, connection monitor.
- Add tests for persistence workflows and model-switch safety.

### Phase D - Tier 3 optional

- Add search/copy UX helpers and optional polish.

## 10) Dependency and Tooling Contract

`pyproject.toml` baseline:

- Runtime:
  - `textual>=0.50.0`
  - `ollama>=0.1.0`
  - `pydantic>=2.0.0`
  - `rich>=13.0.0`
- Dev:
  - `pytest>=7.0.0`
  - `pytest-asyncio>=0.21.0`
  - `pytest-mock>=3.10.0`
  - `pytest-cov>=4.0.0`
  - `ruff>=0.1.0`
  - `mypy>=1.0.0`
  - `black>=23.0.0`

## 11) Release Readiness Checklist

Tier 1 release requires all items checked:

- [ ] All Tier 1 requirements implemented.
- [ ] All quality gates pass.
- [ ] README updated with config and keybind policy.
- [ ] `config.example.toml` includes security and logging sections.
- [ ] Hyprland/Ghostty instructions use terminal-controlled class model.

Tier 2 release requires:

- [ ] Persistence/model switching/status monitor complete.
- [ ] Tier 2 tests pass.

## 12) Changelog from Base Prompt

Key deltas from `prompt.md`:

- Added explicit delivery tiers and non-goals.
- Added strict concurrency/state and cancellation contract.
- Added bounded message store and context trimming contract.
- Added domain exception naming and mapping rules.
- Standardized on Pydantic v2 validation model.
- Added host security policy and logging policy sections.
- Added requirement-to-test traceability and pass/fail quality gates.

## Appendix A - Illustrative Snippets (Non-Normative)

These snippets are examples only; requirements above are authoritative.

### A.1 Pydantic v2 field validator pattern

```python
from pydantic import BaseModel, Field, field_validator
from urllib.parse import urlparse

class OllamaConfig(BaseModel):
    host: str = "http://localhost:11434"
    timeout: int = Field(default=120, gt=0, le=600)

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Unsupported host scheme")
        return value
```

### A.2 Exception mapping sketch

```python
class OllamaChatError(Exception):
    pass

class OllamaConnectionError(OllamaChatError):
    pass

class OllamaModelNotFoundError(OllamaChatError):
    pass
```

### A.3 Batched stream append sketch

```python
buffer = []
for chunk in stream:
    buffer.append(chunk)
    if len(buffer) >= stream_chunk_size:
        bubble.append_chunk("".join(buffer))
        buffer.clear()
if buffer:
    bubble.append_chunk("".join(buffer))
```
# Ollama Chat TUI - Enhanced Production-Ready Architecture

**Version 0.2.0** - Incorporates critical architectural improvements

This specification builds on the original requirements with production-ready enhancements for state management, error handling, message storage, persistence, and comprehensive testing.

## 🎯 CRITICAL ARCHITECTURAL IMPROVEMENTS

### 1. **State Management** (REQUIRED - Prevents Race Conditions)

**Problem Solved:** Original spec had no protection against concurrent requests, mid-stream conversation clears, or proper cleanup.

**Solution:** Add `state.py` with StateManager class:

```python
from enum import Enum
from asyncio import Lock

class ConversationState(Enum):
    IDLE = "idle"
    STREAMING = "streaming"
    ERROR = "error"
    CANCELLING = "cancelling"

class StateManager:
    """Manage application state and prevent race conditions."""
    def __init__(self):
        self._state = ConversationState.IDLE
        self._lock = Lock()
        
    def can_send_message(self) -> bool:
        """Check if new message can be sent."""
        return self._state == ConversationState.IDLE
    
    async def transition_to(self, new_state: ConversationState):
        """Thread-safe state transition."""
        async with self._lock:
            self._state = new_state
```

**Integration in app.py:**
```python
class OllamaChatApp(App):
    def __init__(self):
        self.state_manager = StateManager()
        self.current_task: Optional[asyncio.Task] = None
        self._request_lock = asyncio.Lock()
    
    async def send_user_message(self):
        if not self.state_manager.can_send_message():
            self.notify("Already processing", severity="warning")
            return
            
        async with self._request_lock:
            # Process message...
            pass
    
    async def action_new_conversation(self):
        # Cancel in-flight requests
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
            try:
                await self.current_task
            except asyncio.CancelledError:
                pass
```

---

### 2. **Message Storage with Limits** (REQUIRED - Prevents Memory Leaks)

**Problem Solved:** Original spec had unbounded message history leading to memory leaks and performance degradation.

**Solution:** Add `message_store.py`:

```python
from collections import deque
from typing import List, Dict

class MessageStore:
    """Bounded message storage with context window management."""
    
    def __init__(self, max_messages: int = 100):
        self._messages: deque = deque(maxlen=max_messages)
        self._max_messages = max_messages
    
    def add_message(self, role: str, content: str, timestamp: str = ""):
        """Add message, automatically trim if needed."""
        self._messages.append({
            "role": role,
            "content": content,
            "timestamp": timestamp
        })
    
    def get_api_context(self, max_tokens: int = 4000) -> List[Dict]:
        """Return messages that fit in context window."""
        # Preserve system message
        system_msgs = [m for m in self._messages if m["role"] == "system"]
        other_msgs = [m for m in self._messages if m["role"] != "system"]
        
        # Estimate tokens and trim from middle if needed
        total_tokens = sum(self.estimate_tokens(m["content"]) for m in other_msgs)
        
        if total_tokens > max_tokens:
            # Keep recent messages, trim from middle
            keep_recent = other_msgs[-20:]  # Adjust based on token count
            return system_msgs + keep_recent
        
        return list(self._messages)
    
    def estimate_tokens(self, text: str) -> int:
        """Simple token estimation: ~4 chars per token."""
        return len(text) // 4
    
    def export_to_json(self) -> str:
        """Export conversation as JSON."""
        import json
        return json.dumps(list(self._messages), indent=2)
```

**Config addition:**
```toml
[ollama]
max_history_messages = 100
max_context_tokens = 4000
```

---

### 3. **Custom Exception Hierarchy** (REQUIRED - Better Error Handling)

**Problem Solved:** Generic exceptions make debugging and error handling difficult.

**Solution:** Add `exceptions.py`:

```python
class OllamaError(Exception):
    """Base exception for Ollama-related errors."""
    pass

class ConnectionError(OllamaError):
    """Cannot connect to Ollama service."""
    pass

class ModelNotFoundError(OllamaError):
    """Requested model doesn't exist."""
    pass

class StreamingError(OllamaError):
    """Error during response streaming."""
    pass

class ConfigError(Exception):
    """Configuration validation error."""
    pass
```

**Usage in chat.py:**
```python
async def send_message(self, user_message: str):
    try:
        async for chunk in ollama.chat(...):
            yield chunk
    except httpx.ConnectError as e:
        raise ConnectionError(f"Cannot connect to {self.host}") from e
    except KeyError:
        raise ModelNotFoundError(f"Model '{self.model}' not found")
```

**Error handling in app.py:**
```python
async def send_user_message(self):
    try:
        async for chunk in self.chat.send_message(message):
            # Process chunk
            pass
    except ConnectionError:
        self.notify("⚠️ Ollama not running", severity="error")
    except ModelNotFoundError as e:
        self.notify(f"⚠️ {e}", severity="error")
    except Exception as e:
        logger.exception("Unexpected error")
        self.notify(f"Error: {e}", severity="error")
```

---

### 4. **Configuration Validation** (REQUIRED - Prevent Runtime Errors)

**Problem Solved:** Invalid config values cause cryptic runtime errors.

**Solution:** Add Pydantic validation to `config.py`:

```python
from pydantic import BaseModel, Field, validator
from urllib.parse import urlparse

class OllamaConfig(BaseModel):
    host: str = "http://localhost:11434"
    model: str = Field(min_length=1)
    timeout: int = Field(gt=0, le=600)
    max_history_messages: int = Field(default=100, gt=0)
    max_context_tokens: int = Field(default=4000, gt=0)
    
    @validator('host')
    def validate_host(cls, v):
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Invalid URL scheme")
        # Prevent SSRF
        if parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("Only localhost allowed")
        return v

class UIConfig(BaseModel):
    background_color: str = Field(regex=r'^#[0-9a-fA-F]{6}$')
    user_message_color: str = Field(regex=r'^#[0-9a-fA-F]{6}$')
    # ... validate all color fields
    stream_chunk_size: int = Field(default=10, ge=1, le=100)

class Config(BaseModel):
    app: AppConfig
    ollama: OllamaConfig
    ui: UIConfig
    persistence: PersistenceConfig
    keybinds: Dict[str, str]

def load_config() -> Config:
    """Load and validate configuration."""
    try:
        raw_config = load_raw_toml()
        return Config(**raw_config)
    except ValidationError as e:
        raise ConfigError(f"Invalid config: {e}")
```

---

### 5. **Streaming with Batch Rendering** (REQUIRED - Performance)

**Problem Solved:** Original spec updates UI on every chunk, causing render thrashing.

**Solution:** Batch chunks before updating:

```python
async def send_user_message(self):
    assistant_bubble = conversation.add_message("", "assistant")
    
    buffer = []
    chunk_size = self.config.ui.stream_chunk_size  # Default: 10
    
    async for chunk in self.chat.send_message(message):
        buffer.append(chunk)
        if len(buffer) >= chunk_size:
            assistant_bubble.append_chunk("".join(buffer))
            buffer.clear()
    
    # Flush remaining
    if buffer:
        assistant_bubble.append_chunk("".join(buffer))
```

**Widget using reactive properties:**
```python
from textual.reactive import reactive

class MessageBubble(Static):
    content = reactive("")
    
    def watch_content(self, new_content: str):
        """Auto-update on content change."""
        self.update(self._render_content())
    
    def append_chunk(self, chunk: str):
        self.content += chunk  # Triggers watch_content
```

---

### 6. **Logging Infrastructure** (REQUIRED - Debugging)

**Problem Solved:** No visibility into errors or application behavior.

**Solution:** Add structured logging:

```python
import logging
from rich.logging import RichHandler

def setup_logging(log_level: str = "INFO"):
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True)]
    )
    
    logging.getLogger("ollama_chat").setLevel(log_level)
    logging.getLogger("httpx").setLevel(logging.WARNING)

# Usage throughout app:
logger = logging.getLogger("ollama_chat")
logger.info("Application started")
logger.error(f"Connection failed: {error}")
logger.debug(f"State transition: {old} -> {new}")
```

**Config addition:**
```toml
[app]
log_level = "INFO"  # DEBUG|INFO|WARNING|ERROR|CRITICAL
```

---

## 🆕 NEW FEATURES (Should Add)

### 7. **Conversation Persistence**

**File format:**
```json
{
  "id": "uuid-here",
  "created_at": "2024-01-01T12:00:00Z",
  "updated_at": "2024-01-01T13:00:00Z",
  "model": "llama3.2",
  "title": "First user message preview...",
  "message_count": 42,
  "messages": [...]
}
```

**Implementation:**
```python
async def save_current_conversation(self):
    """Save conversation to JSON file."""
    if not self.message_store.get_message_count():
        return
    
    conv_data = {
        "id": str(uuid.uuid4()),
        "created_at": self.conversation_start_time.isoformat(),
        "updated_at": datetime.now().isoformat(),
        "model": self.chat.current_model,
        "title": self._generate_title(),
        "messages": self.message_store.get_all_messages()
    }
    
    filename = f"{conv_data['id']}.json"
    path = Path(self.config.persistence.conversations_dir) / filename
    path.write_text(json.dumps(conv_data, indent=2))
```

**Config:**
```toml
[persistence]
enabled = true
auto_save = true
conversations_dir = "~/.local/share/ollama-chat/conversations"
max_saved_conversations = 50
```

**Actions:**
- `Ctrl+S`: Manual save
- `Ctrl+L`: Load conversation (shows picker)
- `Ctrl+E`: Export as markdown
- Auto-save on exit

---

### 8. **Model Switching**

```python
async def action_toggle_model_picker(self):
    """Show model selection dialog."""
    models = await self.chat.get_available_models()
    selected = await self.show_picker_dialog(models)
    
    if selected:
        self.chat.switch_model(selected)
        self.notify(f"Switched to: {selected}")
```

**Keybind:** `Ctrl+M`

---

### 9. **Message Search**

```python
async def action_search_messages(self):
    """Search and highlight messages."""
    query = await self.show_input_dialog("Search:")
    if query:
        conversation = self.query_one(ConversationView)
        conversation.search_messages(query)
```

**Keybind:** `Ctrl+F`

---

### 10. **Copy Last Message**

```python
async def action_copy_last_message(self):
    """Copy last assistant message to clipboard."""
    messages = self.message_store.get_all_messages()
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    
    if assistant_msgs:
        await self.copy_to_clipboard(assistant_msgs[-1]["content"])
        self.notify("✓ Copied to clipboard")
```

**Keybind:** `Ctrl+C`

---

### 11. **Status Bar Widget** (NEW)

```python
class StatusBar(Static):
    """Display connection status, state, and stats."""
    
    def compose(self):
        yield Label(id="connection")
        yield Label(id="state")
        yield Label(id="model")
        yield Label(id="stats")
    
    def update_connection(self, connected: bool):
        icon = "🟢" if connected else "🔴"
        self.query_one("#connection").update(f"{icon} Ollama")
    
    def update_stats(self, msg_count: int, tokens: int, max_tokens: int):
        self.query_one("#stats").update(
            f"Messages: {msg_count} | Tokens: ~{tokens}/{max_tokens}"
        )
```

---

### 12. **Connection Monitoring**

```python
async def monitor_ollama_connection(self):
    """Background task to check Ollama availability."""
    while True:
        try:
            connected = await self.chat.test_connection()
            self.query_one(StatusBar).update_connection(connected)
            
            if not connected and self.was_connected:
                self.notify("⚠️ Lost connection", severity="warning")
            elif connected and not self.was_connected:
                self.notify("✓ Reconnected", severity="success")
            
            self.was_connected = connected
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        
        await asyncio.sleep(30)  # Check every 30s

# Start in on_mount:
self.monitor_task = asyncio.create_task(self.monitor_ollama_connection())
```

---

## 📦 UPDATED DEPENDENCIES

**pyproject.toml:**
```toml
[project]
name = "ollama-chat-tui"
version = "0.2.0"
requires-python = ">=3.11"
dependencies = [
    "textual>=0.50.0",
    "ollama>=0.1.0",
    "pydantic>=2.0.0",      # NEW: Config validation
    "rich>=13.0.0",          # NEW: Logging
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-mock>=3.10.0",
    "black>=23.0.0",
    "mypy>=1.0.0",
    "ruff>=0.1.0",
]
```

---

## 🧪 COMPREHENSIVE TESTING

**conftest.py:**
```python
import pytest

@pytest.fixture
async def mock_ollama_response():
    """Mock streaming response."""
    async def _generate(message: str):
        for word in message.split():
            yield {"message": {"content": word + " "}}
    return _generate

@pytest.fixture
def message_store():
    return MessageStore(max_messages=10)
```

**test_message_store.py:**
```python
def test_message_limit(message_store):
    for i in range(20):
        message_store.add_message("user", f"Message {i}")
    
    assert message_store.get_message_count() == 10

def test_system_message_preserved(message_store):
    message_store.add_message("system", "System prompt")
    for i in range(15):
        message_store.add_message("user", f"Message {i}")
    
    messages = message_store.get_all_messages()
    assert messages[0]["role"] == "system"

def test_token_estimation(message_store):
    tokens = message_store.estimate_tokens("Hello world!")
    assert tokens == 3  # 12 chars / 4 = 3 tokens
```

**test_state.py:**
```python
@pytest.mark.asyncio
async def test_state_transitions():
    manager = StateManager()
    
    assert manager.can_send_message()
    
    await manager.transition_to(ConversationState.STREAMING)
    assert not manager.can_send_message()
    
    await manager.transition_to(ConversationState.IDLE)
    assert manager.can_send_message()
```

---

## 🔒 SECURITY ENHANCEMENTS

**Config file permissions:**
```python
def ensure_config_security(config_path: Path):
    """Set proper file permissions."""
    import os
    os.chmod(config_path, 0o600)  # Owner read/write only
```

**SSRF prevention:**
```python
@validator('host')
def validate_host(cls, v):
    parsed = urlparse(v)
    if parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Only localhost connections allowed")
    return v
```

---

## ⚠️ CORRECTED SPECIFICATIONS

### Window Class Issue (CORRECTED)

**Original spec was WRONG:** Applications cannot set their own window class.

**Correct approach:**
```bash
# Terminal sets class, not the app
ghostty --class=ollama-chat-tui -e ollama-chat
```

**App only sets title:**
```python
print(f"\033]0;{title}\007", end='', flush=True)
```

---

## ✅ IMPLEMENTATION CHECKLIST

### Phase 1: Core + Architecture (Week 1)
- [ ] Project structure
- [ ] exceptions.py - Custom exceptions
- [ ] state.py - State management
- [ ] message_store.py - Bounded storage
- [ ] config.py with Pydantic validation
- [ ] Logging setup
- [ ] Basic UI with Textual

### Phase 2: Core Features (Week 2)
- [ ] Ollama client integration
- [ ] Streaming with batched rendering
- [ ] Error handling end-to-end
- [ ] Message display with reactive widgets
- [ ] Input handling
- [ ] Task cancellation

### Phase 3: Enhanced Features (Week 3)
- [ ] StatusBar widget
- [ ] Conversation persistence
- [ ] Model switching dialog
- [ ] Message search
- [ ] Copy functionality
- [ ] Export conversations
- [ ] Connection monitoring

### Phase 4: Polish & Testing (Week 4)
- [ ] Unit tests (>80% coverage)
- [ ] Integration tests
- [ ] Performance optimization
- [ ] Documentation (README, PKGBUILD)
- [ ] Example configurations
- [ ] Desktop entry

---

## 📊 ARCHITECTURE QUALITY GATES

Before considering production-ready:

1. ✅ **No race conditions** - State manager prevents concurrent requests
2. ✅ **Bounded memory** - Message store has limits
3. ✅ **Proper cleanup** - Tasks cancelled on exit
4. ✅ **Error handling** - All exceptions caught and displayed
5. ✅ **Config validation** - Pydantic prevents invalid configs
6. ✅ **Logging** - All important events logged
7. ✅ **Testing** - >80% code coverage
8. ✅ **Performance** - Handles 1000+ message conversations

---

## 🎯 SUCCESS METRICS

**Production-ready means:**
- ✅ Runs for hours without crashes
- ✅ Handles connection failures gracefully
- ✅ No memory leaks in long conversations
- ✅ Responsive UI even during streaming
- ✅ Clear error messages for all failures
- ✅ Comprehensive logs for debugging
- ✅ Easy to install and configure

---

## 📚 REFERENCE IMPLEMENTATION

All architectural patterns follow Python/asyncio best practices:
- State machines for complex async workflows
- Context managers for resource cleanup
- Structured exception hierarchies
- Pydantic for data validation
- Rich for beautiful terminal output
- pytest for comprehensive testing

**Estimated effort:** 3-4 weeks for production-ready implementation

**Technical complexity:** Medium-High (async state management, streaming, TUI)

**Maintainability:** High (well-structured, tested, documented)

---

For original requirements, see the base prompt. This enhanced specification adds ~40% more implementation work but delivers a production-ready application suitable for daily use.
