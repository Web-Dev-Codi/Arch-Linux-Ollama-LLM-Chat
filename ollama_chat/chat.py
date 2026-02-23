"""Async Ollama chat client wrapper with streaming, thinking, tools, and vision support."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
import logging
import inspect
from typing import Any, Literal

from .exceptions import (
    OllamaChatError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaStreamingError,
    OllamaToolError,
)
from .message_store import MessageStore

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - optional transport dependency.
    httpx = None  # type: ignore[assignment]

try:
    from ollama import AsyncClient as _AsyncClient
except (
    ModuleNotFoundError
):  # pragma: no cover - exercised only in missing dependency environments.
    _AsyncClient = None  # type: ignore[misc,assignment]

try:
    import ollama as _ollama_pkg
except ModuleNotFoundError:  # pragma: no cover - optional runtime detail for logging
    _ollama_pkg = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)


@dataclass
class ChatChunk:
    """A single typed chunk yielded during a streaming agent-loop response."""

    kind: Literal["thinking", "content", "tool_call", "tool_result"]
    text: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: str = ""


class OllamaChat:
    """Stateful chat wrapper that keeps bounded message history and streams replies."""

    def __init__(
        self,
        host: str,
        model: str,
        system_prompt: str,
        timeout: int = 120,
        retries: int = 2,
        retry_backoff_seconds: float = 0.5,
        max_history_messages: int = 200,
        max_context_tokens: int = 4096,
        client: Any | None = None,
    ) -> None:
        self.host = host
        self.model = model
        self.system_prompt = system_prompt
        self.timeout = timeout
        self.retries = retries
        self.retry_backoff_seconds = retry_backoff_seconds

        if client is not None:
            self._client = client
        elif _AsyncClient is not None:
            self._client = _AsyncClient(host=host, timeout=timeout)
        else:
            raise OllamaConnectionError(
                "The ollama package is not installed. Install dependencies with pip install -e ."
            )

        self.message_store = MessageStore(
            system_prompt=system_prompt,
            max_history_messages=max_history_messages,
            max_context_tokens=max_context_tokens,
        )

        try:
            self._chat_param_names = set(
                inspect.signature(self._client.chat).parameters.keys()
            )
        except Exception:
            self._chat_param_names = set()

        try:
            sdk_version = (
                getattr(_ollama_pkg, "__version__", "unknown")
                if _ollama_pkg is not None
                else "not installed"
            )
        except Exception:
            sdk_version = "unknown"
        LOGGER.info(
            "chat.sdk.signature",
            extra={
                "event": "chat.sdk.signature",
                "sdk_version": sdk_version,
                "supported_params": sorted(self._chat_param_names),
            },
        )

    @property
    def messages(self) -> list[dict[str, Any]]:
        """Expose message history for UI and tests."""
        return self.message_store.messages

    def clear_history(self) -> None:
        """Clear the current conversation while keeping configured system prompts."""
        self.message_store.clear()

    def load_history(self, messages: list[dict[str, str]]) -> None:
        """Replace current history from a persisted conversation payload."""
        self.message_store.replace_messages(messages)

    def set_model(self, model_name: str) -> None:
        """Update the active model name."""
        normalized = model_name.strip()
        if normalized:
            self.model = normalized

    @staticmethod
    def _model_name_matches(requested_model: str, available_model: str) -> bool:
        requested = requested_model.strip().lower()
        available = available_model.strip().lower()
        if requested == available:
            return True
        if ":" not in requested and available.startswith(f"{requested}:"):
            return True
        return False

    async def list_models(self) -> list[str]:
        """Return available model names from Ollama."""
        response = await self._client.list()
        names: list[str] = []
        models: Any = None
        if hasattr(response, "models"):
            models = getattr(response, "models")
        elif isinstance(response, dict):
            models = response.get("models")
        elif hasattr(response, "model_dump"):
            try:
                models = response.model_dump().get("models")
            except Exception:
                models = None

        if isinstance(models, list):
            for model in models:
                candidate_name: str | None = None
                if isinstance(model, dict):
                    for key in ("name", "model"):
                        value = model.get(key)
                        if isinstance(value, str) and value.strip():
                            candidate_name = value.strip()
                            break
                else:
                    for attr in ("name", "model"):
                        value = getattr(model, attr, None)
                        if isinstance(value, str) and value.strip():
                            candidate_name = value.strip()
                            break
                if candidate_name:
                    names.append(candidate_name)
        return names

    async def ensure_model_ready(self, pull_if_missing: bool = True) -> bool:
        """Ensure configured model is available; optionally pull it when missing."""
        try:
            available_models = await self.list_models()
        except Exception as exc:
            raise self._map_exception(exc) from exc

        if any(
            self._model_name_matches(self.model, available)
            for available in available_models
        ):
            LOGGER.info(
                "chat.model.ready",
                extra={"event": "chat.model.ready", "model": self.model},
            )
            return True

        if not pull_if_missing:
            raise OllamaModelNotFoundError(
                f"Configured model {self.model!r} is not available."
            )

        LOGGER.info(
            "chat.model.pull.start",
            extra={"event": "chat.model.pull.start", "model": self.model},
        )
        try:
            await self._client.pull(model=self.model, stream=False)
        except Exception as exc:
            raise self._map_exception(exc) from exc

        LOGGER.info(
            "chat.model.pull.complete",
            extra={"event": "chat.model.pull.complete", "model": self.model},
        )
        return True

    async def check_connection(self) -> bool:
        """Return whether the Ollama host is reachable."""
        try:
            await self._client.list()
            return True
        except Exception:
            return False

    @property
    def estimated_context_tokens(self) -> int:
        """Return deterministic token estimate for current context."""
        # Pass None so MessageStore reads _messages directly (no copy).
        return self.message_store.estimated_tokens()

    @staticmethod
    def _extract_from_chunk(chunk: Any, field: str) -> Any:
        """Extract a named field from message.field in an Ollama chunk payload.

        Tries SDK object attribute access first, then falls back to dict paths
        produced by model_dump() / dict().  Returns None when the field is absent.
        """
        message_obj = getattr(chunk, "message", None)
        if message_obj is not None:
            value = getattr(message_obj, field, None)
            if value is not None:
                return value

        # Normalise Pydantic-model chunks to plain dicts once.
        if hasattr(chunk, "model_dump"):
            try:
                chunk = chunk.model_dump()
            except Exception:
                pass
        elif hasattr(chunk, "dict"):
            try:
                chunk = chunk.dict()
            except Exception:
                pass

        if isinstance(chunk, dict):
            message = chunk.get("message")
            if isinstance(message, dict):
                value = message.get(field)
                if value is not None:
                    return value
            # Top-level fallback (e.g. generate endpoint).
            return chunk.get(field)
        return None

    @classmethod
    def _extract_chunk_text(cls, chunk: Any) -> str:
        """Extract streamed token text from an Ollama chunk payload."""
        value = cls._extract_from_chunk(chunk, "content")
        return value if isinstance(value, str) else ""

    @classmethod
    def _extract_chunk_thinking(cls, chunk: Any) -> str:
        """Extract streamed thinking text from an Ollama chunk payload."""
        value = cls._extract_from_chunk(chunk, "thinking")
        return value if isinstance(value, str) else ""

    @classmethod
    def _extract_chunk_tool_calls(cls, chunk: Any) -> list[Any]:
        """Extract tool_calls from an Ollama chunk payload."""
        value = cls._extract_from_chunk(chunk, "tool_calls")
        return value if isinstance(value, list) else []

    def _map_exception(self, exc: Exception) -> OllamaChatError:
        if isinstance(exc, OllamaChatError):
            return exc

        lower_message = str(exc).lower()

        if httpx is not None and isinstance(
            exc,
            (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.NetworkError,
            ),
        ):
            return OllamaConnectionError(
                f"Unable to connect to Ollama host {self.host}."
            )

        if "model" in lower_message and "not found" in lower_message:
            return OllamaModelNotFoundError(
                f"Model {self.model!r} was not found on {self.host}."
            )
        if "404" in lower_message and "model" in lower_message:
            return OllamaModelNotFoundError(
                f"Model {self.model!r} was not found on {self.host}."
            )

        return OllamaStreamingError(
            f"Failed to stream response from Ollama at {self.host}: {exc}"
        )

    async def _stream_once_with_capabilities(
        self,
        request_messages: list[dict[str, Any]],
        tools: list[Any],
        think: bool,
    ) -> AsyncGenerator[ChatChunk, None]:
        """Stream a single chat turn, yielding typed ChatChunk objects.

        Yields thinking, content, and tool_call chunks as they arrive.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": request_messages,
            "stream": True,
        }
        if think:
            kwargs["think"] = True
        if tools:
            kwargs["tools"] = tools

        # Only strip optional kwargs when we *know* the SDK doesn't accept them.
        # If signature introspection failed (empty set), keep kwargs so tests and
        # newer SDK versions can still receive them.
        if self._chat_param_names:
            if "think" not in self._chat_param_names:
                kwargs.pop("think", None)
            if "tools" not in self._chat_param_names:
                kwargs.pop("tools", None)

        stream = await self._client.chat(**kwargs)
        async for chunk in stream:
            thinking_text = self._extract_chunk_thinking(chunk)
            if thinking_text:
                yield ChatChunk(kind="thinking", text=thinking_text)

            content_text = self._extract_chunk_text(chunk)
            if content_text:
                yield ChatChunk(kind="content", text=content_text)

            chunk_tool_calls = self._extract_chunk_tool_calls(chunk)
            for tc in chunk_tool_calls:
                name, args = self._parse_tool_call(tc)
                if name:
                    yield ChatChunk(kind="tool_call", tool_name=name, tool_args=args)

    @staticmethod
    def _parse_tool_call(tc: Any) -> tuple[str, dict[str, Any]]:
        """Extract (name, arguments) from a tool call object or dict."""
        # SDK object: tc.function.name / tc.function.arguments
        fn = getattr(tc, "function", None)
        if fn is not None:
            name = getattr(fn, "name", None) or ""
            args = getattr(fn, "arguments", None) or {}
            if not isinstance(args, dict):
                args = {}
            return str(name), args

        # Dict-based fallback
        if isinstance(tc, dict):
            fn_dict = tc.get("function", {})
            if isinstance(fn_dict, dict):
                name = str(fn_dict.get("name", ""))
                args = fn_dict.get("arguments", {})
                if not isinstance(args, dict):
                    args = {}
                return name, args
        return "", {}

    async def send_message(
        self,
        user_message: str,
        images: list[str | bytes] | None = None,
        tool_registry: Any | None = None,
        think: bool = False,
        max_tool_iterations: int = 10,
    ) -> AsyncGenerator[ChatChunk, None]:
        """Send a user message and stream the assistant reply as typed ChatChunk objects.

        Supports thinking traces, tool calling with a full agent loop, and
        image attachments for vision-capable models.

        Images are passed to the API but are NOT stored in conversation history.
        """
        normalized = user_message.strip()
        if not normalized and not images:
            return

        # Build the user message dict; include images only for the API call.
        user_msg: dict[str, Any] = {"role": "user", "content": normalized}
        if images:
            user_msg["images"] = list(images)

        # Persist only the text portion to history (images are ephemeral).
        self.message_store.append("user", normalized)

        # Build the initial API context; inject images into the last user message.
        request_messages: list[dict[str, Any]] = list(
            self.message_store.build_api_context()
        )
        if images and request_messages:
            request_messages[-1] = dict(request_messages[-1])
            request_messages[-1]["images"] = list(images)

        tools: list[Any] = []
        if tool_registry is not None and not tool_registry.is_empty:
            tools = tool_registry.build_tools_list()

        # Accumulated assistant message parts (for history persistence).
        accumulated_thinking = ""
        accumulated_content = ""
        accumulated_tool_calls: list[dict[str, Any]] = []

        for iteration in range(max_tool_iterations):
            for attempt in range(self.retries + 1):
                try:
                    async for chunk in self._stream_once_with_capabilities(
                        request_messages, tools, think
                    ):
                        if chunk.kind == "thinking":
                            accumulated_thinking += chunk.text
                            yield chunk
                        elif chunk.kind == "content":
                            accumulated_content += chunk.text
                            yield chunk
                        elif chunk.kind == "tool_call":
                            accumulated_tool_calls.append(
                                {"name": chunk.tool_name, "args": chunk.tool_args}
                            )
                            yield chunk
                    break
                except asyncio.CancelledError:
                    LOGGER.info(
                        "chat.request.cancelled",
                        extra={"event": "chat.request.cancelled"},
                    )
                    raise
                except OllamaToolError:
                    raise
                except (
                    Exception
                ) as exc:  # noqa: BLE001 - external API can fail in many ways.
                    mapped_exc = self._map_exception(exc)
                    LOGGER.warning(
                        "chat.request.retry",
                        extra={
                            "event": "chat.request.retry",
                            "attempt": attempt + 1,
                            "error_type": mapped_exc.__class__.__name__,
                        },
                    )
                    if attempt >= self.retries:
                        raise mapped_exc from exc
                    await asyncio.sleep(self.retry_backoff_seconds * (attempt + 1))

            # If no tool calls, the agent loop is complete.
            if not accumulated_tool_calls:
                break

            # Append the assistant turn (with tool calls) to the request context.
            # accumulated_tool_calls is non-empty here (checked above).
            assistant_turn: dict[str, Any] = {
                "role": "assistant",
                "content": accumulated_content,
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["args"]},
                    }
                    for tc in accumulated_tool_calls
                ],
            }
            if accumulated_thinking:
                assistant_turn["thinking"] = accumulated_thinking
            request_messages.append(assistant_turn)

            # Execute each tool call and append results.
            for tc in accumulated_tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                LOGGER.info(
                    "chat.tool.call",
                    extra={
                        "event": "chat.tool.call",
                        "tool": tool_name,
                        "iteration": iteration + 1,
                    },
                )
                try:
                    result = tool_registry.execute(tool_name, tool_args)  # type: ignore[union-attr]
                except OllamaToolError as exc:
                    result = f"[Tool error: {exc}]"
                    LOGGER.warning(
                        "chat.tool.error",
                        extra={
                            "event": "chat.tool.error",
                            "tool": tool_name,
                            "error": str(exc),
                        },
                    )
                yield ChatChunk(
                    kind="tool_result",
                    tool_name=tool_name,
                    tool_args=tool_args,
                    tool_result=result,
                )
                request_messages.append(
                    {"role": "tool", "tool_name": tool_name, "content": result}
                )

            # Reset for next iteration, preserving only accumulated_content for history.
            accumulated_thinking = ""
            accumulated_content = ""
            accumulated_tool_calls = []

        # Persist the final assistant response (text only) to history.
        final_response = accumulated_content.strip()
        self.message_store.append("assistant", final_response)
