# Ollama Chat TUI

> **A keyboard-first, fully local AI chat interface for the terminal.**  
> Powered by [Ollama](https://ollama.com/) and [Textual](https://github.com/Textualize/textual) — no cloud, no API keys, no data leaving your machine.

```
┌─────────────────────────────────────────────────────────┐
│  Ollama Chat                        [llama3.2] ● Online │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  You  ────────────────────────────────────────────────  │
│  Explain async/await in Python in one paragraph.        │
│                                                         │
│  Assistant  ──────────────────────────────────────────  │
│  async/await is Python's syntax for writing coroutines  │
│  — functions that can pause execution with `await`,     │
│  yielding control back to the event loop while waiting  │
│  for I/O, then resuming where they left off...          │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  > Type a message...                     ctrl+p for help│
└─────────────────────────────────────────────────────────┘
```

---

## Table of Contents

- [Why Ollama Chat TUI?](#why-ollama-chat-tui)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
  - [Config File Location](#config-file-location)
  - [All Options](#all-options)
- [Keybinds](#keybinds)
- [Capabilities](#capabilities)
- [Desktop Integration](#desktop-integration)
  - [Hyprland + Ghostty](#hyprland--ghostty)
  - [Desktop Entry](#desktop-entry)
- [Packaging](#packaging)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

---

## Why Ollama Chat TUI?

| | Ollama Chat TUI | Web-based chat UIs |
|---|---|---|
| **Privacy** | 100% local — data never leaves your machine | Depends on provider |
| **Offline use** | Works after initial model pull | Requires internet |
| **Cost** | Free (you own the hardware) | Often metered |
| **Speed** | No network latency to the model | Round-trip to cloud |
| **Customization** | Full TOML config, rebindable keys | Usually limited |
| **Terminal native** | Keyboard-first, scriptable | Browser tab |

---

## Features

### Core Chat

- **Streaming responses** with batched rendering for smooth, flicker-free output
- **Animated "thinking" placeholder** shown while the model starts generating
- **Bounded context window** — automatically trims history to stay within token limits
- **Retry with backoff** for resilient streaming on transient Ollama failures

### Model Management

- **Multi-model config** — list multiple models and switch at runtime
- **Clickable model picker** in the status bar, or `ctrl+m` keyboard shortcut
- **Auto-pull on startup** — optionally pull the configured model if it is not present
- **Traffic-light connection indicator** — always know if Ollama is reachable

### Conversation Persistence

- **Save and load** conversation history (JSON format)
- **Export** conversations as Markdown transcripts
- **Search messages** and cycle through results from the input box
- **Copy** the latest assistant reply to clipboard in one shortcut

### Capabilities (optional)

- **Chain-of-thought reasoning** (`think = true`) for supported models (e.g. `qwen3`, `deepseek-r1`)
- **Tool calling** and an agent loop for multi-step model actions
- **Web search** via Ollama's built-in tools (requires Ollama API key)
- **Vision / image attachments** for vision-capable models (e.g. `gemma3`, `llava`)

### Interface & Integration

- **Command palette** (`ctrl+p`) with searchable list of all actions
- **Fully configurable keybinds** via TOML
- **Structured JSON logging** with optional file output for debugging
- **Terminal title** and window class set on startup for WM rules
- **Desktop entry** and Hyprland/Ghostty integration examples included

---

## Requirements

| Requirement | Details |
|---|---|
| Python | 3.11 or newer |
| Ollama | Installed and on your `PATH` ([install guide](https://ollama.com/download)) |
| Ollama daemon | Running — `ollama serve` |
| Internet | Only needed once, to pull models |

---

## Installation

### From source (recommended)

```bash
git clone https://github.com/Web-Dev-Codi/Arch-Linux-Ollama-LLM-Chat.git
cd Arch-Linux-Ollama-LLM-Chat

python -m venv .venv
source .venv/bin/activate

pip install -e .
```

### Developer / contributor install

Includes test runners, linter, formatter, and type checker:

```bash
pip install -e '.[dev]'
```

### Arch Linux (PKGBUILD)

A `PKGBUILD` is included for building a native Arch package:

```bash
makepkg -si
```

---

## Quick Start

**1. Start Ollama and pull a model**

```bash
ollama serve
ollama pull llama3.2
```

**2. (Optional) Copy the example config**

The app works out of the box with sensible defaults. To customize:

```bash
mkdir -p ~/.config/ollama-chat
cp config.example.toml ~/.config/ollama-chat/config.toml
```

**3. Launch the app**

```bash
ollama-chat
# or
python -m ollama_chat
```

**4. Basic workflow**

| Action | How |
|---|---|
| Send a message | Type in the input field → `ctrl+enter` |
| Switch model | Click `Model` in the status bar, or `ctrl+m` |
| New conversation | `ctrl+n` |
| Search messages | `ctrl+f`, type query, press again to cycle |
| Copy last reply | `ctrl+y` |
| Open all actions | `ctrl+p` |
| Quit | `ctrl+q` |

---

## Configuration

### Config File Location

```
~/.config/ollama-chat/config.toml
```

If the file does not exist, built-in defaults are used automatically.  
Use `config.example.toml` from the repo as your starting point.

### All Options

```toml
[app]
# Window title shown in the TUI header
title = "Ollama Chat"
# WM window class set on startup (useful for Hyprland/i3 rules)
class = "ollama-chat-tui"
# How often (seconds) to check Ollama connectivity
connection_check_interval_seconds = 15

[ollama]
# Ollama API endpoint
host = "http://localhost:11434"
# Default active model
model = "llama3.2"
# All models available in the picker
models = ["llama3.2", "qwen2.5", "mistral"]
# Request timeout in seconds
timeout = 120
# System prompt injected at the start of every conversation
system_prompt = "You are a helpful assistant."
# Maximum messages kept in history
max_history_messages = 200
# Token budget for context trimming
max_context_tokens = 4096
# Pull the model on startup if not present locally
pull_model_on_start = true

[ui]
font_size = 14
background_color = "#1a1b26"
user_message_color = "#7aa2f7"
assistant_message_color = "#9ece6a"
border_color = "#565f89"
show_timestamps = true
# Number of streaming chunks to buffer before rendering
stream_chunk_size = 8

[keybinds]
send_message = "ctrl+enter"
new_conversation = "ctrl+n"
quit = "ctrl+q"
scroll_up = "ctrl+k"
scroll_down = "ctrl+j"
command_palette = "ctrl+p"
toggle_model_picker = "ctrl+m"
save_conversation = "ctrl+s"
load_conversation = "ctrl+l"
export_conversation = "ctrl+e"
search_messages = "ctrl+f"
copy_last_message = "ctrl+y"

[security]
# Set true to allow non-localhost Ollama endpoints
allow_remote_hosts = false
allowed_hosts = ["localhost", "127.0.0.1", "::1"]

[logging]
level = "INFO"          # DEBUG | INFO | WARNING | ERROR
structured = true       # JSON-formatted log lines
log_to_file = false
log_file_path = "~/.local/state/ollama-chat/app.log"

[persistence]
enabled = false
directory = "~/.local/state/ollama-chat/conversations"
metadata_path = "~/.local/state/ollama-chat/conversations/index.json"

[capabilities]
# Chain-of-thought reasoning (models: qwen3, deepseek-r1, deepseek-v3.1)
think = true
# Display the reasoning trace inside the assistant bubble
show_thinking = true
# Enable the tool-calling agent loop
tools_enabled = true
# Built-in web_search / web_fetch (requires OLLAMA_API_KEY)
web_search_enabled = false
web_search_api_key = ""
# Vision / image attachments (models: gemma3, llava)
# Use /image <path> or click Attach
vision_enabled = true
# Max tool-call iterations per message before the loop stops
max_tool_iterations = 10
```

---

## Keybinds

All keybinds are rebindable in `[keybinds]`. These are the defaults:

| Keybind | Action |
|---|---|
| `ctrl+enter` | Send message |
| `ctrl+n` | New conversation |
| `ctrl+q` | Quit |
| `ctrl+k` | Scroll up |
| `ctrl+j` | Scroll down |
| `ctrl+p` | Open command palette |
| `ctrl+m` | Open model picker |
| `ctrl+s` | Save conversation *(requires persistence enabled)* |
| `ctrl+l` | Load latest saved conversation *(requires persistence enabled)* |
| `ctrl+e` | Export Markdown transcript *(requires persistence enabled)* |
| `ctrl+f` | Search messages (press again to cycle results) |
| `ctrl+y` | Copy last assistant message to clipboard |

---

## Capabilities

### Chain-of-thought reasoning

Enable `think = true` in `[capabilities]` for models that support it
(e.g. `qwen3`, `deepseek-r1`). The model's internal reasoning trace is shown
above its final answer when `show_thinking = true`.

### Tool calling

Set `tools_enabled = true` to activate the agent loop. The model can invoke
tools multiple times before producing a final answer.

### Web search

Set `web_search_enabled = true` and provide an Ollama API key (via
`web_search_api_key` or the `OLLAMA_API_KEY` environment variable) to allow
the model to search and fetch web pages during a response.

### Vision / image attachments

Set `vision_enabled = true` and use a vision-capable model (e.g. `gemma3`,
`llava`). Attach images with `/image <path>` in the input box.

---

## Desktop Integration

### Hyprland + Ghostty

The app sets the terminal window class from `app.class` on startup.
For the most reliable behavior on Wayland, also pass the class directly to
your terminal:

```bash
ghostty --class=ollama-chat-tui -e ollama-chat
```

Suggested Hyprland window rules (`~/.config/hypr/hyprland.conf`):

```conf
windowrulev2 = float,          class:^(ollama-chat-tui)$
windowrulev2 = size 1200 800,  class:^(ollama-chat-tui)$
windowrulev2 = center,         class:^(ollama-chat-tui)$
windowrulev2 = opacity 0.95,   class:^(ollama-chat-tui)$

bind = $mainMod, O, exec, ghostty --class=ollama-chat-tui -e ollama-chat
```

### Desktop Entry

Create `~/.local/share/applications/ollama-chat.desktop`:

```desktop
[Desktop Entry]
Type=Application
Name=Ollama Chat
Comment=ChatGPT-style TUI for Ollama local LLMs
Exec=ghostty --class=ollama-chat-tui -e ollama-chat
Icon=utilities-terminal
Terminal=false
Categories=Utility;TerminalEmulator;Development;
```

---

## Packaging

| Format | Instructions |
|---|---|
| Python wheel | `python -m build --wheel --no-isolation` |
| Arch Linux | `makepkg -si` (uses included `PKGBUILD`) |

Build configuration lives in `pyproject.toml`.

---

## Building

### Local wheel build (isolated)

```bash
python -m pip install build
python -m build --wheel
# optional: install into current env
python -m pip install --force-reinstall dist/*.whl
# or install for user with pipx
pipx install .
```

Troubleshooting: if you see `BackendUnavailable: Cannot import 'setuptools.build_meta'`, either run the isolated build above, or install/upgrade in your active environment:

```bash
python -m pip install -U setuptools wheel build
# For Python 3.14 pre-releases, you may need:
python -m pip install --pre -U setuptools
```

### Arch package (PKGBUILD)

This repo ships a `PKGBUILD` that builds without network access using system makedepends:

```bash
sudo pacman -S --needed base-devel python-setuptools python-build python-installer python-wheel
makepkg -si
```

The `build()` step uses `python -m build --wheel --no-isolation` so it relies on the above makedepends instead of downloading during build.

---

## Development

```bash
# Full test suite
pytest -q

# With coverage report
pytest --cov=ollama_chat --cov-report=term-missing -q

# Lint
ruff check .

# Format check
black --check .

# Type check
mypy ollama_chat/
```

Run all checks before submitting changes:

```bash
ruff check . && black --check . && mypy ollama_chat/ && pytest -q
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Connection error` on startup | Ensure `ollama serve` is running; verify `ollama.host` in config |
| "Model not found" warning | Set `pull_model_on_start = true`, or run `ollama pull <model>` manually |
| Empty or cut-off response | Check `ollama list` to confirm the model name; review Ollama logs |
| Keybind not responding | Verify the syntax in `[keybinds]` and restart the app |
| Colors not applied | Use valid hex format: `#RRGGBB` or `#RGB` |
| Window class rule not matching | Ensure `app.class` is set; prefer launching with `ghostty --class=ollama-chat-tui` |
| Tool loop not stopping | Lower `max_tool_iterations` in `[capabilities]` |

---

## License

[MIT](LICENSE) — © Web-Dev-Codi
