"""Conversation persistence utilities for save/load/export workflows."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4


class ConversationPersistence:
    """Manage on-disk conversation snapshots and metadata index."""

    def __init__(self, enabled: bool, directory: str, metadata_path: str) -> None:
        self.enabled = enabled
        self.directory = Path(directory).expanduser()
        self.metadata_path = Path(metadata_path).expanduser()

    def _enforce_private_permissions(self, path: Path) -> None:
        if os.name != "posix":
            return
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def _ensure_paths(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.metadata_path.exists():
            self.metadata_path.write_text("[]", encoding="utf-8")
        self._enforce_private_permissions(self.metadata_path)

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
                        if isinstance(path_value, str) and isinstance(created_at, str):
                            rows.append({"path": path_value, "created_at": created_at})
                return rows
        except Exception:
            return []
        return []

    def _write_index(self, rows: list[dict[str, str]]) -> None:
        self.metadata_path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self._enforce_private_permissions(self.metadata_path)

    def list_conversations(self) -> list[dict[str, str]]:
        """List known conversation snapshots, newest first."""
        rows = self._read_index()
        return sorted(rows, key=lambda item: item["created_at"], reverse=True)

    def save_conversation(self, messages: list[dict[str, str]], model: str) -> Path:
        """Persist a conversation and update metadata index."""
        if not self.enabled:
            raise RuntimeError("Persistence is disabled in configuration.")

        self._ensure_paths()
        created_at = datetime.now(timezone.utc).isoformat()
        filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}.json"
        target = self.directory / filename

        payload: dict[str, Any] = {
            "created_at": created_at,
            "model": model,
            "messages": messages,
        }
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self._enforce_private_permissions(target)

        index_rows = self._read_index()
        index_rows.append({"path": str(target), "created_at": created_at})
        self._write_index(index_rows)
        return target

    def load_conversation(self, file_path: Path) -> dict[str, Any]:
        """Load a conversation payload from a specific snapshot path."""
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Conversation payload is invalid.")
        return payload

    def load_latest_conversation(self) -> dict[str, Any] | None:
        """Load the most recent conversation from metadata index."""
        rows = self.list_conversations()
        if not rows:
            return None
        target = Path(rows[0]["path"]).expanduser()
        if not target.exists():
            return None
        return self.load_conversation(target)

    def export_markdown(self, messages: list[dict[str, str]], model: str) -> Path:
        """Export conversation transcript to markdown."""
        if not self.enabled:
            raise RuntimeError("Persistence is disabled in configuration.")
        self._ensure_paths()

        filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-export.md"
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
        self._enforce_private_permissions(target)
        return target
