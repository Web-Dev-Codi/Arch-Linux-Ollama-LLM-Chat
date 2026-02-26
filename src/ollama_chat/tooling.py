"""Tool registry for Ollama agent-loop tool calling."""

from __future__ import annotations

from collections.abc import Callable
import asyncio
import concurrent.futures
from dataclasses import dataclass, field
from inspect import Parameter, signature
import logging
import os
import sys
import threading
import time
from typing import Any

from .custom_tools import CustomToolSuite, ToolRuntimeOptions, ToolSpec
from .exceptions import OllamaToolError
from .tools.base import ToolContext

try:
    from ollama import web_fetch as _ollama_web_fetch
    from ollama import web_search as _ollama_web_search
except ModuleNotFoundError:  # pragma: no cover - optional dependency.
    _ollama_web_search = None  # type: ignore[assignment]
    _ollama_web_fetch = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)

# Serialise all temporary env-var mutations so that concurrent threads
# (e.g. when tool execution is offloaded via asyncio.to_thread) cannot
# observe each other's transient OLLAMA_API_KEY value.
_env_lock = threading.Lock()


def _run_async_from_sync(coro):
    """Run async coroutine from sync context, handling existing event loops.

    If called from within an async context (existing event loop), runs the
    coroutine in a new thread with its own event loop.

    If called from sync context (no running loop), creates a new event loop.
    """
    try:
        # Check if there's a running loop
        loop = asyncio.get_running_loop()
        # We're in an async context - need to run in a new thread with new loop
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # No running loop - safe to create one
        return asyncio.run(coro)


def _with_temp_env(key: str, value: str, fn: Callable[[], str]) -> str:
    """Temporarily set an environment variable, call fn(), then restore.

    Protected by a module-level lock so that concurrent threads do not
    observe each other's transient environment changes.
    """
    with _env_lock:
        old_value = os.environ.get(key)
        os.environ[key] = value
        try:
            return fn()
        finally:
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def _truncate_output(text: str, max_lines: int, max_bytes: int) -> tuple[str, bool]:
    """Apply deterministic truncation by byte and line limits."""
    truncated = False
    result = text

    if max_bytes > 0:
        encoded = result.encode("utf-8", errors="ignore")
        if len(encoded) > max_bytes:
            truncated = True
            clipped = encoded[:max_bytes]
            result = clipped.decode("utf-8", errors="ignore")
            result += "\n... [truncated by byte limit]"

    if max_lines > 0:
        lines = result.splitlines()
        if len(lines) > max_lines:
            truncated = True
            result = "\n".join(lines[:max_lines] + ["... [truncated by line limit]"])

    return result, truncated


class ToolsPackageAdapter:
    def __init__(
        self,
        runtime_options: ToolRuntimeOptions,
        ask_cb: Callable[..., Any] | None = None,
        metadata_cb: Callable[[dict], None] | None = None,
    ) -> None:
        self._runtime = runtime_options
        self._ask_cb = ask_cb
        self._metadata_cb = metadata_cb

    def to_specs(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        # Ensure modules that import `from support import ...` can resolve the local
        # package alias (ollama_chat.support) without modifying their import lines.
        try:
            import ollama_chat.support as _support_pkg  # type: ignore[import-not-found]

            sys.modules.setdefault("support", _support_pkg)
        except Exception:
            pass
        try:
            from .tools.registry import get_registry  # local/lazy import

            tools = get_registry().tools_for_model()
        except Exception:
            tools = []
        for tool in tools:
            name = getattr(tool, "id", "")
            if not name:
                continue

            # Use the NEW to_ollama_schema() method which returns proper format
            try:
                ollama_schema = tool.to_ollama_schema()
                # Extract the inner function dict for the parameters
                func_dict = ollama_schema.get("function", {})
                schema = func_dict.get(
                    "parameters",
                    {
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": True,
                    },
                )
            except AttributeError:
                # Fallback to legacy schema() method for old tools
                try:
                    legacy = tool.schema()
                    schema = legacy.get(
                        "parameters",
                        {
                            "type": "object",
                            "properties": {},
                            "required": [],
                        },
                    )
                except Exception:
                    schema = {"type": "object", "properties": {}, "required": []}
            except Exception:
                schema = {"type": "object", "properties": {}, "required": []}

            # Ensure schema has correct structure
            if schema.get("type") != "object":
                schema = {
                    "type": "object",
                    "properties": schema.get("properties", {}),
                    "required": schema.get("required", []),
                    "additionalProperties": True,
                }
            else:
                schema.setdefault("additionalProperties", True)

            def make_handler(t=tool) -> Callable[[dict[str, Any]], str]:
                def handler(args: dict[str, Any]) -> str:
                    async def _run() -> str:
                        ctx = ToolContext(
                            session_id="default",
                            message_id=str(time.time_ns()),
                            agent="ollama",
                            abort=asyncio.Event(),
                            extra={
                                "project_dir": self._runtime.workspace_root,
                                "bypassCwdCheck": self._runtime.allow_external_directories,
                            },
                        )
                        if self._metadata_cb is not None:
                            ctx._metadata_cb = self._metadata_cb  # type: ignore[attr-defined]
                        if self._ask_cb is not None:
                            ctx._ask_cb = self._ask_cb  # type: ignore[attr-defined]
                        result = await t.run(args, ctx)
                        return str(result.output)

                    return _run_async_from_sync(_run())

                return handler

            specs.append(
                ToolSpec(
                    name=name,
                    description=getattr(tool, "description", name),
                    parameters_schema=schema,
                    handler=make_handler(),
                    safety_level="safe",
                    category="builtin",
                )
            )
        return specs


class ToolRegistry:
    """Registry of callable tools available to the model during an agent loop."""

    def __init__(self, runtime_options: ToolRuntimeOptions | None = None) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}
        self._specs: dict[str, ToolSpec] = {}
        self._runtime_options = runtime_options or ToolRuntimeOptions()

    def register(self, fn: Callable[..., Any]) -> None:
        """Register a callable as a named tool.

        The function name is used as the tool name.
        """
        self._tools[fn.__name__] = fn
        LOGGER.debug(
            "tools.registered",
            extra={"event": "tools.registered", "tool": fn.__name__},
        )

    def register_spec(self, spec: ToolSpec) -> None:
        """Register a schema-first tool specification."""
        self._specs[spec.name] = spec
        LOGGER.debug(
            "tools.spec.registered",
            extra={"event": "tools.spec.registered", "tool": spec.name},
        )

    def list_tool_names(self) -> list[str]:
        """Return all callable and schema tool names."""
        names = set(self._tools.keys()) | set(self._specs.keys())
        return sorted(names)

    def build_tools_list(self) -> list[dict[str, Any]]:
        """Return Ollama-formatted tool schemas (no raw callables).

        Converts all registered tools (both callables and ToolSpecs) into
        properly formatted Ollama tool schemas with the structure:
        {
            "type": "function",
            "function": {
                "name": "...",
                "description": "...",
                "parameters": {...}
            }
        }
        """
        schemas: list[dict[str, Any]] = []

        # Convert callable tools to schemas via introspection
        for name, fn in self._tools.items():
            try:
                sig = signature(fn)
                params: dict[str, Any] = {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": True,
                }

                for param_name, param in sig.parameters.items():
                    if param_name in ("self", "cls"):
                        continue

                    # Extract type hint if available
                    param_type = "string"  # Default
                    if param.annotation != Parameter.empty:
                        ann_str = str(param.annotation).lower()
                        if "int" in ann_str:
                            param_type = "integer"
                        elif "float" in ann_str or "number" in ann_str:
                            param_type = "number"
                        elif "bool" in ann_str:
                            param_type = "boolean"
                        elif "list" in ann_str or "sequence" in ann_str:
                            param_type = "array"
                        elif "dict" in ann_str or "mapping" in ann_str:
                            param_type = "object"

                    params["properties"][param_name] = {
                        "type": param_type,
                        "description": param_name,
                    }

                    # Mark as required if no default value
                    if param.default == Parameter.empty:
                        params["required"].append(param_name)

                schemas.append(
                    {
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": (fn.__doc__ or name).strip(),
                            "parameters": params,
                        },
                    }
                )
            except Exception as exc:
                LOGGER.warning(
                    "tools.schema.introspection.failed",
                    extra={
                        "event": "tools.schema.introspection.failed",
                        "tool": name,
                        "error": str(exc),
                    },
                )

        # Add ToolSpec schemas (already properly formatted)
        schemas.extend([spec.as_ollama_tool() for spec in self._specs.values()])

        return schemas

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a named tool and return its string result.

        Schema validation is handled by the ToolSpec handler or Tool.run().
        This method just coordinates execution and applies output truncation.

        Raises OllamaToolError if the tool is unknown or raises an exception.
        This method is synchronous; callers in an async context should use
        ``asyncio.to_thread(registry.execute, name, args)`` to avoid blocking
        the event loop.
        """
        spec = self._specs.get(name)
        if spec is not None:
            try:
                # ToolSpec handlers do their own validation if needed
                result = str(spec.handler(arguments))
                truncated, _ = _truncate_output(
                    result,
                    max_lines=self._runtime_options.max_output_lines,
                    max_bytes=self._runtime_options.max_output_bytes,
                )
                return truncated
            except OllamaToolError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise OllamaToolError(f"Tool {name!r} raised an error: {exc}") from exc

        fn = self._tools.get(name)
        if fn is None:
            raise OllamaToolError(f"Unknown tool requested by model: {name!r}")

        try:
            result = str(fn(**arguments))
            truncated, _ = _truncate_output(
                result,
                max_lines=self._runtime_options.max_output_lines,
                max_bytes=self._runtime_options.max_output_bytes,
            )
            return truncated
        except OllamaToolError:
            raise
        except Exception as exc:  # noqa: BLE001 - tool functions can fail arbitrarily.
            raise OllamaToolError(f"Tool {name!r} raised an error: {exc}") from exc

    @property
    def is_empty(self) -> bool:
        """Return True when no tools are registered."""
        return not bool(self._tools or self._specs)


@dataclass(frozen=True)
class ToolRegistryOptions:
    """Options used to build a ToolRegistry without boolean flags.

    If ``web_search_api_key`` is a non-empty string, web_search and web_fetch
    tools are registered with the provided key. If it is empty or None, no web
    tools are added.
    """

    web_search_api_key: str | None = None
    enable_custom_tools: bool = False
    enable_builtin_tools: bool = True
    runtime_options: ToolRuntimeOptions = field(default_factory=ToolRuntimeOptions)


def build_registry(options: ToolRegistryOptions | None = None) -> ToolRegistry:
    """Build a ToolRegistry based on provided options.

    - Optional callable-based web_search/web_fetch registration remains for
      backward compatibility.
    - Optional schema-based custom coding tools are registered when
      ``enable_custom_tools`` is true.
    """
    runtime = options.runtime_options if options is not None else ToolRuntimeOptions()
    registry = ToolRegistry(runtime_options=runtime)
    if options is None:
        return registry

    api_key = (options.web_search_api_key or "").strip()
    web_search_fn: Callable[[str, int], str] | None = None
    web_fetch_fn: Callable[[str], str] | None = None

    if api_key:
        web_search_fn = _make_web_search_tool(api_key)
        web_fetch_fn = _make_web_fetch_tool(api_key)
        # Backwards-compatible callable registrations.
        registry.register(web_search_fn)
        registry.register(web_fetch_fn)
        LOGGER.info(
            "tools.web_search.enabled",
            extra={"event": "tools.web_search.enabled"},
        )

    # Register built-in class-based tools first so that custom tools may override
    # duplicate names when both systems are enabled.
    builtin_names: set[str] = set()
    if options.enable_builtin_tools:
        adapter = ToolsPackageAdapter(options.runtime_options)
        builtin_specs = adapter.to_specs()
        for spec in builtin_specs:
            registry.register_spec(spec)
            builtin_names.add(spec.name)

    if options.enable_custom_tools:
        suite = CustomToolSuite(
            runtime_options=options.runtime_options,
            web_search_fn=web_search_fn,
            web_fetch_fn=web_fetch_fn,
        )
        suite.bind_executor(registry.execute)
        for spec in suite.specs():
            # Prefer built-in implementations for overlapping names in the initial
            # allowlist (read, edit, grep, codesearch, list). Skip duplicates.
            if spec.name in builtin_names:
                continue
            registry.register_spec(spec)
    return registry


def _make_web_search_tool(api_key: str) -> Callable[..., str]:
    """Return a web_search callable with the API key bound at creation time."""

    if _ollama_web_search is None:
        raise OllamaToolError(
            "web_search is unavailable: the ollama package is not installed."
        )

    def _web_search_tool(query: str, max_results: int = 5) -> str:
        """Search the web for a query and return relevant results.

        Args:
            query: The search query string.
            max_results: Maximum number of results to return (1-10).

        Returns:
            Formatted search results as a string.
        """
        try:
            return _with_temp_env(
                "OLLAMA_API_KEY",
                api_key,
                lambda: str(_ollama_web_search(query, max_results=max_results)),
            )
        except Exception as exc:  # noqa: BLE001
            raise OllamaToolError(f"web_search failed: {exc}") from exc

    return _web_search_tool


def _make_web_fetch_tool(api_key: str) -> Callable[..., str]:
    """Return a web_fetch callable with the API key bound at creation time."""

    if _ollama_web_fetch is None:
        raise OllamaToolError(
            "web_fetch is unavailable: the ollama package is not installed."
        )

    def _web_fetch_tool(url: str) -> str:
        """Fetch the content of a web page by URL.

        Args:
            url: The URL to fetch.

        Returns:
            The page title and content as a string.
        """
        try:
            return _with_temp_env(
                "OLLAMA_API_KEY",
                api_key,
                lambda: str(_ollama_web_fetch(url)),
            )
        except Exception as exc:  # noqa: BLE001
            raise OllamaToolError(f"web_fetch failed: {exc}") from exc

    return _web_fetch_tool


def build_default_registry(
    web_search_enabled: bool = False,
    web_search_api_key: str = "",
) -> ToolRegistry:
    """Compatibility wrapper for legacy API with a boolean flag.

    Prefer ``build_registry(ToolRegistryOptions(web_search_api_key=...))``.
    """
    if not web_search_enabled:
        return ToolRegistry()

    # Resolve API key: explicit config value takes precedence over env var.
    api_key = web_search_api_key or os.environ.get("OLLAMA_API_KEY", "").strip()
    if not api_key:
        raise OllamaToolError(
            "web_search_enabled is True but no OLLAMA_API_KEY was found. "
            "Set web_search_api_key in [capabilities] or export OLLAMA_API_KEY."
        )

    return build_registry(ToolRegistryOptions(web_search_api_key=api_key))
