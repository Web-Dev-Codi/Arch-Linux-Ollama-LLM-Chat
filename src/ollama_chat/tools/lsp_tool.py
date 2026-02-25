from __future__ import annotations

from pathlib import Path

from support import lsp_client

from .base import ParamsSchema, Tool, ToolContext, ToolResult
from .external_directory import assert_external_directory

OPERATIONS = [
    "goToDefinition",
    "findReferences",
    "hover",
    "documentSymbol",
    "workspaceSymbol",
    "goToImplementation",
    "prepareCallHierarchy",
    "incomingCalls",
    "outgoingCalls",
]


class LspParams(ParamsSchema):
    operation: str
    file_path: str
    line: int
    character: int


class LspTool(Tool):
    id = "lsp"
    params_schema = LspParams

    async def execute(self, params: LspParams, ctx: ToolContext) -> ToolResult:
        file_path = str(Path(params.file_path).expanduser().resolve())
        await assert_external_directory(ctx, file_path)
        await ctx.ask(permission="lsp", patterns=["*"], always=["*"], metadata={})

        if params.operation not in OPERATIONS:
            return ToolResult(
                title="lsp",
                output=f"Unsupported operation: {params.operation}",
                metadata={"ok": False},
            )

        uri = Path(file_path).as_uri()
        position = {"line": max(0, params.line - 1), "character": max(0, params.character - 1)}

        if not lsp_client.has_clients_for(file_path):
            return ToolResult(
                title="lsp",
                output="No LSP server available for this file type.",
                metadata={"ok": False},
            )

        # This standalone implementation does not wire a real LSP; return a stub response.
        return ToolResult(
            title=f"lsp: {params.operation}",
            output=f"No results found for {params.operation}",
            metadata={"uri": uri, "position": position},
        )
