"""Tests for schema-first custom coding tools."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ollama_chat.exceptions import OllamaToolError
from ollama_chat.tooling import ToolRegistryOptions, ToolRuntimeOptions, build_registry


class CustomToolsTests(unittest.TestCase):
    """Validate registration and core custom-tool behaviors."""

    def test_custom_tool_names_registered(self) -> None:
        registry = build_registry(
            ToolRegistryOptions(
                enable_custom_tools=True,
                # Built-in tools are enabled by default; list of names can include
                # overlap from the built-in adapter. We only require that the
                # schema-first set is a subset of the registry names.
                runtime_options=ToolRuntimeOptions(),
            )
        )
        names = set(registry.list_tool_names())
        expected_subset = {
            "apply_patch",
            "bash",
            "batch",
            "glob",
            "invalid",
            "ls",
            "multiedit",
            "plan-enter",
            "plan-exit",
            "plan",
            "question",
            "registry",
            "task",
            "todo",
            "todoread",
            "todowrite",
            "tool",
            "truncation",
            "webfetch",
            "websearch",
            "write",
        }
        self.assertTrue(expected_subset.issubset(names))

    def test_builtin_adapter_precedence_for_allowlisted_names(self) -> None:
        registry = build_registry(
            ToolRegistryOptions(
                enable_custom_tools=True,
                runtime_options=ToolRuntimeOptions(),
            )
        )
        names = set(registry.list_tool_names())
        # Ensure allowlisted built-ins are present
        for name in {"codesearch", "edit", "grep", "list", "read"}:
            self.assertIn(name, names)

    def test_write_read_edit_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = build_registry(
                ToolRegistryOptions(
                    enable_custom_tools=True,
                    runtime_options=ToolRuntimeOptions(workspace_root=str(root)),
                )
            )

            target = root / "hello.txt"
            result = registry.execute(
                "write",
                {
                    "path": str(target),
                    "content": "hello world\n",
                    "overwrite": True,
                },
            )
            self.assertIn("Wrote", result)

            read_text = registry.execute("read", {"path": str(target)})
            self.assertIn("hello world", read_text)

            registry.execute(
                "edit",
                {
                    "path": str(target),
                    "old_text": "world",
                    "new_text": "tooling",
                },
            )
            updated = target.read_text(encoding="utf-8")
            self.assertIn("hello tooling", updated)

    def test_batch_and_todo_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = build_registry(
                ToolRegistryOptions(
                    enable_custom_tools=True,
                    runtime_options=ToolRuntimeOptions(workspace_root=tmp),
                )
            )
            response = registry.execute(
                "batch",
                {
                    "calls": [
                        {"name": "todo", "arguments": {"item": "first"}},
                        {
                            "name": "todowrite",
                            "arguments": {"items": ["second"], "mode": "append"},
                        },
                        {"name": "todoread", "arguments": {}},
                    ]
                },
            )
            self.assertIn("\"ok\": true", response)
            self.assertIn("second", response)

    def test_external_directory_policy_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = build_registry(
                ToolRegistryOptions(
                    enable_custom_tools=True,
                    runtime_options=ToolRuntimeOptions(workspace_root=tmp),
                )
            )
            with self.assertRaises(OllamaToolError):
                registry.execute(
                    "external-directory",
                    {"action": "add", "path": "/tmp"},
                )

    def test_invalid_tool_raises(self) -> None:
        registry = build_registry(
            ToolRegistryOptions(
                enable_custom_tools=True,
                runtime_options=ToolRuntimeOptions(),
            )
        )
        with self.assertRaises(OllamaToolError):
            registry.execute("invalid", {})


if __name__ == "__main__":
    unittest.main()
