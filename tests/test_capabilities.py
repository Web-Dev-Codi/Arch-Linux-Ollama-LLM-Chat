"""Tests for CapabilityContext, SearchState, and AttachmentState dataclasses."""

from __future__ import annotations

import unittest

from ollama_chat.capabilities import AttachmentState, CapabilityContext, SearchState


class CapabilityContextTests(unittest.TestCase):
    """Validate CapabilityContext.from_config() and safe defaults."""

    def test_from_config_maps_all_keys(self) -> None:
        """Only the user-preference fields are read from config; auto-detected
        fields (think, tools_enabled, vision_enabled) always start True."""
        config = {
            "capabilities": {
                # These were removed from config — they must be ignored.
                "think": False,
                "tools_enabled": False,
                "vision_enabled": False,
                # These are still configurable.
                "show_thinking": False,
                "web_search_enabled": True,
                "web_search_api_key": "sk-test-123",
                "max_tool_iterations": 5,
            }
        }
        ctx = CapabilityContext.from_config(config)
        # Auto-detected fields are always permissive (True) after from_config().
        self.assertTrue(ctx.think)
        self.assertTrue(ctx.tools_enabled)
        self.assertTrue(ctx.vision_enabled)
        # User-preference fields come from config.
        self.assertFalse(ctx.show_thinking)
        self.assertTrue(ctx.web_search_enabled)
        self.assertEqual(ctx.web_search_api_key, "sk-test-123")
        self.assertEqual(ctx.max_tool_iterations, 5)

    def test_defaults_when_config_keys_absent(self) -> None:
        ctx = CapabilityContext.from_config({})
        # Auto-detected fields default to True (permissive).
        self.assertTrue(ctx.think)
        self.assertTrue(ctx.tools_enabled)
        self.assertTrue(ctx.vision_enabled)
        # User-preference fields use their own defaults.
        self.assertTrue(ctx.show_thinking)
        self.assertFalse(ctx.web_search_enabled)
        self.assertEqual(ctx.web_search_api_key, "")
        self.assertEqual(ctx.max_tool_iterations, 10)

    def test_defaults_with_empty_capabilities_section(self) -> None:
        ctx = CapabilityContext.from_config({"capabilities": {}})
        self.assertTrue(ctx.think)
        self.assertTrue(ctx.vision_enabled)
        self.assertEqual(ctx.max_tool_iterations, 10)

    def test_partial_config_uses_defaults_for_missing(self) -> None:
        """Supplying only some configurable fields leaves others at their defaults."""
        config = {"capabilities": {"show_thinking": False, "max_tool_iterations": 3}}
        ctx = CapabilityContext.from_config(config)
        # Auto-detected fields: always True from from_config().
        self.assertTrue(ctx.think)
        self.assertTrue(ctx.vision_enabled)
        self.assertTrue(ctx.tools_enabled)
        # Configured fields.
        self.assertFalse(ctx.show_thinking)
        self.assertEqual(ctx.max_tool_iterations, 3)
        # Unconfigured fields use defaults.
        self.assertFalse(ctx.web_search_enabled)
        self.assertEqual(ctx.web_search_api_key, "")


class SearchStateTests(unittest.TestCase):
    """Validate SearchState navigation helpers."""

    def test_initial_state(self) -> None:
        s = SearchState()
        self.assertEqual(s.query, "")
        self.assertEqual(s.results, [])
        self.assertEqual(s.position, -1)
        self.assertFalse(s.has_results())

    def test_reset_clears_all(self) -> None:
        s = SearchState(query="hello", results=[1, 2, 3], position=1)
        s.reset()
        self.assertEqual(s.query, "")
        self.assertEqual(s.results, [])
        self.assertEqual(s.position, -1)

    def test_advance_wraps_around(self) -> None:
        s = SearchState(query="test", results=[10, 20, 30], position=-1)
        self.assertEqual(s.advance(), 10)
        self.assertEqual(s.position, 0)
        self.assertEqual(s.advance(), 20)
        self.assertEqual(s.position, 1)
        self.assertEqual(s.advance(), 30)
        self.assertEqual(s.position, 2)
        self.assertEqual(s.advance(), 10)
        self.assertEqual(s.position, 0)

    def test_advance_returns_negative_one_when_empty(self) -> None:
        s = SearchState()
        self.assertEqual(s.advance(), -1)

    def test_has_results(self) -> None:
        s = SearchState(results=[5])
        self.assertTrue(s.has_results())


class AttachmentStateTests(unittest.TestCase):
    """Validate AttachmentState helpers."""

    def test_add_image_and_file(self) -> None:
        a = AttachmentState()
        a.add_image("/tmp/cat.png")
        a.add_file("/tmp/readme.md")
        self.assertEqual(a.images, ["/tmp/cat.png"])
        self.assertEqual(a.files, ["/tmp/readme.md"])
        self.assertTrue(a.has_any())

    def test_clear(self) -> None:
        a = AttachmentState(images=["/a.png"], files=["/b.txt"])
        a.clear()
        self.assertEqual(a.images, [])
        self.assertEqual(a.files, [])
        self.assertFalse(a.has_any())

    def test_has_any_false_when_empty(self) -> None:
        a = AttachmentState()
        self.assertFalse(a.has_any())


if __name__ == "__main__":
    unittest.main()
