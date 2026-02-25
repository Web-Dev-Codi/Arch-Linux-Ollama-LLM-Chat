from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel

from .base import ParamsSchema, Tool, ToolContext, ToolResult


class ToolCallSpec(BaseModel):
    tool: str
    parameters: dict[str, Any]


class BatchParams(ParamsSchema):
    tool_calls: list[ToolCallSpec]


DISALLOWED = {"batch"}
FILTERED_FROM_SUGGESTIONS = {"invalid", "apply_patch"} | DISALLOWED


class BatchTool(Tool):
    id = "batch"
    params_schema = BatchParams

    async def execute(self, params: BatchParams, ctx: ToolContext) -> ToolResult:
        calls = list(params.tool_calls or [])
        over = 0
        if len(calls) > 25:
            over = len(calls) - 25
            calls = calls[:25]

        # Lazy import to avoid circular dependency at module import time.
        from .registry import get_registry  # noqa: WPS433
        registry = get_registry()

        async def run_one(index: int, call: ToolCallSpec) -> tuple[int, bool, str | None, ToolResult | None]:
            if call.tool in DISALLOWED:
                return index, False, "Tool not allowed in batch", None
            tool = registry.get(call.tool)
            if not tool:
                return index, False, f"Tool not in registry: {call.tool}", None
            part_id = f"part_{index}"
            try:
                result = await tool.run(call.parameters, ctx.with_call_id(part_id))
                return index, True, None, result
            except Exception as exc:  # noqa: BLE001
                return index, False, str(exc), None

        tasks = [run_one(i, call) for i, call in enumerate(calls)]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        ok_count = sum(1 for _, ok, _, _ in results if ok)
        fail_count = len(results) - ok_count
        attachments = []
        for _, ok, _, res in results:
            if ok and res is not None:
                attachments.extend(res.attachments)

        if fail_count == 0:
            summary = f"All {ok_count} tools executed successfully."
        else:
            summary = f"Executed {ok_count}/{len(results)} tools. {fail_count} failed."
        if over:
            summary += f" Skipped {over} additional call(s)."

        return ToolResult(title="batch", output=summary, metadata={"ok": fail_count == 0}, attachments=attachments)
