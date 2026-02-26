from __future__ import annotations

from .base import ParamsSchema, Tool, ToolContext, ToolResult


class InvalidParams(ParamsSchema):
    tool: str
    error: str


class InvalidTool(Tool):
    id = "invalid"
    description = "Catches malformed tool calls. Never explicitly invoked."
    params_schema = InvalidParams

    async def execute(self, params: InvalidParams, ctx: ToolContext) -> ToolResult:  # noqa: D401 - simple
        return ToolResult(
            title="Invalid Tool",
            output=(
                f"The arguments provided to the tool {params.tool!r} are invalid: "
                f"{params.error}"
            ),
            metadata={"ok": False},
        )
