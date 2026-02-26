from __future__ import annotations

import json

from .base import ParamsSchema, Tool, ToolContext, ToolResult

EXA_BASE_URL = "https://mcp.exa.ai"
EXA_ENDPOINT = "/mcp"


class CodeSearchParams(ParamsSchema):
    query: str
    tokens_num: int = 5000  # 1000–50000


class CodeSearchTool(Tool):
    id = "codesearch"
    params_schema = CodeSearchParams

    async def execute(self, params: CodeSearchParams, ctx: ToolContext) -> ToolResult:
        await ctx.ask(
            permission="codesearch",
            patterns=[params.query],
            always=["*"],
            metadata={"query": params.query, "tokens_num": params.tokens_num},
        )

        try:
            import httpx  # noqa: WPS433
        except Exception as exc:  # pragma: no cover - optional dep
            return ToolResult(title="codesearch", output=f"Missing dependency: {exc}", metadata={"ok": False})

        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "get_code_context_exa",
                "arguments": {
                    "query": params.query,
                    "tokensNum": int(params.tokens_num),
                },
            },
        }
        headers = {
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
        }
        url = EXA_BASE_URL + EXA_ENDPOINT
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, content=json.dumps(body))
                text = resp.text
        except Exception as exc:  # pragma: no cover - network
            return ToolResult(title="codesearch", output=f"Code search failed: {exc}", metadata={"ok": False})

        result_text = None
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                result_text = (
                    data.get("result", {})
                    .get("content", [{"text": ""}])[0]
                    .get("text", "")
                )
                if result_text:
                    break
            except Exception:
                continue
        if not result_text:
            result_text = "No code snippets or documentation found. Try a different query."
        return ToolResult(title="codesearch", output=result_text, metadata={})
