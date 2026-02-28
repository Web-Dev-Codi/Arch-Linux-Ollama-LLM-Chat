from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from ..support import bus
from .base import ParamsSchema, Tool, ToolContext, ToolResult

try:  # Optional dependency
    import aiosqlite  # type: ignore
except Exception:  # pragma: no cover - optional
    aiosqlite = None  # type: ignore[assignment]

DB_PATH = Path.home() / ".local" / "share" / "ollamaterm" / "todo.sqlite3"


async def _ensure_schema():
    if aiosqlite is None:  # pragma: no cover - optional
        return
    async with aiosqlite.connect(DB_PATH) as db:  # type: ignore[attribute-defined-outside-init]
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL,
                priority TEXT NOT NULL,
                position INTEGER NOT NULL
            )
            """
        )
        await db.commit()


class TodoItem(BaseModel):
    content: str
    status: str  # pending | in_progress | completed | cancelled
    priority: str  # high | medium | low


class TodoWriteParams(ParamsSchema):
    todos: list[TodoItem]


class TodoReadParams(ParamsSchema):
    pass


class TodoWriteTool(Tool):
    id = "todowrite"
    params_schema = TodoWriteParams

    async def execute(self, params: TodoWriteParams, ctx: ToolContext) -> ToolResult:
        await ctx.ask(permission="todowrite", patterns=["*"], always=["*"], metadata={})
        if aiosqlite is None:  # pragma: no cover - optional
            return ToolResult(title="todowrite", output="aiosqlite is not installed.", metadata={"ok": False})
        await _ensure_schema()
        async with aiosqlite.connect(DB_PATH) as db:  # type: ignore[attribute-defined-outside-init]
            await db.execute("DELETE FROM todos WHERE session_id=?", [ctx.session_id])
            await db.executemany(
                "INSERT INTO todos(session_id,content,status,priority,position) VALUES(?,?,?,?,?)",
                [
                    (ctx.session_id, t.content, t.status, t.priority, i)
                    for i, t in enumerate(params.todos)
                ],
            )
            await db.commit()
        try:
            await bus.bus.publish(
                "todo.updated",
                {
                    "session_id": ctx.session_id,
                    "todos": [t.model_dump() for t in params.todos],
                },
            )
        except Exception:
            pass
        remaining = len([t for t in params.todos if t.status != "completed"])
        return ToolResult(
            title=f"{remaining} todos",
            output=json.dumps([t.model_dump() for t in params.todos], indent=2),
            metadata={"count": len(params.todos)},
        )


class TodoReadTool(Tool):
    id = "todoread"
    params_schema = TodoReadParams

    async def execute(self, params: TodoReadParams, ctx: ToolContext) -> ToolResult:  # noqa: ARG002 - unused params
        await ctx.ask(permission="todoread", patterns=["*"], always=["*"], metadata={})
        if aiosqlite is None:  # pragma: no cover - optional
            return ToolResult(title="todoread", output="aiosqlite is not installed.", metadata={"ok": False})
        await _ensure_schema()
        async with aiosqlite.connect(DB_PATH) as db:  # type: ignore[attribute-defined-outside-init]
            cursor = await db.execute(
                "SELECT content,status,priority FROM todos WHERE session_id=? ORDER BY position",
                [ctx.session_id],
            )
            rows = await cursor.fetchall()
        todos = [
            {"content": r[0], "status": r[1], "priority": r[2]}  # type: ignore[index]
            for r in rows
        ]
        return ToolResult(
            title="todos",
            output=json.dumps(todos, indent=2),
            metadata={"count": len(todos)},
        )
