from __future__ import annotations

from difflib import unified_diff
from pathlib import Path

from support import bus, lsp_client
from support import file_time as file_time_service

from .base import ParamsSchema, Tool, ToolContext, ToolResult
from .external_directory import assert_external_directory


class EditParams(ParamsSchema):
    file_path: str
    old_string: str
    new_string: str
    replace_all: bool = False


class EditTool(Tool):
    id = "edit"
    params_schema = EditParams

    async def execute(self, params: EditParams, ctx: ToolContext) -> ToolResult:
        if params.old_string == params.new_string:
            return ToolResult(title=params.file_path, output="No changes to apply.", metadata={"ok": False})

        file_path = Path(params.file_path).expanduser().resolve()
        await assert_external_directory(ctx, str(file_path))

        # Special case: create new file when old_string is empty
        if params.old_string == "":
            diff_lines = list(
                unified_diff([], params.new_string.splitlines(), fromfile=str(file_path), tofile=str(file_path), lineterm="")
            )
            diff_str = "\n".join(diff_lines)
            await ctx.ask(
                permission="edit",
                patterns=[str(file_path)],
                always=["*"],
                metadata={"filepath": str(file_path), "diff": diff_str},
            )
            def _write() -> None:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(params.new_string, encoding="utf-8")
            await file_time_service.with_lock(str(file_path), _write)
            try:
                await bus.bus.publish("file.edited", {"file": str(file_path)})
                await bus.bus.publish("file.watcher.updated", {"file": str(file_path), "event": "add"})
            except Exception:
                pass
            try:
                file_time_service.record_read(ctx.session_id, str(file_path))
            except Exception:
                pass
            try:
                lsp_client.touch_file(str(file_path), notify=True)
            except Exception:
                pass
            return ToolResult(title=str(file_path), output="File created.", metadata={"created": True})

        # Otherwise, require prior read
        try:
            await file_time_service.assert_read(ctx.session_id, str(file_path))
        except Exception as exc:
            return ToolResult(title=str(file_path), output=str(exc), metadata={"ok": False})

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return ToolResult(title=str(file_path), output=str(exc), metadata={"ok": False})

        # Simple replacement strategy: exact text, optionally first occurrence only
        occurrences = content.count(params.old_string)
        if occurrences == 0:
            return ToolResult(
                title=str(file_path),
                output="Could not find oldString in the file. Make sure to read the file and pass the exact text.",
                metadata={"ok": False},
            )
        if not params.replace_all and occurrences > 1:
            return ToolResult(
                title=str(file_path),
                output="Found multiple matches for oldString; set replace_all=true to replace them all.",
                metadata={"ok": False},
            )

        new_content = (
            content.replace(params.old_string, params.new_string)
            if params.replace_all
            else content.replace(params.old_string, params.new_string, 1)
        )

        diff_lines = list(
            unified_diff(
                content.splitlines(),
                new_content.splitlines(),
                fromfile=str(file_path),
                tofile=str(file_path),
                lineterm="",
            )
        )
        diff_str = "\n".join(diff_lines)
        await ctx.ask(
            permission="edit",
            patterns=[str(file_path)],
            always=["*"],
            metadata={"filepath": str(file_path), "diff": diff_str},
        )

        def _write() -> None:
            file_path.write_text(new_content, encoding="utf-8")
        await file_time_service.with_lock(str(file_path), _write)

        try:
            await bus.bus.publish("file.edited", {"file": str(file_path)})
            await bus.bus.publish("file.watcher.updated", {"file": str(file_path), "event": "change"})
        except Exception:
            pass
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
            errors = [d for d in diagnostics.get(str(file_path), []) if d.get("severity") == 1]
            output = f"Applied {'all' if params.replace_all else 'one'} replacement successfully."
            if errors:
                output += "\n<diagnostics>\n" + "\n".join(d.get("message", "") for d in errors[:20]) + "\n</diagnostics>"
        except Exception:
            output = f"Applied {'all' if params.replace_all else 'one'} replacement successfully."

        return ToolResult(title=str(file_path), output=output, metadata={"changed": True})
