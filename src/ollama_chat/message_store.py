"""Bounded message storage and deterministic context trimming."""

from __future__ import annotations

from collections.abc import Iterable
import json
from typing import Any

# Public message type (no internal fields).
Message = dict[str, Any]


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
                    "_token_estimate": self._estimate_tokens_for_parts(
                        "system", system_prompt.strip()
                    ),
                }
            )
        self._messages: list[Message] = list(self._base_messages)

    @property
    def messages(self) -> list[Message]:
        """Return a shallow copy of all stored messages (without internal keys)."""
        cleaned: list[Message] = []
        for message in self._messages:
            payload = {k: v for k, v in message.items() if not k.startswith("_")}
            cleaned.append(payload)
        return cleaned

    @property
    def message_count(self) -> int:
        """Return the total number of stored messages."""
        return len(self._messages)

    @property
    def non_system_count(self) -> int:
        """Return the number of non-system messages without copying the list."""
        return sum(1 for m in self._messages if m.get("role") != "system")

    def clear(self) -> None:
        """Reset store while preserving initial system messages."""
        self._messages = list(self._base_messages)

    def rollback_last_user_append(self) -> None:
        """Remove the last message if it is a user message.

        Used to undo a user-message append when streaming fails, preventing
        consecutive user messages from corrupting API history on the next send.
        """
        if self._messages and self._messages[-1].get("role") == "user":
            self._messages.pop()

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
                        "_token_estimate": self._estimate_tokens_for_parts(
                            role, content
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
                "_token_estimate": self._estimate_tokens_for_parts(
                    normalized_role, normalized_content
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
        # Fast path: cached int from append/replace_messages.
        if isinstance(cached, int):
            return cached
        # Fallback: recompute and cache (handles messages loaded without estimates).
        role = message.get("role", "")
        content = message.get("content", "")
        estimate = cls._estimate_tokens_for_parts(str(role), str(content))
        message["_token_estimate"] = estimate
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
        """Enforce max_history_messages in O(n) by slicing, not repeated deletion."""
        if len(self._messages) <= self.max_history_messages:
            return
        system_msgs = [m for m in self._messages if m.get("role") == "system"]
        non_system = [m for m in self._messages if m.get("role") != "system"]
        max_non_system = max(0, self.max_history_messages - len(system_msgs))
        # Keep only the newest non-system messages that fit within the limit.
        trimmed = non_system[-max_non_system:] if max_non_system > 0 else []
        self._messages = system_msgs + trimmed

    def _trim_context_in_place(
        self, context: list[Message], max_context_tokens: int
    ) -> None:
        """Remove oldest non-system messages until token budget is met — O(n).

        Walks from newest to oldest non-system message, greedily keeping messages
        that fit within the remaining budget after reserving space for system messages.
        This matches the original FIFO-eviction semantics in a single pass.
        """
        total = sum(self._message_tokens(m) for m in context)
        if total <= max_context_tokens:
            return

        system_msgs = [m for m in context if m.get("role") == "system"]
        non_system = [m for m in context if m.get("role") != "system"]

        if not non_system:
            return  # Only system messages remain; cannot trim further.

        system_cost = sum(self._message_tokens(m) for m in system_msgs)
        budget = max(0, max_context_tokens - system_cost)

        # Walk from newest (right) to oldest (left), accumulating tokens.
        # Stop as soon as a message exceeds the remaining budget — all older
        # messages would also have been evicted by the original FIFO algorithm.
        kept_start = len(non_system)  # default: keep nothing
        cumulative = 0
        for i in range(len(non_system) - 1, -1, -1):
            cost = self._message_tokens(non_system[i])
            if cumulative + cost <= budget:
                cumulative += cost
                kept_start = i
            else:
                break

        context[:] = system_msgs + non_system[kept_start:]
