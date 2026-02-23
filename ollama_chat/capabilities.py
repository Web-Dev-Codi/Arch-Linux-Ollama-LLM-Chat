"""Capability, search, and attachment state containers for the chat application."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CapabilityContext:
    """Immutable snapshot of all model capability flags from config."""

    think: bool = True
    show_thinking: bool = True
    tools_enabled: bool = True
    web_search_enabled: bool = False
    web_search_api_key: str = ""
    vision_enabled: bool = True
    max_tool_iterations: int = 10

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> CapabilityContext:
        """Build a CapabilityContext from the [capabilities] config section."""
        cap_cfg = config.get("capabilities", {})
        return cls(
            think=bool(cap_cfg.get("think", True)),
            show_thinking=bool(cap_cfg.get("show_thinking", True)),
            tools_enabled=bool(cap_cfg.get("tools_enabled", True)),
            web_search_enabled=bool(cap_cfg.get("web_search_enabled", False)),
            web_search_api_key=str(cap_cfg.get("web_search_api_key", "")),
            vision_enabled=bool(cap_cfg.get("vision_enabled", True)),
            max_tool_iterations=int(cap_cfg.get("max_tool_iterations", 10)),
        )


@dataclass
class SearchState:
    """Tracks in-conversation search position and results."""

    query: str = ""
    results: list[int] = field(default_factory=list)
    position: int = -1

    def reset(self) -> None:
        """Clear all search state."""
        self.query = ""
        self.results = []
        self.position = -1

    def advance(self) -> int:
        """Move to the next result, wrapping around. Returns the current message index."""
        if not self.results:
            return -1
        self.position = (self.position + 1) % len(self.results)
        return self.results[self.position]

    def has_results(self) -> bool:
        """Return True when there are search results to navigate."""
        return len(self.results) > 0


@dataclass
class AttachmentState:
    """Pending image and file attachments awaiting the next send."""

    images: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    def add_image(self, path: str) -> None:
        """Queue an image attachment."""
        self.images.append(path)

    def add_file(self, path: str) -> None:
        """Queue a file attachment."""
        self.files.append(path)

    def clear(self) -> None:
        """Discard all pending attachments."""
        self.images.clear()
        self.files.clear()

    def has_any(self) -> bool:
        """Return True when at least one attachment is pending."""
        return bool(self.images or self.files)
