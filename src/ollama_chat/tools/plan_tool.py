from __future__ import annotations

from ..support import question_service
from .base import ParamsSchema, Tool, ToolContext, ToolResult


class PlanExitTool(Tool):
    id = "plan_exit"
    params_schema = ParamsSchema  # no parameters

    async def execute(self, params: ParamsSchema, ctx: ToolContext) -> ToolResult:  # noqa: ARG002 - unused params
        # Ask user to confirm switching to build agent.
        questions = [
            {
                "question": "Plan is complete. Switch to build agent?",
                "header": "Build Agent",
                "options": [
                    {"label": "Yes", "description": "Switch to build agent"},
                    {"label": "No", "description": "Stay with plan agent"},
                ],
                "custom": False,
            }
        ]
        answers = await question_service.ask(session_id=ctx.session_id, questions=questions)
        if answers and answers[0] and answers[0][0] == "No":
            return ToolResult(
                title="Plan Mode",
                output="User chose to stay in plan mode.",
                metadata={"switched": False},
            )

        # In a full runtime, we'd emit a synthetic user message to trigger build agent.
        return ToolResult(
            title="Switching to build agent",
            output=(
                "User approved switching to build agent. Wait for further instructions."
            ),
            metadata={"switched": True},
        )
