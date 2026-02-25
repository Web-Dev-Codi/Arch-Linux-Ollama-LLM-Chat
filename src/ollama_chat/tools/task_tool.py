from __future__ import annotations

import uuid

from .base import ParamsSchema, Tool, ToolContext, ToolResult


class TaskParams(ParamsSchema):
    description: str
    prompt: str
    subagent_type: str
    task_id: str | None = None
    command: str | None = None


class TaskTool(Tool):
    id = "task"
    params_schema = TaskParams

    async def execute(self, params: TaskParams, ctx: ToolContext) -> ToolResult:
        if not ctx.extra.get("bypassAgentCheck"):
            await ctx.ask(
                permission="task",
                patterns=[params.subagent_type],
                always=["*"],
                metadata={"description": params.description, "command": params.command or ""},
            )

        # Minimal standalone behavior: generate or reuse a task_id and echo the prompt
        task_id = params.task_id or str(uuid.uuid4())
        ctx.metadata(
            title=params.description,
            metadata={"session_id": task_id, "agent": params.subagent_type},
        )
        text = params.prompt.strip()
        output = f"task_id: {task_id}\n\n<task_result>\n{text}\n</task_result>"
        return ToolResult(title=params.description, output=output, metadata={"task_id": task_id})
