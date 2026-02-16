# Ollama Chat TUI

`ollama-chat-tui` is a ChatGPT-style terminal UI built with Textual for local Ollama models.  
It supports streaming responses, configurable keybinds, and Hyprland/Ghostty-friendly launch behavior.

## Features

- Streaming responses from Ollama with batched UI rendering.
- Lock-protected app state machine with cancellation-safe reset/shutdown.
- Bounded message history with deterministic context token trimming.
- Domain exception mapping with user-safe error notifications.
- Configurable app, model, UI colors, security policy, logging, and keybinds via TOML.
- Clear user/assistant message bubbles with optional timestamps.
- Keyboard-first workflow for sending, scrolling, new chat, and quit.
- Terminal title is set by the app; terminal class is set by your launcher.
- Python package with console entrypoint: `ollama-chat`.

## Requirements

- Python 3.11+
- Ollama installed and available in `PATH`
- Ollama daemon available locally (`ollama serve`)

## Installation

### Quick start (recommended)

```bash
git clone https://github.com/Web-Dev-Codi/Arch-Linux-Ollama-LLM-Chat.git
cd Arch-Linux-Ollama-LLM-Chat
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Install modes

- **Standard use**: `pip install -e .`
- **Contributor/dev mode**: `pip install -e '.[dev]'`

## Run and use the app

### 1) Start Ollama and pull a model

```bash
ollama serve
ollama pull llama3.2
```

### 2) Optional: create your config file

Defaults are loaded automatically, but you can start from the example:

```bash
mkdir -p ~/.config/ollama-chat
cp config.example.toml ~/.config/ollama-chat/config.toml
```

### 3) Launch the TUI

```bash
ollama-chat
```

Alternative entrypoint:

```bash
python -m ollama_chat
```

### 4) Basic workflow

- Type your prompt in the input field.
- Press `ctrl+enter` to send.
- Click `Model` in the status bar to pick a configured model.
- Use `ctrl+n` to start a new conversation.
- Use `ctrl+q` to quit.

## Configuration

Configuration file location:

`~/.config/ollama-chat/config.toml`

If the file does not exist, defaults are used automatically.  
Use `config.example.toml` as a starting point.

Example:

```toml
[app]
title = "Ollama Chat"
class = "ollama-chat-tui"
connection_check_interval_seconds = 15

[ollama]
host = "http://localhost:11434"
model = "llama3.2"
models = ["llama3.2", "qwen2.5", "mistral"]
timeout = 120
system_prompt = "You are a helpful assistant."
max_history_messages = 200
max_context_tokens = 4096
pull_model_on_start = true

[ui]
font_size = 14
background_color = "#1a1b26"
user_message_color = "#7aa2f7"
assistant_message_color = "#9ece6a"
border_color = "#565f89"
show_timestamps = true
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
allow_remote_hosts = false
allowed_hosts = ["localhost", "127.0.0.1", "::1"]

[logging]
level = "INFO"
structured = true
log_to_file = false
log_file_path = "~/.local/state/ollama-chat/app.log"

[persistence]
enabled = false
directory = "~/.local/state/ollama-chat/conversations"
metadata_path = "~/.local/state/ollama-chat/conversations/index.json"
```

## Keybinds

Default keybinds:

- `ctrl+enter`: Send message
- `ctrl+n`: New conversation
- `ctrl+q`: Quit
- `ctrl+k`: Scroll up
- `ctrl+j`: Scroll down
- `ctrl+p`: Open command palette
- `ctrl+m`: Open configured model picker
- `ctrl+s`: Save conversation (requires `[persistence].enabled = true`)
- `ctrl+l`: Load latest saved conversation (requires persistence enabled)
- `ctrl+e`: Export markdown transcript (requires persistence enabled)
- `ctrl+f`: Search messages (type query in input box, then press again to cycle)
- `ctrl+y`: Copy last assistant message to clipboard

## Hyprland + Ghostty integration

The app sets terminal title using ANSI escape codes at startup and does not set terminal window class directly.
Set your terminal class in the launcher command (for example Ghostty `--class`).

Launch directly with a class:

```bash
ghostty --class=ollama-chat-tui -e ollama-chat
```

Example Hyprland rules:

```conf
windowrulev2 = float, class:^(ollama-chat-tui)$
windowrulev2 = size 1200 800, class:^(ollama-chat-tui)$
windowrulev2 = center, class:^(ollama-chat-tui)$
windowrulev2 = opacity 0.95, class:^(ollama-chat-tui)$
bind = $mainMod, O, exec, ghostty --class=ollama-chat-tui -e ollama-chat
```

## Desktop entry example

`~/.local/share/applications/ollama-chat.desktop`

```desktop
[Desktop Entry]
Type=Application
Name=Ollama Chat
Comment=ChatGPT-style TUI for Ollama
Exec=ghostty --class=ollama-chat-tui -e ollama-chat
Icon=utilities-terminal
Terminal=false
Categories=Utility;TerminalEmulator;Development;
```

## Packaging

- Python packaging is configured in `pyproject.toml`.
- Arch packaging example is included as `PKGBUILD`.

## Testing

Run tests:

```bash
pytest -q
```

## Troubleshooting

- `Connection error`: Ensure `ollama serve` is running and `ollama.host` points to the correct endpoint.
- Startup says model is missing: keep `ollama.pull_model_on_start = true` or run `ollama pull <model>` manually.
- Empty assistant response: verify the model name exists (`ollama list`) and check Ollama logs.
- Keybind not working: confirm syntax in `[keybinds]` and restart the app.
- UI colors not applied as expected: validate hex color format (`#RRGGBB` or `#RGB`).

## Screenshot / Demo

- Screenshot placeholder: `docs/screenshot.png`
- Demo GIF placeholder: `docs/demo.gif`
