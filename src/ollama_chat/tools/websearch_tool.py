from __future__ import annotations

import json

from .base import ParamsSchema, Tool, ToolContext, ToolResult

EXA_BASE_URL = "https://mcp.exa.ai"
EXA_ENDPOINT = "/mcp"


class WebSearchParams(ParamsSchema):
    query: str
    num_results: int | None = 8
    livecrawl: str | None = None  # "fallback" | "preferred"
    type: str | None = "auto"  # "auto" | "fast" | "deep"
    context_max_characters: int | None = None


class WebSearchTool(Tool):
    id = "websearch"
    params_schema = WebSearchParams

    async def execute(self, params: WebSearchParams, ctx: ToolContext) -> ToolResult:
        await ctx.ask(
            permission="websearch",
            patterns=[params.query],
            always=["*"],
            metadata={"query": params.query},
        )

        try:
            import httpx  # noqa: WPS433
        except Exception as exc:  # pragma: no cover - optional dep
            return ToolResult(title="websearch", output=f"Missing dependency: {exc}", metadata={"ok": False})

        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "web_search_exa",
                "arguments": {
                    "query": params.query,
                    "type": (params.type or "auto"),
                    "numResults": int(params.num_results or 8),
                    "livecrawl": (params.livecrawl or "fallback"),
                    "contextMaxCharacters": params.context_max_characters,
                },
            },
        }
        headers = {
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
        }
        url = EXA_BASE_URL + EXA_ENDPOINT
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(url, headers=headers, content=json.dumps(body))
                text = resp.text
        except Exception as exc:  # pragma: no cover - network
            return ToolResult(title="websearch", output=f"Search failed: {exc}", metadata={"ok": False})

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
            result_text = "No search results found."
        return ToolResult(title="websearch", output=result_text, metadata={})
