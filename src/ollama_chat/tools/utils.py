"""Common utilities for tool implementations."""

from __future__ import annotations

from difflib import unified_diff
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import ToolContext


async def notify_file_change(
    path: Path,
    event: str,  # "change", "create", "delete"
    ctx: ToolContext,
    *,
    notify_lsp: bool = True,
    record_access: bool = True,
) -> None:
    """Broadcast file change events to all interested parties.

    Replaces 30+ duplicate notification sequences across tools.

    Args:
        path: File that was changed
        event: Type of change (change/create/delete)
        ctx: Tool execution context
        notify_lsp: Whether to notify LSP server
        record_access: Whether to track file access time
    """
    from ..support.bus import bus
    from ..support.file_time import file_time_service
    from ..support.lsp_client import lsp_client

    path_str = str(path)

    # Publish to event bus
    await bus.publish("file.edited", {"file": path_str})
    await bus.publish("file.watcher.updated", {"file": path_str, "event": event})

    # Notify LSP server
    if notify_lsp:
        lsp_client.touch_file(path_str, notify=True)

    # Track access for safety checks
    if record_access and event in ("change", "create"):
        file_time_service.record_read(ctx.session_id, path_str)


def generate_unified_diff(
    old_content: str,
    new_content: str,
    file_path: Path | str,
    *,
    context_lines: int = 3,
) -> str:
    """Generate unified diff between two content strings.

    Replaces 6 duplicate diff generation blocks.

    Args:
        old_content: Original file content
        new_content: Modified file content
        file_path: File being modified (for diff header)
        context_lines: Number of context lines around changes

    Returns:
        Unified diff as string
    """
    diff_lines = list(
        unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=str(file_path),
            tofile=str(file_path),
            lineterm="",
            n=context_lines,
        )
    )
    return "\n".join(diff_lines)


async def check_file_safety(
    path: Path,
    ctx: ToolContext,
    *,
    check_external: bool = True,
    assert_not_modified: bool = False,
) -> None:
    """Perform safety checks before file operation.

    Args:
        path: File to check
        ctx: Tool execution context
        check_external: Whether to check external directory permissions
        assert_not_modified: Whether to verify file hasn't changed since read

    Raises:
        PermissionError: If file access not allowed
        RuntimeError: If file was modified since last read
    """
    from ..support.file_time import file_time_service
    from .external_directory import assert_external_directory

    # Check external directory permissions
    if check_external:
        await assert_external_directory(ctx, str(path))

    # Verify file hasn't been modified
    if assert_not_modified:
        await file_time_service.assert_read(ctx.session_id, str(path))
