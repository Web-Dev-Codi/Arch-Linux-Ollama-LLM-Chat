from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path

from ..support import file_time as file_time_service
from ..support import lsp_client
from .abstracts import FileOperationTool
from .base import Attachment, ParamsSchema, ToolContext, ToolResult

DEFAULT_READ_LIMIT = 2000
MAX_LINE_LENGTH = 2000
MAX_BYTES = 50 * 1024  # 50 KB


class ReadParams(ParamsSchema):
    file_path: str
    offset: int | None = None  # 1-indexed; default 1
    limit: int | None = None  # default DEFAULT_READ_LIMIT


class ReadTool(FileOperationTool):
    id = "read"
    params_schema = ReadParams

    async def perform_operation(
        self, file_path: Path, params: ReadParams, ctx: ToolContext
    ) -> ToolResult:
        if not file_path.exists():
            parent = file_path.parent
            name = file_path.name.lower()
            suggestions: list[str] = []
            try:
                for entry in parent.iterdir():
                    ename = entry.name.lower()
                    if name in ename or ename in name:
                        suggestions.append(str(entry))
                        if len(suggestions) >= 3:
                            break
            except Exception:
                pass
            raise FileNotFoundError(
                f"File not found: {str(file_path)}. Suggestions: {', '.join(suggestions) if suggestions else 'none'}"
            )

        # If directory: list entries with offset/limit
        if file_path.is_dir():
            entries = sorted(os.listdir(file_path))
            off = max(0, (params.offset or 1) - 1)
            lim = params.limit or DEFAULT_READ_LIMIT
            shown = entries[off : off + lim]
            lines = []
            for name in shown:
                p = file_path / name
                suffix = "/" if p.is_dir() else ""
                lines.append(name + suffix)
            content = (
                f"<path>{str(file_path)}</path>\n<type>directory</type>\n<entries>\n"
                + "\n".join(lines)
                + "\n</entries>"
            )
            return ToolResult(
                title=str(file_path),
                output=content,
                metadata={"ok": True},
            )

        # MIME and attachment handling for images and PDFs
        mime, _ = mimetypes.guess_type(str(file_path))
        try:
            if (
                mime
                and (mime.startswith("image/") or mime == "application/pdf")
                and not mime.endswith("svg+xml")
                and "vnd.fastbidsheet" not in mime
            ):
                data = file_path.read_bytes()
                b64 = base64.b64encode(data).decode()
                attachment = Attachment(
                    type="file", mime=mime, url=f"data:{mime};base64,{b64}"
                )
                return ToolResult(
                    title=str(file_path),
                    output="Binary attachment returned.",
                    metadata={"ok": True, "attachment": True},
                    attachments=[attachment],
                )
        except Exception:
            # Fallback to text flow
            pass

        # Binary detection
        try:
            with open(file_path, "rb") as bf:
                sample = bf.read(4096)
            if b"\x00" in sample:
                raise RuntimeError("Cannot read binary file")
            non_printable = sum(1 for b in sample if b < 9 or (13 < b < 32))
            if len(sample) > 0 and non_printable / len(sample) > 0.3:
                raise RuntimeError("Cannot read binary file")
        except Exception as exc:
            return ToolResult(
                title=str(file_path), output=str(exc), metadata={"ok": False}
            )

        # Read text with offset/limit and byte cap
        offset = max(1, int(params.offset or 1))
        limit = max(1, int(params.limit or DEFAULT_READ_LIMIT))
        out_lines: list[str] = []
        total_bytes = 0
        total_lines = 0
        start_line = offset
        end_line = offset - 1
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                for i, raw in enumerate(f, start=1):
                    total_lines = i
                    if i < offset:
                        continue
                    if len(out_lines) >= limit or total_bytes > MAX_BYTES:
                        break
                    line = raw.rstrip("\n")
                    if len(line) > MAX_LINE_LENGTH:
                        line = line[:MAX_LINE_LENGTH] + "... (line truncated)"
                    out_lines.append(f"{i}: {line}")
                    total_bytes += len(line.encode("utf-8", errors="ignore"))
                    end_line = i
        except Exception as exc:
            return ToolResult(
                title=str(file_path), output=str(exc), metadata={"ok": False}
            )

        summary: str
        if end_line < total_lines:
            summary = f"(Showing lines {start_line}-{end_line} of total {total_lines})"
        else:
            summary = f"(End of file - total {total_lines} lines)"

        content = (
            f"<path>{str(file_path)}</path>\n<type>file</type>\n<content>\n"
            + "\n".join(out_lines)
            + f"\n{summary}\n</content>"
        )

        # Post-read hooks
        try:
            file_time_service.record_read(ctx.session_id, str(file_path))
        except Exception:
            pass
        try:
            lsp_client.touch_file(str(file_path), notify=False)
        except Exception:
            pass

        return ToolResult(title=str(file_path), output=content, metadata={"ok": True})
