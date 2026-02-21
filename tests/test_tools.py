"""Tests for the ToolRegistry."""

from __future__ import annotations

import unittest

from ollama_chat.exceptions import OllamaToolError
from ollama_chat.tools import ToolRegistry, build_default_registry


def _add(a: int, b: int) -> int:
    """Add two integers.

    Args:
        a: First integer.
        b: Second integer.

    Returns:
        The sum.
    """
    return a + b


def _failing_tool(x: str) -> str:
    """A tool that always raises.

    Args:
        x: Input string.

    Returns:
        Never returns.
    """
    raise ValueError(f"bad input: {x}")


class ToolRegistryTests(unittest.TestCase):
    """Unit tests for ToolRegistry."""

    def test_register_and_build_tools_list(self) -> None:
        registry = ToolRegistry()
        registry.register(_add)
        tools = registry.build_tools_list()
        self.assertEqual(len(tools), 1)
        self.assertIs(tools[0], _add)

    def test_execute_known_tool_returns_string(self) -> None:
        registry = ToolRegistry()
        registry.register(_add)
        result = registry.execute("_add", {"a": 3, "b": 4})
        self.assertEqual(result, "7")

    def test_execute_unknown_tool_raises(self) -> None:
        registry = ToolRegistry()
        with self.assertRaises(OllamaToolError) as ctx:
            registry.execute("nonexistent", {})
        self.assertIn("nonexistent", str(ctx.exception))

    def test_execute_tool_exception_wrapped_as_tool_error(self) -> None:
        registry = ToolRegistry()
        registry.register(_failing_tool)
        with self.assertRaises(OllamaToolError) as ctx:
            registry.execute("_failing_tool", {"x": "oops"})
        self.assertIn("_failing_tool", str(ctx.exception))

    def test_is_empty_true_when_no_tools(self) -> None:
        registry = ToolRegistry()
        self.assertTrue(registry.is_empty)

    def test_is_empty_false_after_register(self) -> None:
        registry = ToolRegistry()
        registry.register(_add)
        self.assertFalse(registry.is_empty)

    def test_build_default_registry_empty_when_web_search_disabled(self) -> None:
        registry = build_default_registry(web_search_enabled=False)
        self.assertTrue(registry.is_empty)

    def test_build_default_registry_registers_web_tools_when_enabled(self) -> None:
        registry = build_default_registry(
            web_search_enabled=True, web_search_api_key="test-key"
        )
        tools = registry.build_tools_list()
        tool_names = [fn.__name__ for fn in tools]
        # Inner factory functions are named _web_search_tool / _web_fetch_tool.
        self.assertTrue(any("web_search" in n for n in tool_names))
        self.assertTrue(any("web_fetch" in n for n in tool_names))

    def test_build_default_registry_raises_without_api_key(self) -> None:
        from ollama_chat.exceptions import OllamaToolError

        # Ensure OLLAMA_API_KEY is not set for this test.
        import os

        old = os.environ.pop("OLLAMA_API_KEY", None)
        try:
            with self.assertRaises(OllamaToolError):
                build_default_registry(web_search_enabled=True, web_search_api_key="")
        finally:
            if old is not None:
                os.environ["OLLAMA_API_KEY"] = old

    def test_multiple_registrations_do_not_duplicate(self) -> None:
        registry = ToolRegistry()
        registry.register(_add)
        registry.register(_add)
        # Second registration overwrites the first (same name key).
        self.assertEqual(len(registry.build_tools_list()), 1)


if __name__ == "__main__":
    unittest.main()
