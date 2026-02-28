"""Persistent model capability cache."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import logging
from pathlib import Path
import time

LOGGER = logging.getLogger(__name__)


@dataclass
class ModelCapabilityCache:
    """Cached capability metadata for a specific model."""

    model_name: str
    supports_tools: bool
    supports_vision: bool
    supports_thinking: bool
    raw_capabilities: list[str]
    timestamp: float  # Unix timestamp of when cached

    def is_stale(self, max_age_seconds: int = 86400) -> bool:
        """Check if cache is older than max_age (default: 24 hours)."""
        return (time.time() - self.timestamp) > max_age_seconds


class CapabilityPersistence:
    """Manage persistent capability cache across app restarts."""

    def __init__(self, cache_file: Path | None = None) -> None:
        if cache_file is None:
            from .config import ensure_config_dir

            config_dir = ensure_config_dir()
            cache_file = config_dir / "model_capabilities.json"

        self._cache_file = cache_file
        self._cache: dict[str, ModelCapabilityCache] = {}
        self._load()

    def _load(self) -> None:
        """Load cache from disk."""
        if not self._cache_file.exists():
            return

        try:
            with open(self._cache_file, encoding="utf-8") as f:
                data = json.load(f)

            for model_name, entry in data.items():
                try:
                    self._cache[model_name] = ModelCapabilityCache(
                        model_name=entry["model_name"],
                        supports_tools=entry["supports_tools"],
                        supports_vision=entry["supports_vision"],
                        supports_thinking=entry["supports_thinking"],
                        raw_capabilities=entry["raw_capabilities"],
                        timestamp=entry["timestamp"],
                    )
                except (KeyError, TypeError) as exc:
                    LOGGER.warning(
                        "capability_cache.load.entry_invalid",
                        extra={
                            "event": "capability_cache.load.entry_invalid",
                            "model": model_name,
                            "error": str(exc),
                        },
                    )
        except Exception as exc:
            LOGGER.warning(
                "capability_cache.load.failed",
                extra={
                    "event": "capability_cache.load.failed",
                    "error": str(exc),
                },
            )

    def _save(self) -> None:
        """Save cache to disk."""
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)

            data = {}
            for model_name, cache_entry in self._cache.items():
                data[model_name] = asdict(cache_entry)

            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            LOGGER.warning(
                "capability_cache.save.failed",
                extra={
                    "event": "capability_cache.save.failed",
                    "error": str(exc),
                },
            )

    def get(
        self, model_name: str, max_age_seconds: int = 86400
    ) -> ModelCapabilityCache | None:
        """Retrieve cached capabilities if fresh."""
        cache = self._cache.get(model_name)
        if cache is None:
            return None

        if cache.is_stale(max_age_seconds):
            return None

        return cache

    def set(self, cache: ModelCapabilityCache) -> None:
        """Store capability cache and persist to disk."""
        self._cache[cache.model_name] = cache
        self._save()

    def invalidate(self, model_name: str) -> None:
        """Remove cached entry for a model."""
        self._cache.pop(model_name, None)
        self._save()

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self._save()
