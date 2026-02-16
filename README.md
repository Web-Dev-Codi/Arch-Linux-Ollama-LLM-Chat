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
- Ollama daemon available locally

## Installation

### Development install

```bash
pip install -e .
```

### Run

```bash
ollama-chat
```

or

```bash
python -m ollama_chat
```

## Ollama setup

Start Ollama and ensure the selected model is available:

```bash
ollama serve
ollama pull llama3.2
```

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
timeout = 120
system_prompt = "You are a helpful assistant."
max_history_messages = 200
max_context_tokens = 4096

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
- `ctrl+m`: Cycle available models
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
python -m unittest discover -s tests -p 'test_*.py'
```

## Troubleshooting

- `Connection error`: Ensure `ollama serve` is running and `ollama.host` points to the correct endpoint.
- Empty assistant response: verify the model name exists (`ollama list`) and check Ollama logs.
- Keybind not working: confirm syntax in `[keybinds]` and restart the app.
- UI colors not applied as expected: validate hex color format (`#RRGGBB` or `#RGB`).

## Screenshot / Demo

- Screenshot placeholder: `docs/screenshot.png`
- Demo GIF placeholder: `docs/demo.gif`
