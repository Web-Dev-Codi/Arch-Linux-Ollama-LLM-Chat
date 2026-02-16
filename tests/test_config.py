"""Tests for configuration loading and validation."""

from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from ollama_chat.config import DEFAULT_CONFIG, load_config


class ConfigTests(unittest.TestCase):
    """Validate config merge and fallback behavior."""

    def test_missing_config_uses_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config = load_config(config_path=config_path)
            self.assertEqual(config["app"]["title"], DEFAULT_CONFIG["app"]["title"])
            self.assertEqual(config["ollama"]["model"], DEFAULT_CONFIG["ollama"]["model"])
            self.assertEqual(config["ollama"]["models"], DEFAULT_CONFIG["ollama"]["models"])
            self.assertEqual(config["keybinds"]["send_message"], DEFAULT_CONFIG["keybinds"]["send_message"])
            self.assertEqual(config["keybinds"]["command_palette"], DEFAULT_CONFIG["keybinds"]["command_palette"])
            self.assertEqual(config["security"]["allow_remote_hosts"], DEFAULT_CONFIG["security"]["allow_remote_hosts"])
            self.assertEqual(config["logging"]["level"], DEFAULT_CONFIG["logging"]["level"])

    def test_partial_config_overrides_selected_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                """
[ollama]
model = "qwen2.5"
models = ["qwen2.5", "llama3.2", "qwen2.5"]

[ui]
show_timestamps = false
                """.strip(),
                encoding="utf-8",
            )
            config = load_config(config_path=config_path)
            self.assertEqual(config["ollama"]["model"], "qwen2.5")
            self.assertEqual(config["ollama"]["models"], ["qwen2.5", "llama3.2"])
            self.assertFalse(config["ui"]["show_timestamps"])
            self.assertEqual(config["app"]["title"], DEFAULT_CONFIG["app"]["title"])
            self.assertEqual(config["security"]["allow_remote_hosts"], DEFAULT_CONFIG["security"]["allow_remote_hosts"])

    def test_models_fallback_to_single_model_when_models_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                """
[ollama]
model = "mistral"
                """.strip(),
                encoding="utf-8",
            )
            config = load_config(config_path=config_path)
            self.assertEqual(config["ollama"]["model"], "mistral")
            self.assertEqual(config["ollama"]["models"], ["mistral"])

    def test_invalid_values_fallback_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                """
[ollama]
timeout = -1
host = "localhost"

[ui]
background_color = "blue"
font_size = "large"

[keybinds]
send_message = ""
                """.strip(),
                encoding="utf-8",
            )
            config = load_config(config_path=config_path)
            self.assertEqual(config["ollama"]["timeout"], DEFAULT_CONFIG["ollama"]["timeout"])
            self.assertEqual(config["ollama"]["host"], DEFAULT_CONFIG["ollama"]["host"])
            self.assertEqual(config["ui"]["background_color"], DEFAULT_CONFIG["ui"]["background_color"])
            self.assertEqual(config["ui"]["font_size"], DEFAULT_CONFIG["ui"]["font_size"])
            self.assertEqual(config["keybinds"]["send_message"], DEFAULT_CONFIG["keybinds"]["send_message"])

    def test_remote_host_disallowed_by_default_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                """
[ollama]
host = "http://example.com:11434"
                """.strip(),
                encoding="utf-8",
            )
            config = load_config(config_path=config_path)
            self.assertEqual(config["ollama"]["host"], DEFAULT_CONFIG["ollama"]["host"])
            self.assertFalse(config["security"]["allow_remote_hosts"])

    def test_remote_host_allowed_when_policy_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                """
[ollama]
host = "http://example.com:11434"

[security]
allow_remote_hosts = true
allowed_hosts = ["localhost"]
                """.strip(),
                encoding="utf-8",
            )
            config = load_config(config_path=config_path)
            self.assertEqual(config["ollama"]["host"], "http://example.com:11434")
            self.assertTrue(config["security"]["allow_remote_hosts"])


if __name__ == "__main__":
    unittest.main()
