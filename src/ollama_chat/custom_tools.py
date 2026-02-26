"""Schema-first custom coding tools for Ollama function calling."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import fnmatch
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from .exceptions import OllamaToolError

_SEARCH_SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
}


@dataclass(frozen=True)
class ToolRuntimeOptions:
    """Runtime limits and safety controls for local tools."""

    enabled: bool = True
    workspace_root: str = "."
    allow_external_directories: bool = False
    command_timeout_seconds: int = 30
    max_output_lines: int = 200
    max_output_bytes: int = 50_000
    max_read_bytes: int = 200_000
    max_search_results: int = 200
    default_external_directories: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolSpec:
    """JSON-schema function tool definition + handler."""

    name: str
    description: str
    parameters_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], str]
    safety_level: str = "safe"
    category: str = "meta"

    def as_ollama_tool(self) -> dict[str, Any]:
        """Render the tool in Ollama's function schema format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


@dataclass
class _ToolState:
    """Session-local mutable state for plan/todo/task tools."""

    allowed_external_roots: set[Path] = field(default_factory=set)
    plan_mode: bool = False
    plan_content: str = ""
    todos: list[str] = field(default_factory=list)
    tasks: dict[str, str] = field(default_factory=dict)


class CustomToolSuite:
    """Factory for schema-first custom coding tools."""

    def __init__(
        self,
        runtime_options: ToolRuntimeOptions,
        web_search_fn: Callable[[str, int], str] | None = None,
        web_fetch_fn: Callable[[str], str] | None = None,
    ) -> None:
        self._runtime_options = runtime_options
        root = (runtime_options.workspace_root or ".").strip() or "."
        self._workspace_root = Path(os.path.expanduser(root)).resolve()
        self._state = _ToolState()
        self._default_external_roots: set[Path] = set()
        for entry in runtime_options.default_external_directories:
            try:
                self._default_external_roots.add(
                    Path(os.path.expanduser(entry)).resolve()
                )
            except Exception:
                continue

        self._web_search_fn = web_search_fn
        self._web_fetch_fn = web_fetch_fn
        self._executor: Callable[[str, dict[str, Any]], str] | None = None
        self._specs: dict[str, ToolSpec] = {}
        self._build_specs()

    def bind_executor(self, executor: Callable[[str, dict[str, Any]], str]) -> None:
        """Provide an executor callback used by the batch tool."""
        self._executor = executor

    def specs(self) -> list[ToolSpec]:
        """Return all custom tool specs."""
        return list(self._specs.values())

    def get_spec(self, name: str) -> ToolSpec | None:
        """Return one spec by name."""
        return self._specs.get(name)

    @staticmethod
    def _object_schema(
        properties: dict[str, Any],
        required: list[str] | None = None,
        *,
        additional_properties: bool = False,
    ) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": additional_properties,
        }

    def _register(self, spec: ToolSpec) -> None:
        self._specs[spec.name] = spec

    def _build_specs(self) -> None:
        self._register(
            ToolSpec(
                name="read",
                description=(
                    "Read file contents from workspace with optional line window."
                ),
                parameters_schema=self._object_schema(
                    {
                        "path": {
                            "type": "string",
                            "description": "Absolute or workspace-relative path.",
                        },
                        "offset": {
                            "type": "integer",
                            "description": "1-indexed starting line number.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max number of lines to return.",
                        },
                    },
                    required=["path"],
                ),
                handler=self._handle_read,
                category="fs",
            )
        )

        self._register(
            ToolSpec(
                name="ls",
                description="List files and directories.",
                parameters_schema=self._object_schema(
                    {
                        "path": {
                            "type": "string",
                            "description": "Directory path (default workspace root).",
                        },
                        "max_entries": {
                            "type": "integer",
                            "description": "Maximum entries to return.",
                        },
                    }
                ),
                handler=self._handle_ls,
                category="fs",
            )
        )

        self._register(
            ToolSpec(
                name="glob",
                description="Find files by glob pattern.",
                parameters_schema=self._object_schema(
                    {
                        "pattern": {
                            "type": "string",
                            "description": "Glob pattern, e.g. **/*.py",
                        },
                        "path": {
                            "type": "string",
                            "description": "Base path (default workspace root).",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of matches.",
                        },
                    },
                    required=["pattern"],
                ),
                handler=self._handle_glob,
                category="search",
            )
        )

        grep_schema = self._object_schema(
            {
                "query": {
                    "type": "string",
                    "description": "Regex or literal text query.",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory path.",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Case-sensitive search.",
                },
                "fixed_strings": {
                    "type": "boolean",
                    "description": "Treat query as literal text.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum matching lines.",
                },
            },
            required=["query"],
        )
        self._register(
            ToolSpec(
                name="grep",
                description="Search file content and return matching lines.",
                parameters_schema=grep_schema,
                handler=self._handle_grep,
                category="search",
            )
        )
        self._register(
            ToolSpec(
                name="codesearch",
                description="Code search alias for grep.",
                parameters_schema=grep_schema,
                handler=self._handle_grep,
                category="search",
            )
        )

        self._register(
            ToolSpec(
                name="write",
                description="Write full file content atomically.",
                parameters_schema=self._object_schema(
                    {
                        "path": {
                            "type": "string",
                            "description": "Target file path.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Complete file content.",
                        },
                        "overwrite": {
                            "type": "boolean",
                            "description": "Allow overwrite of existing file.",
                        },
                        "create_dirs": {
                            "type": "boolean",
                            "description": "Create parent directories if missing.",
                        },
                    },
                    required=["path", "content"],
                ),
                handler=self._handle_write,
                safety_level="confirm",
                category="edit",
            )
        )

        edit_schema = self._object_schema(
            {
                "path": {
                    "type": "string",
                    "description": "Target file path.",
                },
                "old_text": {
                    "type": "string",
                    "description": "Text to replace.",
                },
                "new_text": {
                    "type": "string",
                    "description": "Replacement text.",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences.",
                },
            },
            required=["path", "old_text", "new_text"],
        )
        self._register(
            ToolSpec(
                name="edit",
                description="Replace a snippet in a file.",
                parameters_schema=edit_schema,
                handler=self._handle_edit,
                safety_level="confirm",
                category="edit",
            )
        )

        array_edit_item = self._object_schema(
            {
                "old_text": {
                    "type": "string",
                    "description": "Text to replace.",
                },
                "new_text": {
                    "type": "string",
                    "description": "Replacement text.",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences.",
                },
            },
            required=["old_text", "new_text"],
        )
        self._register(
            ToolSpec(
                name="multiedit",
                description="Apply multiple snippet edits atomically.",
                parameters_schema=self._object_schema(
                    {
                        "path": {
                            "type": "string",
                            "description": "Target file path.",
                        },
                        "edits": {
                            "type": "array",
                            "description": "Ordered edit operations.",
                            "items": array_edit_item,
                        },
                    },
                    required=["path", "edits"],
                ),
                handler=self._handle_multiedit,
                safety_level="confirm",
                category="edit",
            )
        )

        self._register(
            ToolSpec(
                name="apply_patch",
                description=(
                    "Apply structured patch hunks (old_text/new_text) to a file."
                ),
                parameters_schema=self._object_schema(
                    {
                        "path": {
                            "type": "string",
                            "description": "Target file path.",
                        },
                        "hunks": {
                            "type": "array",
                            "description": "Patch hunks.",
                            "items": array_edit_item,
                        },
                    },
                    required=["path", "hunks"],
                ),
                handler=self._handle_apply_patch,
                safety_level="confirm",
                category="edit",
            )
        )

        self._register(
            ToolSpec(
                name="bash",
                description="Run a shell command with timeout and output caps.",
                parameters_schema=self._object_schema(
                    {
                        "command": {
                            "type": "string",
                            "description": "Shell command.",
                        },
                        "cwd": {
                            "type": "string",
                            "description": "Optional working directory.",
                        },
                    },
                    required=["command"],
                ),
                handler=self._handle_bash,
                safety_level="confirm",
                category="shell",
            )
        )

        self._register(
            ToolSpec(
                name="batch",
                description="Run a sequence of tool calls in one invocation.",
                parameters_schema=self._object_schema(
                    {
                        "calls": {
                            "type": "array",
                            "description": "Array of tool call objects.",
                            "items": self._object_schema(
                                {
                                    "name": {
                                        "type": "string",
                                        "description": "Tool name.",
                                    },
                                    "arguments": {
                                        "type": "object",
                                        "description": "Arguments object.",
                                        "additionalProperties": True,
                                    },
                                },
                                required=["name", "arguments"],
                                additional_properties=False,
                            ),
                        },
                        "continue_on_error": {
                            "type": "boolean",
                            "description": "Continue after errors.",
                        },
                    },
                    required=["calls"],
                ),
                handler=self._handle_batch,
                category="meta",
            )
        )

        self._register(
            ToolSpec(
                name="external-directory",
                description="Manage external directory allowlist for this session.",
                parameters_schema=self._object_schema(
                    {
                        "action": {
                            "type": "string",
                            "description": "add, remove, or list.",
                        },
                        "path": {
                            "type": "string",
                            "description": "Directory path for add/remove.",
                        },
                    }
                ),
                handler=self._handle_external_directory,
                safety_level="confirm",
                category="fs",
            )
        )

        self._register(
            ToolSpec(
                name="registry",
                description="List available tools and metadata.",
                parameters_schema=self._object_schema({}),
                handler=self._handle_registry,
                category="meta",
            )
        )
        self._register(
            ToolSpec(
                name="tool",
                description="Inspect a tool definition by name.",
                parameters_schema=self._object_schema(
                    {
                        "name": {
                            "type": "string",
                            "description": "Tool name.",
                        }
                    },
                    required=["name"],
                ),
                handler=self._handle_tool,
                category="meta",
            )
        )
        self._register(
            ToolSpec(
                name="invalid",
                description="Intentionally fail for debugging tool error handling.",
                parameters_schema=self._object_schema({}),
                handler=self._handle_invalid,
                category="meta",
            )
        )
        self._register(
            ToolSpec(
                name="truncation",
                description="Show current output truncation limits.",
                parameters_schema=self._object_schema({}),
                handler=self._handle_truncation,
                category="meta",
            )
        )

        self._register(
            ToolSpec(
                name="plan-enter",
                description="Enter planning mode and optionally set a plan goal.",
                parameters_schema=self._object_schema(
                    {
                        "goal": {
                            "type": "string",
                            "description": "Optional initial plan text.",
                        }
                    }
                ),
                handler=self._handle_plan_enter,
                category="planning",
            )
        )
        self._register(
            ToolSpec(
                name="plan-exit",
                description="Exit planning mode.",
                parameters_schema=self._object_schema({}),
                handler=self._handle_plan_exit,
                category="planning",
            )
        )
        self._register(
            ToolSpec(
                name="plan",
                description="Get/set/append/clear the current plan content.",
                parameters_schema=self._object_schema(
                    {
                        "action": {
                            "type": "string",
                            "description": "get, set, append, or clear.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Content for set/append.",
                        },
                    }
                ),
                handler=self._handle_plan,
                category="planning",
            )
        )
        self._register(
            ToolSpec(
                name="question",
                description="Emit a structured clarification question.",
                parameters_schema=self._object_schema(
                    {
                        "prompt": {
                            "type": "string",
                            "description": "Question text.",
                        },
                        "context": {
                            "type": "string",
                            "description": "Optional context.",
                        },
                    },
                    required=["prompt"],
                ),
                handler=self._handle_question,
                category="planning",
            )
        )

        self._register(
            ToolSpec(
                name="todo",
                description="Add one todo item.",
                parameters_schema=self._object_schema(
                    {
                        "item": {
                            "type": "string",
                            "description": "Todo item text.",
                        }
                    },
                    required=["item"],
                ),
                handler=self._handle_todo,
                category="task",
            )
        )
        self._register(
            ToolSpec(
                name="todoread",
                description="Read the current todo list.",
                parameters_schema=self._object_schema({}),
                handler=self._handle_todoread,
                category="task",
            )
        )
        self._register(
            ToolSpec(
                name="todowrite",
                description="Replace or append todo items.",
                parameters_schema=self._object_schema(
                    {
                        "items": {
                            "type": "array",
                            "description": "Todo item strings.",
                            "items": {
                                "type": "string",
                                "description": "Todo item.",
                            },
                        },
                        "mode": {
                            "type": "string",
                            "description": "replace or append.",
                        },
                    },
                    required=["items"],
                ),
                handler=self._handle_todowrite,
                category="task",
            )
        )
        self._register(
            ToolSpec(
                name="task",
                description="Set/get/list named task statuses.",
                parameters_schema=self._object_schema(
                    {
                        "action": {
                            "type": "string",
                            "description": "set, get, or list.",
                        },
                        "name": {
                            "type": "string",
                            "description": "Task name.",
                        },
                        "status": {
                            "type": "string",
                            "description": "Task status for set action.",
                        },
                    }
                ),
                handler=self._handle_task,
                category="task",
            )
        )

        self._register(
            ToolSpec(
                name="lsp",
                description="Language-server tool stub (not configured).",
                parameters_schema=self._object_schema(
                    {
                        "action": {
                            "type": "string",
                            "description": "Requested LSP action.",
                        },
                        "path": {
                            "type": "string",
                            "description": "Target path.",
                        },
                        "symbol": {
                            "type": "string",
                            "description": "Optional symbol.",
                        },
                    }
                ),
                handler=self._handle_lsp,
                category="meta",
            )
        )
        self._register(
            ToolSpec(
                name="skill",
                description="Skill invocation tool stub.",
                parameters_schema=self._object_schema(
                    {
                        "name": {
                            "type": "string",
                            "description": "Skill name.",
                        },
                        "input": {
                            "type": "string",
                            "description": "Skill input.",
                        },
                    }
                ),
                handler=self._handle_skill,
                category="meta",
            )
        )
        self._register(
            ToolSpec(
                name="websearch",
                description="Search the web using Ollama web_search integration.",
                parameters_schema=self._object_schema(
                    {
                        "query": {
                            "type": "string",
                            "description": "Search query.",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results.",
                        },
                    },
                    required=["query"],
                ),
                handler=self._handle_websearch,
                category="web",
            )
        )
        self._register(
            ToolSpec(
                name="webfetch",
                description="Fetch a URL using Ollama web_fetch integration.",
                parameters_schema=self._object_schema(
                    {
                        "url": {
                            "type": "string",
                            "description": "URL to fetch.",
                        }
                    },
                    required=["url"],
                ),
                handler=self._handle_webfetch,
                category="web",
            )
        )

    @staticmethod
    def _to_json(value: Any) -> str:
        return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)

    def _resolve_any_path(self, path_text: str) -> Path:
        expanded = os.path.expanduser(path_text)
        candidate = Path(expanded)
        if not candidate.is_absolute():
            candidate = self._workspace_root / candidate
        return candidate.resolve()

    def _allowed_roots(self) -> set[Path]:
        roots = {self._workspace_root}
        roots.update(self._default_external_roots)
        if self._runtime_options.allow_external_directories:
            roots.update(self._state.allowed_external_roots)
        return roots

    def _is_path_allowed(self, path: Path) -> bool:
        for root in self._allowed_roots():
            if path == root or root in path.parents:
                return True
        return False

    def _resolve_path(self, path_text: str, *, must_exist: bool = False) -> Path:
        resolved = self._resolve_any_path(path_text)
        if not self._is_path_allowed(resolved):
            raise OllamaToolError(
                f"Path {str(resolved)!r} is outside allowed workspace roots."
            )
        if must_exist and not resolved.exists():
            raise OllamaToolError(f"Path does not exist: {str(resolved)!r}")
        return resolved

    def _atomic_write(self, path: Path, content: str) -> None:
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(parent),
            delete=False,
        ) as temp_file:
            temp_file.write(content)
            temp_name = temp_file.name
        Path(temp_name).replace(path)

    def _handle_read(self, args: dict[str, Any]) -> str:
        path = self._resolve_path(str(args["path"]), must_exist=True)
        if path.is_dir():
            raise OllamaToolError("read expects a file path.")

        raw = path.read_bytes()
        if len(raw) > self._runtime_options.max_read_bytes:
            raw = raw[: self._runtime_options.max_read_bytes]
        text = raw.decode("utf-8", errors="ignore")

        offset = int(args.get("offset", 1))
        limit = int(args.get("limit", 200))
        offset = max(1, offset)
        limit = max(1, limit)

        lines = text.splitlines()
        start = offset - 1
        end = start + limit
        output: list[str] = []
        for idx, line in enumerate(lines[start:end], start=offset):
            output.append(f"{idx:>6}\t{line}")
        return "\n".join(output)

    def _handle_ls(self, args: dict[str, Any]) -> str:
        target = self._resolve_path(str(args.get("path", ".")), must_exist=True)
        if not target.is_dir():
            raise OllamaToolError("ls expects a directory path.")

        max_entries = max(1, int(args.get("max_entries", 200)))
        entries = sorted(target.iterdir(), key=lambda p: p.name.lower())
        lines: list[str] = []
        for entry in entries[:max_entries]:
            if entry.is_dir():
                lines.append(f"[dir ] {entry.name}/")
            else:
                lines.append(f"[file] {entry.name} ({entry.stat().st_size} bytes)")
        if len(entries) > max_entries:
            lines.append(f"... {len(entries) - max_entries} more entries")
        return "\n".join(lines)

    def _handle_glob(self, args: dict[str, Any]) -> str:
        base = self._resolve_path(str(args.get("path", ".")), must_exist=True)
        if not base.is_dir():
            raise OllamaToolError("glob path must be a directory.")
        pattern = str(args["pattern"])
        max_results = max(
            1,
            int(args.get("max_results", self._runtime_options.max_search_results)),
        )

        found: list[str] = []
        for root, dir_names, file_names in os.walk(base):
            dir_names[:] = [d for d in dir_names if d not in _SEARCH_SKIP_DIR_NAMES]
            root_path = Path(root)
            for name in sorted(file_names + dir_names):
                full = root_path / name
                rel = str(full.relative_to(base))
                if fnmatch.fnmatch(rel, pattern):
                    prefix = "dir" if full.is_dir() else "file"
                    found.append(f"{prefix}: {rel}")
                    if len(found) >= max_results:
                        return "\n".join(found)
        if not found:
            return "No matches found."
        return "\n".join(found)

    def _iter_search_files(self, target: Path) -> list[Path]:
        if target.is_file():
            return [target]

        files: list[Path] = []
        for root, dir_names, file_names in os.walk(target):
            dir_names[:] = [d for d in dir_names if d not in _SEARCH_SKIP_DIR_NAMES]
            root_path = Path(root)
            for file_name in file_names:
                files.append(root_path / file_name)
        return files

    def _handle_grep(self, args: dict[str, Any]) -> str:
        query = str(args["query"])
        case_sensitive = bool(args.get("case_sensitive", False))
        fixed_strings = bool(args.get("fixed_strings", False))
        max_results = max(
            1,
            int(args.get("max_results", self._runtime_options.max_search_results)),
        )

        target = self._resolve_path(str(args.get("path", ".")), must_exist=True)

        flags = 0 if case_sensitive else re.IGNORECASE
        if fixed_strings:
            pattern = re.compile(re.escape(query), flags)
        else:
            try:
                pattern = re.compile(query, flags)
            except re.error as exc:
                raise OllamaToolError(f"Invalid regex: {exc}") from exc

        matches: list[str] = []
        for file_path in self._iter_search_files(target):
            if len(matches) >= max_results:
                break
            try:
                if file_path.stat().st_size > self._runtime_options.max_read_bytes:
                    continue
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            try:
                rel = file_path.relative_to(self._workspace_root)
            except ValueError:
                rel = file_path
            for line_no, line in enumerate(content.splitlines(), start=1):
                if pattern.search(line):
                    matches.append(f"{str(rel)}:{line_no}:{line}")
                    if len(matches) >= max_results:
                        break

        if not matches:
            return "No matches found."
        return "\n".join(matches)

    def _apply_edits(self, content: str, edits: list[dict[str, Any]]) -> str:
        updated = content
        for edit in edits:
            old_text = str(edit["old_text"])
            new_text = str(edit["new_text"])
            replace_all = bool(edit.get("replace_all", False))
            if old_text not in updated:
                raise OllamaToolError("Edit failed: old_text not found.")
            if replace_all:
                updated = updated.replace(old_text, new_text)
            else:
                updated = updated.replace(old_text, new_text, 1)
        return updated

    def _handle_write(self, args: dict[str, Any]) -> str:
        path = self._resolve_path(str(args["path"]))
        overwrite = bool(args.get("overwrite", True))
        create_dirs = bool(args.get("create_dirs", True))

        if path.exists() and not overwrite:
            raise OllamaToolError(f"Refusing to overwrite existing file: {str(path)!r}")
        if not path.parent.exists() and not create_dirs:
            raise OllamaToolError("Parent directory missing and create_dirs is false.")

        content = str(args["content"])
        self._atomic_write(path, content)
        return f"Wrote {len(content.encode('utf-8'))} bytes to {str(path)}"

    def _handle_edit(self, args: dict[str, Any]) -> str:
        path = self._resolve_path(str(args["path"]), must_exist=True)
        content = path.read_text(encoding="utf-8", errors="ignore")
        updated = self._apply_edits(
            content,
            [
                {
                    "old_text": str(args["old_text"]),
                    "new_text": str(args["new_text"]),
                    "replace_all": bool(args.get("replace_all", False)),
                }
            ],
        )
        self._atomic_write(path, updated)
        return f"Edited file: {str(path)}"

    def _handle_multiedit(self, args: dict[str, Any]) -> str:
        path = self._resolve_path(str(args["path"]), must_exist=True)
        edits = args.get("edits", [])
        if not isinstance(edits, list) or not edits:
            raise OllamaToolError("multiedit requires a non-empty edits list.")

        content = path.read_text(encoding="utf-8", errors="ignore")
        updated = self._apply_edits(content, edits)
        self._atomic_write(path, updated)
        return f"Applied {len(edits)} edit(s) to {str(path)}"

    def _handle_apply_patch(self, args: dict[str, Any]) -> str:
        path = self._resolve_path(str(args["path"]), must_exist=True)
        hunks = args.get("hunks", [])
        if not isinstance(hunks, list) or not hunks:
            raise OllamaToolError("apply_patch requires a non-empty hunks list.")

        content = path.read_text(encoding="utf-8", errors="ignore")
        updated = self._apply_edits(content, hunks)
        self._atomic_write(path, updated)
        return f"Applied {len(hunks)} hunk(s) to {str(path)}"

    def _handle_bash(self, args: dict[str, Any]) -> str:
        command = str(args["command"]).strip()
        if not command:
            raise OllamaToolError("bash command must not be empty.")

        cwd = str(args.get("cwd", ".")).strip() or "."
        cwd_path = self._resolve_path(cwd, must_exist=True)
        if not cwd_path.is_dir():
            raise OllamaToolError("bash cwd must be a directory.")

        try:
            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(cwd_path),
                timeout=max(1, int(self._runtime_options.command_timeout_seconds)),
            )
        except subprocess.TimeoutExpired as exc:
            raise OllamaToolError(f"bash timed out after {exc.timeout}s") from exc

        output = (completed.stdout or "") + (completed.stderr or "")
        header = f"exit_code={completed.returncode} cwd={str(cwd_path)}"
        if output.strip():
            return f"{header}\n{output}"
        return header

    def _handle_batch(self, args: dict[str, Any]) -> str:
        calls = args.get("calls", [])
        if not isinstance(calls, list) or not calls:
            raise OllamaToolError("batch requires a non-empty calls list.")
        if self._executor is None:
            raise OllamaToolError("batch executor is not configured.")

        continue_on_error = bool(args.get("continue_on_error", True))
        rows: list[dict[str, Any]] = []
        for index, call in enumerate(calls):
            if not isinstance(call, dict):
                raise OllamaToolError(f"batch call index {index} must be an object.")
            name = str(call.get("name", "")).strip()
            call_args = call.get("arguments", {})
            if not name:
                raise OllamaToolError(f"batch call index {index} missing tool name.")
            if not isinstance(call_args, dict):
                raise OllamaToolError(
                    f"batch call index {index} arguments must be object."
                )
            if name == "batch":
                raise OllamaToolError("batch cannot call itself recursively.")

            try:
                result = self._executor(name, call_args)
                rows.append({"index": index, "name": name, "ok": True, "result": result})
            except OllamaToolError as exc:
                rows.append(
                    {
                        "index": index,
                        "name": name,
                        "ok": False,
                        "error": str(exc),
                    }
                )
                if not continue_on_error:
                    break
        return self._to_json(rows)

    def _handle_external_directory(self, args: dict[str, Any]) -> str:
        if not self._runtime_options.allow_external_directories:
            raise OllamaToolError(
                "external-directory is disabled by policy. "
                "Enable tools.allow_external_directories."
            )

        action = str(args.get("action", "list")).strip().lower() or "list"
        if action == "list":
            roots = sorted(str(path) for path in self._state.allowed_external_roots)
            if not roots:
                return "No external directories configured."
            return "\n".join(roots)

        path_text = str(args.get("path", "")).strip()
        if not path_text:
            raise OllamaToolError("external-directory add/remove requires a path.")
        path = self._resolve_any_path(path_text)

        if action == "add":
            if not path.exists() or not path.is_dir():
                raise OllamaToolError("Path must exist and be a directory.")
            self._state.allowed_external_roots.add(path)
            return f"Added external directory: {str(path)}"

        if action == "remove":
            self._state.allowed_external_roots.discard(path)
            return f"Removed external directory: {str(path)}"

        raise OllamaToolError("external-directory action must be add, remove, or list.")

    def _handle_registry(self, _args: dict[str, Any]) -> str:
        rows = []
        for spec in self._specs.values():
            rows.append(
                {
                    "name": spec.name,
                    "category": spec.category,
                    "safety_level": spec.safety_level,
                    "description": spec.description,
                }
            )
        rows.sort(key=lambda item: str(item["name"]))
        return self._to_json(rows)

    def _handle_tool(self, args: dict[str, Any]) -> str:
        name = str(args["name"])
        spec = self._specs.get(name)
        if spec is None:
            raise OllamaToolError(f"Unknown tool {name!r}")
        return self._to_json(
            {
                "name": spec.name,
                "description": spec.description,
                "category": spec.category,
                "safety_level": spec.safety_level,
                "parameters": spec.parameters_schema,
            }
        )

    def _handle_invalid(self, _args: dict[str, Any]) -> str:
        raise OllamaToolError("invalid tool invoked intentionally")

    def _handle_truncation(self, _args: dict[str, Any]) -> str:
        return self._to_json(
            {
                "max_output_lines": self._runtime_options.max_output_lines,
                "max_output_bytes": self._runtime_options.max_output_bytes,
                "max_read_bytes": self._runtime_options.max_read_bytes,
                "max_search_results": self._runtime_options.max_search_results,
            }
        )

    def _handle_plan_enter(self, args: dict[str, Any]) -> str:
        self._state.plan_mode = True
        goal = str(args.get("goal", "")).strip()
        if goal:
            self._state.plan_content = goal
        return "plan mode enabled"

    def _handle_plan_exit(self, _args: dict[str, Any]) -> str:
        self._state.plan_mode = False
        return "plan mode disabled"

    def _handle_plan(self, args: dict[str, Any]) -> str:
        action = str(args.get("action", "get")).strip().lower() or "get"
        if action == "get":
            return self._state.plan_content or ""
        if action == "set":
            self._state.plan_content = str(args.get("content", ""))
            return "plan updated"
        if action == "append":
            addition = str(args.get("content", ""))
            if self._state.plan_content:
                self._state.plan_content = f"{self._state.plan_content}\n{addition}"
            else:
                self._state.plan_content = addition
            return "plan appended"
        if action == "clear":
            self._state.plan_content = ""
            return "plan cleared"
        raise OllamaToolError("plan action must be get, set, append, or clear.")

    def _handle_question(self, args: dict[str, Any]) -> str:
        return self._to_json(
            {
                "type": "question",
                "prompt": str(args["prompt"]),
                "context": str(args.get("context", "")),
            }
        )

    def _handle_todo(self, args: dict[str, Any]) -> str:
        item = str(args["item"]).strip()
        if not item:
            raise OllamaToolError("todo item must not be empty.")
        self._state.todos.append(item)
        return f"todo added ({len(self._state.todos)} item(s) total)"

    def _handle_todoread(self, _args: dict[str, Any]) -> str:
        if not self._state.todos:
            return "[]"
        return self._to_json(self._state.todos)

    def _handle_todowrite(self, args: dict[str, Any]) -> str:
        items = args.get("items", [])
        if not isinstance(items, list):
            raise OllamaToolError("todowrite items must be an array.")
        normalized = [str(item).strip() for item in items if str(item).strip()]
        mode = str(args.get("mode", "replace")).strip().lower() or "replace"
        if mode == "replace":
            self._state.todos = normalized
        elif mode == "append":
            self._state.todos.extend(normalized)
        else:
            raise OllamaToolError("todowrite mode must be replace or append.")
        return f"todo list now has {len(self._state.todos)} item(s)"

    def _handle_task(self, args: dict[str, Any]) -> str:
        action = str(args.get("action", "list")).strip().lower() or "list"
        if action == "list":
            return self._to_json(self._state.tasks)
        if action == "get":
            name = str(args.get("name", "")).strip()
            if not name:
                raise OllamaToolError("task get requires a task name.")
            return self._state.tasks.get(name, "")
        if action == "set":
            name = str(args.get("name", "")).strip()
            status = str(args.get("status", "")).strip()
            if not name or not status:
                raise OllamaToolError("task set requires name and status.")
            self._state.tasks[name] = status
            return f"task {name!r} set to {status!r}"
        raise OllamaToolError("task action must be list, get, or set.")

    @staticmethod
    def _not_configured(name: str) -> str:
        return f"{name} is not configured in this runtime."

    def _handle_lsp(self, _args: dict[str, Any]) -> str:
        return self._not_configured("lsp")

    def _handle_skill(self, _args: dict[str, Any]) -> str:
        return self._not_configured("skill")

    def _handle_websearch(self, args: dict[str, Any]) -> str:
        if self._web_search_fn is None:
            return self._not_configured("websearch")
        query = str(args["query"])
        max_results = int(args.get("max_results", 5))
        return str(self._web_search_fn(query, max_results))

    def _handle_webfetch(self, args: dict[str, Any]) -> str:
        if self._web_fetch_fn is None:
            return self._not_configured("webfetch")
        url = str(args["url"])
        return str(self._web_fetch_fn(url))
