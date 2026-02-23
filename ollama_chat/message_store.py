"""Bounded message storage and deterministic context trimming."""

from __future__ import annotations

import json
from typing import Iterable

Message = dict[str, str]


class MessageStore:
    """Manage conversation history with bounds and context trimming."""

    def __init__(
        self,
        system_prompt: str = "",
        max_history_messages: int = 200,
        max_context_tokens: int = 4096,
    ) -> None:
        self.max_history_messages = max(1, max_history_messages)
        self.max_context_tokens = max(1, max_context_tokens)
        self._base_messages: list[Message] = []
        if system_prompt.strip():
            self._base_messages.append(
                {
                    "role": "system",
                    "content": system_prompt.strip(),
                    "_token_estimate": str(
                        self._estimate_tokens_for_parts("system", system_prompt.strip())
                    ),
                }
            )
        self._messages: list[Message] = list(self._base_messages)

    @property
    def messages(self) -> list[Message]:
        """Return a shallow copy of all stored messages."""
        cleaned: list[Message] = []
        for message in self._messages:
            payload = dict(message)
            payload.pop("_token_estimate", None)
            cleaned.append(payload)
        return cleaned

    @property
    def message_count(self) -> int:
        """Return the number of stored messages."""
        return len(self._messages)

    def clear(self) -> None:
        """Reset store while preserving initial system messages."""
        self._messages = list(self._base_messages)

    def replace_messages(self, messages: list[Message]) -> None:
        """Replace history from persisted data while keeping invariants."""
        normalized_messages: list[Message] = []
        for message in messages:
            role = str(message.get("role", "")).strip().lower()
            content = str(message.get("content", "")).strip()
            if role:
                normalized_messages.append(
                    {
                        "role": role,
                        "content": content,
                        "_token_estimate": str(
                            self._estimate_tokens_for_parts(role, content)
                        ),
                    }
                )

        if not normalized_messages:
            self.clear()
            return

        if (
            not any(item.get("role") == "system" for item in normalized_messages)
            and self._base_messages
        ):
            normalized_messages = list(self._base_messages) + normalized_messages

        self._messages = normalized_messages
        self._trim_by_history_limit()

    def append(self, role: str, content: str) -> None:
        """Append a normalized message and enforce storage bounds."""
        normalized_role = role.strip().lower()
        normalized_content = content.strip()
        if not normalized_role:
            return
        self._messages.append(
            {
                "role": normalized_role,
                "content": normalized_content,
                "_token_estimate": str(
                    self._estimate_tokens_for_parts(normalized_role, normalized_content)
                ),
            }
        )
        self._trim_by_history_limit()

    @staticmethod
    def _estimate_tokens_for_parts(role: str, content: str) -> int:
        """Estimate token cost for a single message from role/content."""
        role_cost = 2 if role else 0
        return role_cost + len(content) // 4 + len(content.split()) + 2

    @classmethod
    def _message_tokens(cls, message: Message) -> int:
        cached = message.get("_token_estimate")
        if isinstance(cached, str) and cached.isdigit():
            return int(cached)
        role = message.get("role", "")
        content = message.get("content", "")
        estimate = cls._estimate_tokens_for_parts(str(role), str(content))
        message["_token_estimate"] = str(estimate)
        return estimate

    def estimated_tokens(self, messages: Iterable[Message] | None = None) -> int:
        """Estimate token count deterministically from message text."""
        items = self._messages if messages is None else list(messages)
        total = sum(self._message_tokens(m) for m in items)
        return max(total, 1)

    def build_api_context(self, max_context_tokens: int | None = None) -> list[Message]:
        """Build API context while preserving system messages and token limits."""
        limit = max(1, max_context_tokens or self.max_context_tokens)
        # Shallow-copy each dict so callers can safely mutate the list.
        context: list[Message] = [dict(m) for m in self._messages]
        self._trim_context_in_place(context, limit)
        return context

    def export_json(self) -> str:
        """Export current history using stable list and field ordering."""
        stable_messages = [
            {"role": message.get("role", ""), "content": message.get("content", "")}
            for message in self._messages
        ]
        return json.dumps(
            stable_messages, ensure_ascii=False, separators=(",", ":"), sort_keys=False
        )

    def _trim_by_history_limit(self) -> None:
        while len(self._messages) > self.max_history_messages:
            removed = self._remove_oldest_non_system(self._messages)
            if not removed:
                self._messages.pop(0)

    def _trim_context_in_place(
        self, context: list[Message], max_context_tokens: int
    ) -> None:
        """Remove oldest non-system messages until token budget is met.

        Token total is maintained incrementally (O(n)) rather than
        re-computed from scratch on every removal (was O(n²)).
        """
        total = sum(self._message_tokens(m) for m in context)
        while total > max_context_tokens and context:
            for index, message in enumerate(context):
                if message.get("role") != "system":
                    total -= self._message_tokens(message)
                    del context[index]
                    break
            else:
                # Only system messages remain; cannot trim further.
                break

    @staticmethod
    def _remove_oldest_non_system(messages: list[Message]) -> bool:
        for index, message in enumerate(messages):
            if message.get("role") != "system":
                del messages[index]
                return True
        return False
