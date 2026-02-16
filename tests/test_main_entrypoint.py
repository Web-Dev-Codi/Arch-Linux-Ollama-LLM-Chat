"""Tests for CLI entrypoint wiring."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ollama_chat.__main__ import main


class MainEntrypointTests(unittest.TestCase):
    """Validate top-level main() behavior."""

    def test_main_ensures_config_and_runs_app(self) -> None:
        with patch("ollama_chat.__main__.ensure_config_dir") as ensure_mock, patch(
            "ollama_chat.__main__.OllamaChatApp"
        ) as app_cls_mock:
            app_instance = app_cls_mock.return_value
            main()
            ensure_mock.assert_called_once()
            app_cls_mock.assert_called_once()
            app_instance.run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
