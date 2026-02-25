from __future__ import annotations

from pydantic import BaseModel

from .base import ParamsSchema, Tool, ToolContext, ToolResult
from .edit_tool import EditParams, EditTool


class EditOp(BaseModel):
    file_path: str
    old_string: str
    new_string: str
    replace_all: bool = False


class MultiEditParams(ParamsSchema):
    file_path: str
    edits: list[EditOp]


class MultiEditTool(Tool):
    id = "multiedit"
    params_schema = MultiEditParams

    async def execute(self, params: MultiEditParams, ctx: ToolContext) -> ToolResult:
        if not params.edits:
            return ToolResult(
                title=params.file_path,
                output="No edits provided.",
                metadata={"ok": False},
            )
        editor = EditTool()
        results = []
        last_output = ""
        for op in params.edits:
            result = await editor.execute(
                EditParams(
                    file_path=params.file_path,
                    old_string=op.old_string,
                    new_string=op.new_string,
                    replace_all=op.replace_all,
                ),
                ctx,
            )
            results.append(result)
            last_output = result.output
        return ToolResult(
            title=params.file_path,
            output=last_output,
            metadata={"results": [r.metadata for r in results]},
        )
