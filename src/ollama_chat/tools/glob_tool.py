from __future__ import annotations

import asyncio
import os
from pathlib import Path

from ..support import ripgrep

from .abstracts import SearchTool
from .base import ParamsSchema, ToolContext

MAX_RESULTS = 100


class GlobParams(ParamsSchema):
    pattern: str
    path: str | None = None  # default: project directory


class GlobTool(SearchTool):
    id = "glob"
    params_schema = GlobParams

    async def perform_search(
        self, path: Path, params: GlobParams, ctx: ToolContext
    ) -> str:
        pattern = params.pattern
        search_root = path

        files: list[str] = []
        # Try ripgrep first
        try:
            rg = await ripgrep.filepath()
            proc = await asyncio.create_subprocess_exec(
                rg,
                "--files",
                "--glob",
                pattern,
                str(search_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            if proc.stdout is not None:
                raw = await proc.stdout.read()
                files = [f for f in raw.decode().split("\n") if f]
        except Exception:
            files = []

        if not files:
            # Fallback to Python globbing
            try:
                for p in search_root.rglob(pattern):
                    files.append(str(p))
            except Exception:
                pass

        truncated = False
        if len(files) > MAX_RESULTS:
            files = files[:MAX_RESULTS]
            truncated = True

        # Sort by mtime desc
        try:
            files.sort(key=lambda f: os.stat(f).st_mtime, reverse=True)
        except Exception:
            pass

        output = "\n".join(files)
        if truncated:
            output += "\n... results truncated; refine your search pattern."
        return output
