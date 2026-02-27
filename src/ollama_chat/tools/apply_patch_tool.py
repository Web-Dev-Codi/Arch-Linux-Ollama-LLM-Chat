from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..support import lsp_client

from .base import ParamsSchema, Tool, ToolContext, ToolResult
from .utils import generate_unified_diff, notify_file_change, check_file_safety


class ApplyPatchParams(ParamsSchema):
    patch_text: str


@dataclass
class _AddHunk:
    path: str
    content: str


@dataclass
class _DeleteHunk:
    path: str


@dataclass
class _UpdateHunk:
    path: str
    chunks: list[tuple[str, str]]  # (old_text, new_text)
    move_to: str | None = None


_HUNK_MARKER = "*** "
_BEGIN = "*** Begin Patch"
_END = "*** End Patch"
_ADD = "*** Add File:"
_UPDATE = "*** Update File:"
_DELETE = "*** Delete File:"
_MOVE_TO = "*** Move to:"


def _extract_between(text: str, start: str, end: str) -> str:
    try:
        s = text.index(start)
        e = text.rindex(end)
        return text[s + len(start) : e]
    except ValueError:
        return text


def _parse_patch(text: str) -> list[Any]:
    body = _extract_between(text, _BEGIN, _END)
    lines = body.splitlines()
    i = 0
    hunks: list[Any] = []

    def _collect_until_header(start: int) -> tuple[list[str], int]:
        out: list[str] = []
        j = start
        while j < len(lines):
            if lines[j].startswith(_HUNK_MARKER) and not lines[j].startswith("@@"):
                break
            out.append(lines[j])
            j += 1
        return out, j

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith(_ADD):
            path = line[len(_ADD) :].strip()
            content_lines, i = _collect_until_header(i + 1)
            content: list[str] = []
            for ln in content_lines:
                if ln.startswith("+"):
                    content.append(ln[1:])
                else:
                    # Allow raw lines as well (defensive)
                    content.append(ln)
            hunks.append(
                _AddHunk(
                    path=path,
                    content="\n".join(content) + ("\n" if content_lines else ""),
                )
            )
            continue
        if line.startswith(_DELETE):
            path = line[len(_DELETE) :].strip()
            hunks.append(_DeleteHunk(path=path))
            i += 1
            continue
        if line.startswith(_UPDATE):
            path = line[len(_UPDATE) :].strip()
            move_to: str | None = None
            j = i + 1
            # Optional move to next line
            if j < len(lines) and lines[j].startswith(_MOVE_TO):
                move_to = lines[j][len(_MOVE_TO) :].strip()
                j += 1
            chunks: list[tuple[str, str]] = []
            cur_old: list[str] = []
            cur_new: list[str] = []
            in_chunk = False
            while j < len(lines):
                s = lines[j]
                if s.startswith(_HUNK_MARKER) and not s.startswith("@@"):
                    break
                if s.startswith("@@"):
                    # start new chunk
                    if in_chunk and (cur_old or cur_new):
                        chunks.append(("\n".join(cur_old), "\n".join(cur_new)))
                    cur_old, cur_new = [], []
                    in_chunk = True
                    j += 1
                    continue
                if not in_chunk:
                    j += 1
                    continue
                if s.startswith(" "):
                    cur_old.append(s[1:])
                    cur_new.append(s[1:])
                elif s.startswith("-"):
                    cur_old.append(s[1:])
                elif s.startswith("+"):
                    cur_new.append(s[1:])
                else:
                    # treat as context
                    cur_old.append(s)
                    cur_new.append(s)
                j += 1
            if in_chunk and (cur_old or cur_new):
                chunks.append(("\n".join(cur_old), "\n".join(cur_new)))
            hunks.append(_UpdateHunk(path=path, chunks=chunks, move_to=move_to))
            i = j
            continue
        # Unknown line: skip
        i += 1

    return hunks


def _apply_update_chunks(old: str, chunks: list[tuple[str, str]]) -> str:
    updated = old
    for old_text, new_text in chunks:
        if not old_text and not new_text:
            continue
        # Try exact match first
        if old_text and old_text in updated:
            updated = updated.replace(old_text, new_text, 1)
            continue
        # Try without trailing newline
        if old_text.endswith("\n") and old_text[:-1] in updated:
            updated = updated.replace(old_text[:-1], new_text, 1)
            continue
        # As a last resort, raise error to surface mismatch
        raise RuntimeError(
            "apply_patch verification failed: cannot locate chunk in target file"
        )
    return updated


class ApplyPatchTool(Tool):
    id = "apply_patch"
    params_schema = ApplyPatchParams

    async def execute(self, params: ApplyPatchParams, ctx: ToolContext) -> ToolResult:
        hunks = _parse_patch(params.patch_text)
        if not hunks:
            return ToolResult(
                title="apply_patch",
                output="apply_patch verification failed: no hunks found",
                metadata={"ok": False},
            )

        # Resolve paths and build previews/diffs
        diffs: list[str] = []
        file_list: list[str] = []
        actions: list[tuple[str, Any]] = []  # (action, data)

        for h in hunks:
            if isinstance(h, _AddHunk):
                path = ctx.resolve_path(h.path)
                await check_file_safety(path, ctx, assert_not_modified=False)
                old_content = ""
                new_content = h.content
                diff = generate_unified_diff(old_content, new_content, path)
                diffs.append(diff)
                file_list.append(str(path))
                actions.append(("add", (path, new_content)))
            elif isinstance(h, _DeleteHunk):
                path = ctx.resolve_path(h.path)
                await check_file_safety(path, ctx, assert_not_modified=False)
                old_content = (
                    path.read_text(encoding="utf-8", errors="ignore")
                    if path.exists()
                    else ""
                )
                new_content = ""
                diff = generate_unified_diff(old_content, new_content, path)
                diffs.append(diff)
                file_list.append(str(path))
                actions.append(("delete", (path,)))
            elif isinstance(h, _UpdateHunk):
                src = ctx.resolve_path(h.path)
                await check_file_safety(src, ctx, assert_not_modified=False)
                dst = ctx.resolve_path(h.move_to) if h.move_to else None
                if dst is not None:
                    await check_file_safety(dst, ctx, assert_not_modified=False)
                old_content = (
                    src.read_text(encoding="utf-8", errors="ignore")
                    if src.exists()
                    else ""
                )
                new_content = _apply_update_chunks(old_content, h.chunks)
                diff = generate_unified_diff(old_content, new_content, dst or src)
                diffs.append(diff)
                file_list.append(str(dst or src))
                actions.append(("update", (src, dst, new_content)))

        diff_text = "\n".join(diffs)
        await ctx.ask(
            permission="edit",
            patterns=file_list,
            always=["*"],
            metadata={"diff": diff_text, "files": file_list},
        )

        changed: list[str] = []
        # Apply changes
        for kind, data in actions:
            if kind == "add":
                path, content = data
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                changed.append(f"A {path}")
                try:
                    await notify_file_change(path, "create", ctx)
                except Exception:
                    pass
            elif kind == "delete":
                (path,) = data
                try:
                    path.unlink(missing_ok=True)
                    changed.append(f"D {path}")
                    try:
                        await notify_file_change(path, "delete", ctx)
                    except Exception:
                        pass
                except Exception:
                    changed.append(f"D {path} (failed)")
            elif kind == "update":
                src, dst, content = data
                target = dst or src
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                if dst and dst != src:
                    try:
                        src.unlink(missing_ok=True)
                    except Exception:
                        pass
                changed.append(f"M {target}")
                try:
                    await notify_file_change(target, "change", ctx)
                except Exception:
                    pass

        output = "\n".join(changed) if changed else "No changes applied."
        return ToolResult(
            title="apply_patch",
            output=output,
            metadata={"ok": True, "changed": len(changed), "event": "change"},
        )
