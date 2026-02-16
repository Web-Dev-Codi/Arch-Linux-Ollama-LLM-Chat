"""Async Ollama chat client wrapper with streaming support."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
import logging
from typing import Any

from .exceptions import (
    OllamaChatError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaStreamingError,
)
from .message_store import MessageStore

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - optional transport dependency.
    httpx = None  # type: ignore[assignment]

try:
    from ollama import AsyncClient as _AsyncClient
except ModuleNotFoundError:  # pragma: no cover - exercised only in missing dependency environments.
    _AsyncClient = None  # type: ignore[misc,assignment]

LOGGER = logging.getLogger(__name__)


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
            raise OllamaConnectionError("The ollama package is not installed. Install dependencies with pip install -e .")

        self.message_store = MessageStore(
            system_prompt=system_prompt,
            max_history_messages=max_history_messages,
            max_context_tokens=max_context_tokens,
        )

    @property
    def messages(self) -> list[dict[str, str]]:
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

        if any(self._model_name_matches(self.model, available) for available in available_models):
            LOGGER.info(
                "chat.model.ready",
                extra={"event": "chat.model.ready", "model": self.model},
            )
            return True

        if not pull_if_missing:
            raise OllamaModelNotFoundError(f"Configured model {self.model!r} is not available.")

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
        return self.message_store.estimated_tokens(self.messages)

    @staticmethod
    def _extract_chunk_text(chunk: Any) -> str:
        """Extract streamed token text from an Ollama chunk payload."""
        message_obj = getattr(chunk, "message", None)
        if message_obj is not None:
            message_content = getattr(message_obj, "content", None)
            if isinstance(message_content, str):
                return message_content

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
                content = message.get("content")
                if isinstance(content, str):
                    return content
            content = chunk.get("content")
            if isinstance(content, str):
                return content
        return ""

    def _map_exception(self, exc: Exception) -> OllamaChatError:
        if isinstance(exc, OllamaChatError):
            return exc

        lower_message = str(exc).lower()

        if httpx is not None and isinstance(
            exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError)
        ):
            return OllamaConnectionError(f"Unable to connect to Ollama host {self.host}.")

        if "model" in lower_message and "not found" in lower_message:
            return OllamaModelNotFoundError(f"Model {self.model!r} was not found on {self.host}.")
        if "404" in lower_message and "model" in lower_message:
            return OllamaModelNotFoundError(f"Model {self.model!r} was not found on {self.host}.")

        return OllamaStreamingError(f"Failed to stream response from Ollama at {self.host}: {exc}")

    async def _stream_once(self, request_messages: list[dict[str, str]]) -> AsyncGenerator[str, None]:
        stream = await self._client.chat(model=self.model, messages=request_messages, stream=True)
        async for chunk in stream:
            text = self._extract_chunk_text(chunk)
            if text:
                yield text

    async def send_message(self, user_message: str) -> AsyncGenerator[str, None]:
        """
        Send a user message and stream the assistant reply chunk-by-chunk.

        The user message is appended before streaming starts. On successful completion,
        the final assistant response is appended to conversation history.
        """
        normalized = user_message.strip()
        if not normalized:
            return

        self.message_store.append("user", normalized)
        request_messages = self.message_store.build_api_context()

        assistant_parts: list[str] = []
        for attempt in range(self.retries + 1):
            try:
                async for chunk in self._stream_once(request_messages):
                    assistant_parts.append(chunk)
                    yield chunk
                break
            except asyncio.CancelledError:
                LOGGER.info("chat.request.cancelled", extra={"event": "chat.request.cancelled"})
                raise
            except Exception as exc:  # noqa: BLE001 - external API can fail in many ways.
                mapped_exc = self._map_exception(exc)
                LOGGER.warning(
                    "chat.request.retry",
                    extra={"event": "chat.request.retry", "attempt": attempt + 1, "error_type": mapped_exc.__class__.__name__},
                )
                if attempt >= self.retries:
                    raise mapped_exc from exc
                await asyncio.sleep(self.retry_backoff_seconds * (attempt + 1))

        final_response = "".join(assistant_parts).strip()
        self.message_store.append("assistant", final_response)
