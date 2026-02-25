"""Conversation persistence utilities for save/load/export workflows."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from .exceptions import OllamaChatError


class PersistenceError(OllamaChatError):
    """Raised when persistence operations fail."""


class PersistenceDisabledError(PersistenceError):
    """Raised when persistence is disabled in configuration."""


class PersistenceFormatError(PersistenceError):
    """Raised when a persisted payload cannot be decoded safely."""


class ConversationPersistence:
    """Manage on-disk conversation snapshots and metadata index."""

    def __init__(self, enabled: bool, directory: str, metadata_path: str) -> None:
        self.enabled = enabled
        self.directory = Path(directory).expanduser()
        self.metadata_path = Path(metadata_path).expanduser()

    def _enforce_permissions(self, path: Path, mode: int = 0o600) -> None:
        """Set POSIX permissions on a file or directory; silently ignores failures."""
        if os.name != "posix":
            return
        try:
            path.chmod(mode)
        except OSError:
            pass

    def _ensure_paths(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._enforce_permissions(self.directory, 0o700)
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self._enforce_permissions(self.metadata_path.parent, 0o700)
        if not self.metadata_path.exists():
            self.metadata_path.write_text("[]", encoding="utf-8")
        self._enforce_permissions(self.metadata_path)

    def _resolve_snapshot_path(self, raw_path: str) -> Path | None:
        candidate = Path(raw_path).expanduser()
        try:
            base = self.directory.resolve(strict=False)
            resolved = candidate.resolve(strict=False)
        except OSError:
            return None

        # Ensure resolved is inside base.
        try:
            resolved.relative_to(base)
        except ValueError:
            return None
        return resolved

    def _read_index(self) -> list[dict[str, str]]:
        self._ensure_paths()
        try:
            payload = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                rows: list[dict[str, str]] = []
                for item in payload:
                    if isinstance(item, dict):
                        path_value = item.get("path")
                        created_at = item.get("created_at")
                        name_value = item.get("name")
                        if isinstance(path_value, str) and isinstance(created_at, str):
                            row: dict[str, str] = {
                                "path": path_value,
                                "created_at": created_at,
                            }
                            if isinstance(name_value, str) and name_value.strip():
                                row["name"] = name_value.strip()
                            rows.append(row)
                return rows
        except Exception:
            pass
        return []

    def _write_index(self, rows: list[dict[str, str]]) -> None:
        self.metadata_path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self._enforce_permissions(self.metadata_path)

    def list_conversations(self) -> list[dict[str, str]]:
        """List known conversation snapshots, newest first."""
        rows = self._read_index()
        return sorted(rows, key=lambda item: item["created_at"], reverse=True)

    def save_conversation(
        self,
        messages: list[dict[str, str]],
        model: str,
        name: str = "",
    ) -> Path:
        """Persist a conversation and update metadata index."""
        if not self.enabled:
            raise PersistenceDisabledError("Persistence is disabled in configuration.")

        self._ensure_paths()
        now = datetime.now(UTC)
        created_at = now.isoformat()
        filename = f"{now.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}.json"
        target = self.directory / filename

        payload: dict[str, Any] = {
            "created_at": created_at,
            "model": model,
            "messages": messages,
        }
        normalized_name = name.strip()
        if normalized_name:
            payload["name"] = normalized_name
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self._enforce_permissions(target)

        index_rows = self._read_index()
        index_row: dict[str, str] = {"path": str(target), "created_at": created_at}
        if normalized_name:
            index_row["name"] = normalized_name
        index_rows.append(index_row)
        self._write_index(index_rows)
        return target

    def load_conversation(self, file_path: Path) -> dict[str, Any]:
        """Load a conversation payload from a specific snapshot path."""
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise PersistenceFormatError("Conversation payload is invalid.")
        return payload

    def load_latest_conversation(self) -> dict[str, Any] | None:
        """Load the most recent conversation from metadata index."""
        rows = self.list_conversations()
        if not rows:
            return None
        target = self._resolve_snapshot_path(rows[0]["path"])
        if target is None:
            return None
        if not target.exists():
            return None
        return self.load_conversation(target)

    def export_markdown(self, messages: list[dict[str, str]], model: str) -> Path:
        """Export conversation transcript to markdown."""
        if not self.enabled:
            raise PersistenceDisabledError("Persistence is disabled in configuration.")
        self._ensure_paths()

        filename = f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-export.md"
        target = self.directory / filename
        lines = [f"# Conversation Export ({model})", ""]
        for message in messages:
            role = str(message.get("role", "assistant")).capitalize()
            content = str(message.get("content", "")).strip()
            lines.append(f"## {role}")
            lines.append("")
            lines.append(content)
            lines.append("")
        target.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        self._enforce_permissions(target)
        return target
