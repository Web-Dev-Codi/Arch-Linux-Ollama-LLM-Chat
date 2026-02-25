"""CLI entrypoint for OllamaTerm."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from importlib import metadata

from .app import OllamaChatApp
from .config import ensure_config_dir


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ollamaterm",
        description="OllamaTerm - Terminal chat interface for local Ollama models",
    )
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
            version = metadata.version("ollamaterm")
        except metadata.PackageNotFoundError:
            version = "0.0.0"
        print(f"ollamaterm {version}")
        return

    ensure_config_dir()
    app = OllamaChatApp()
    app.run()


if __name__ == "__main__":
    main()
