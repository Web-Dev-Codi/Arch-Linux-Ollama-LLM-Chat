from __future__ import annotations

from pydantic import BaseModel

from ..support import question_service

from .base import ParamsSchema, Tool, ToolContext, ToolResult


class QuestionOption(BaseModel):
    label: str
    description: str


class QuestionInfo(BaseModel):
    question: str
    header: str
    options: list[QuestionOption]
    multiple: bool = False
    custom: bool = True


class QuestionParams(ParamsSchema):
    questions: list[QuestionInfo]


class QuestionTool(Tool):
    id = "question"
    params_schema = QuestionParams
    description = "Suspends execution to ask the user structured questions."

    async def execute(self, params: QuestionParams, ctx: ToolContext) -> ToolResult:
        answers = await question_service.ask(
            session_id=ctx.session_id,
            questions=[q.model_dump() for q in params.questions],
            tool={"message_id": ctx.message_id, "call_id": ctx.call_id},
        )
        pairs: list[str] = []
        for q, ans in zip(params.questions, answers):
            pairs.append(f'"{q.question}"="{", ".join(ans)}"')
        output = (
            "User has answered your questions: "
            + "; ".join(pairs)
            + ". You can now continue..."
        )
        return ToolResult(
            title="Question Answered",
            output=output,
            metadata={"answers": answers},
        )
