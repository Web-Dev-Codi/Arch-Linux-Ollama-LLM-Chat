"""CLI entrypoint for ollama-chat."""

from .app import OllamaChatApp
from .config import ensure_config_dir


def main() -> None:
    """Ensure configuration exists and run the TUI."""
    ensure_config_dir()
    app = OllamaChatApp()
    app.run()


if __name__ == "__main__":
    main()
