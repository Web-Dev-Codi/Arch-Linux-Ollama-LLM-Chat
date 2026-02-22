"""CLI entrypoint for ollama-chat."""

from __future__ import annotations

import argparse
from importlib import metadata
from typing import Sequence

from .app import OllamaChatApp
from .config import ensure_config_dir


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ollama-chat", description="Ollama Chat TUI")
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Ensure configuration exists, handle CLI flags, and run the TUI."""

    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.version:
        try:
            version = metadata.version("ollama-chat-tui")
        except metadata.PackageNotFoundError:
            version = "0.0.0"
        print(f"ollama-chat {version}")
        return

    ensure_config_dir()
    app = OllamaChatApp()
    app.run()


if __name__ == "__main__":
    main()
