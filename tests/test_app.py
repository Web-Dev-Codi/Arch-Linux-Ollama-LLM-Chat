"""Tests for app-level binding configuration behavior."""

from __future__ import annotations

import unittest

from ollama_chat.config import DEFAULT_CONFIG

try:
    from ollama_chat.app import OllamaChatApp
except ModuleNotFoundError:
    OllamaChatApp = None  # type: ignore[assignment]


@unittest.skipIf(OllamaChatApp is None, "textual is not installed")
class AppBindingTests(unittest.TestCase):
    """Validate binding derivation from config."""

    def test_binding_specs_created_from_keybinds(self) -> None:
        config = {
            **DEFAULT_CONFIG,
            "keybinds": {
                **DEFAULT_CONFIG["keybinds"],
            },
        }
        bindings = OllamaChatApp._binding_specs_from_config(config)  # type: ignore[union-attr]
        self.assertEqual(len(bindings), len(OllamaChatApp.KEY_TO_ACTION))  # type: ignore[union-attr]
        self.assertEqual(bindings[0].action, "send_message")
        self.assertEqual(bindings[0].key, "ctrl+enter")

    def test_blank_keybind_is_not_registered(self) -> None:
        config = {
            **DEFAULT_CONFIG,
            "keybinds": {
                **DEFAULT_CONFIG["keybinds"],
                "toggle_model_picker": " ",
            },
        }
        bindings = OllamaChatApp._binding_specs_from_config(config)  # type: ignore[union-attr]
        actions = {binding.action for binding in bindings}
        self.assertNotIn("toggle_model_picker", actions)


if __name__ == "__main__":
    unittest.main()
