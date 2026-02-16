# Ollama Chat TUI

`ollama-chat-tui` is your local AI cockpit in the terminal: fast, private, and gloriously cloud-free.
Talk to Ollama models with a slick ChatGPT-style TUI, live streaming replies, clickable model switching, and keyboard-first controls.
Best part: once your models are pulled, you can keep chatting even when your internet is having a meltdown.

No API keys. No surprise bills. No sending your conversations to someone else's server. Just you, your machine, and your LLMs.

## Features

- Fully local LLM chat via Ollama with no cloud dependency.
- Works offline after models are pulled.
- Streaming responses with batched rendering for smooth output.
- Animated in-bubble "thinking" placeholders while responses start.
- Interactive status bar with traffic-light connection indicators.
- Clickable model picker in the status bar, plus `ctrl+m` shortcut.
- Built-in command palette shortcut (`ctrl+p`) with UI hints in header/footer.
- Multi-model config support with quick runtime model switching.
- Save/load/export conversation history (JSON and Markdown).
- Search messages and cycle results from the input box.
- Copy the latest assistant reply to clipboard in one shortcut.
- Lock-protected app state machine with cancellation-safe reset/shutdown.
- Bounded message history with deterministic context token trimming.
- Retry and backoff for resilient streaming on transient failures.
- Secure-by-default host allowlist for Ollama endpoint safety.
- Structured logging with optional file logging for debugging/ops.
- Configurable app settings, keybinds, UI, security, and logging via TOML.
- Terminal title and a best-effort window class are set by the app on startup.
- Python package with console entrypoint: `ollama-chat`.

## Requirements

- Python 3.11+
- Ollama installed and available in `PATH`
- Ollama daemon available locally (`ollama serve`)
- Internet is only needed to pull models initially; chat usage can be offline afterward

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

The app now attempts to set terminal window class on startup using `app.class` from config.
For the most reliable behavior (especially on Wayland-native terminals), still pass class in the launcher command (for example Ghostty `--class`).

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
- Window class rule not matching: keep `app.class` set, and prefer launching terminal with explicit class flag (for example `ghostty --class=ollama-chat-tui -e ollama-chat`).

## Screenshot / Demo

- Screenshot placeholder: `docs/screenshot.png`
- Demo GIF placeholder: `docs/demo.gif`
