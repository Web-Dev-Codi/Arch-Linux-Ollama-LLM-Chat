from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
import os
from pathlib import Path
from typing import Any

_state: dict[str, dict[str, datetime]] = {}
_locks: dict[str, asyncio.Lock] = {}


def record_read(session_id: str, filepath: str | os.PathLike[str]) -> None:
    """Record that session_id has read filepath at the current time."""
    path = str(Path(filepath).resolve())
    _state.setdefault(session_id, {})[path] = datetime.utcnow()


def get_read_time(session_id: str, filepath: str | os.PathLike[str]) -> datetime | None:
    path = str(Path(filepath).resolve())
    return _state.get(session_id, {}).get(path)


async def assert_read(session_id: str, filepath: str | os.PathLike[str]) -> None:
    """
    Guard against overwriting files that have not been read in this session.

    If OLLAMATERM_DISABLE_FILETIME_CHECK is set, the check is skipped.
    """
    if os.environ.get("OLLAMATERM_DISABLE_FILETIME_CHECK"):
        return

    path = str(Path(filepath).resolve())
    read_time = get_read_time(session_id, path)
    if read_time is None:
        raise RuntimeError(f"You must read file {path!r} before overwriting it.")

    try:
        mtime = os.stat(path).st_mtime_ns / 1e9
    except FileNotFoundError:
        # New file, allow creation.
        return

    # Allow small tolerance for filesystem timestamp granularity.
    if mtime > read_time.timestamp() + 0.05:
        raise RuntimeError(f"File {path!r} has been modified since last read.")


async def with_lock(filepath: str | os.PathLike[str], fn: Callable[[], Any]):
    """Serialize concurrent writes to the same file."""
    key = str(Path(filepath).resolve())
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        return await fn()
