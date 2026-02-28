from __future__ import annotations

from pathlib import Path

from ..support import file_time as file_time_service
from ..support import lsp_client
from .abstracts import FileOperationTool
from .base import ParamsSchema, ToolContext, ToolResult
from .utils import generate_unified_diff


class WriteParams(ParamsSchema):
    file_path: str
    content: str


class WriteTool(FileOperationTool):
    id = "write"
    params_schema = WriteParams

    async def perform_operation(
        self, file_path: Path, params: WriteParams, ctx: ToolContext
    ) -> ToolResult:
        exists = file_path.exists()
        old_content = ""
        if exists:
            old_content = file_path.read_text(encoding="utf-8", errors="replace")

        diff_str = generate_unified_diff(old_content, params.content, file_path)
        await ctx.ask(
            permission="edit",
            patterns=[str(file_path)],
            always=["*"],
            metadata={"filepath": str(file_path), "diff": diff_str},
        )

        def _write() -> None:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(params.content, encoding="utf-8")

        # Serialize concurrent writes
        await file_time_service.with_lock(str(file_path), _write)

        try:
            file_time_service.record_read(ctx.session_id, str(file_path))
        except Exception:
            pass

        try:
            lsp_client.touch_file(str(file_path), notify=True)
        except Exception:
            pass

        # LSP diagnostics
        try:
            diagnostics = lsp_client.get_diagnostics()
            errors = [
                d for d in diagnostics.get(str(file_path), []) if d.get("severity") == 1
            ]
            other_files = [
                (p, [d for d in ds if d.get("severity") == 1])
                for p, ds in diagnostics.items()
                if p != str(file_path)
            ]
            other_files = [(p, es) for p, es in other_files if es][:5]
            output = "Wrote file successfully."
            if errors:
                output += (
                    "\n<diagnostics>\n"
                    + "\n".join(d.get("message", "") for d in errors[:20])
                    + "\n</diagnostics>"
                )
            for p, es in other_files:
                output += (
                    f'\n<diagnostics file="{p}">\n'
                    + "\n".join(d.get("message", "") for d in es[:20])
                    + "\n</diagnostics>"
                )
        except Exception:
            output = "Wrote file successfully."

        return ToolResult(
            title=str(file_path),
            output=output,
            metadata={"ok": True, "changed": True, "event": "change" if exists else "create"},
        )
