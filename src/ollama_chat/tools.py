"""Tool registry for Ollama agent-loop tool calling."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import logging
import os
import threading
from typing import Any

from .custom_tools import CustomToolSuite, ToolRuntimeOptions, ToolSpec
from .exceptions import OllamaToolError

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

    def build_tools_list(self) -> list[Any]:
        """Return callable and schema tools for passing to the Ollama SDK."""
        callables = list(self._tools.values())
        schema_tools = [spec.as_ollama_tool() for spec in self._specs.values()]
        return callables + schema_tools

    def _validate_value(self, name: str, value: Any, schema: dict[str, Any]) -> None:
        expected = schema.get("type")
        if expected is None:
            return

        if expected == "string":
            if not isinstance(value, str):
                raise OllamaToolError(f"Argument {name!r} must be a string.")
            return

        if expected == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                raise OllamaToolError(f"Argument {name!r} must be an integer.")
            return

        if expected == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise OllamaToolError(f"Argument {name!r} must be numeric.")
            return

        if expected == "boolean":
            if not isinstance(value, bool):
                raise OllamaToolError(f"Argument {name!r} must be a boolean.")
            return

        if expected == "object":
            if not isinstance(value, dict):
                raise OllamaToolError(f"Argument {name!r} must be an object.")
            return

        if expected == "array":
            if not isinstance(value, list):
                raise OllamaToolError(f"Argument {name!r} must be an array.")
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for idx, item in enumerate(value):
                    self._validate_value(f"{name}[{idx}]", item, item_schema)
            return

    def _validate_schema_arguments(
        self,
        schema: dict[str, Any],
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate arguments against a constrained JSON schema subset."""
        if not isinstance(arguments, dict):
            raise OllamaToolError("Tool arguments must be a JSON object.")

        if schema.get("type") != "object":
            raise OllamaToolError("Tool schema root must be an object.")

        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise OllamaToolError("Tool schema properties must be an object.")
        required = schema.get("required", [])
        if not isinstance(required, list):
            raise OllamaToolError("Tool schema required must be a list.")
        additional_allowed = bool(schema.get("additionalProperties", False))

        missing = [name for name in required if name not in arguments]
        if missing:
            raise OllamaToolError(f"Missing required argument(s): {', '.join(missing)}")

        for arg_name, arg_value in arguments.items():
            prop_schema = properties.get(arg_name)
            if prop_schema is None:
                if additional_allowed:
                    continue
                raise OllamaToolError(f"Unknown argument: {arg_name!r}")
            self._validate_value(arg_name, arg_value, prop_schema)

        return arguments

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a named tool and return its string result.

        Raises OllamaToolError if the tool is unknown or raises an exception.
        This method is synchronous; callers in an async context should use
        ``asyncio.to_thread(registry.execute, name, args)`` to avoid blocking
        the event loop.
        """
        spec = self._specs.get(name)
        if spec is not None:
            try:
                validated = self._validate_schema_arguments(
                    spec.parameters_schema,
                    arguments,
                )
                result = str(spec.handler(validated))
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

    if options.enable_custom_tools:
        suite = CustomToolSuite(
            runtime_options=options.runtime_options,
            web_search_fn=web_search_fn,
            web_fetch_fn=web_fetch_fn,
        )
        suite.bind_executor(registry.execute)
        for spec in suite.specs():
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
