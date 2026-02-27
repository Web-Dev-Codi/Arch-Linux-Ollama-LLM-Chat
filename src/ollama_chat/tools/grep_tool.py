from __future__ import annotations

import os
from pathlib import Path
import re

from .abstracts import SearchTool
from .base import ParamsSchema, ToolContext

MAX_LINE_LENGTH = 2000
MAX_RESULTS = 100


class GrepParams(ParamsSchema):
    pattern: str
    path: str | None = None
    include: str | None = None  # file glob filter, e.g. "*.py"


class GrepTool(SearchTool):
    id = "grep"
    params_schema = GrepParams

    async def perform_search(
        self, path: Path, params: GrepParams, ctx: ToolContext
    ) -> str:
        pattern = params.pattern
        search_root = path

        rg = "rg"
        try:
            # Prefer ripgrep if available
            args = [
                rg,
                "-nH",
                "--hidden",
                "--no-messages",
                "--field-match-separator=|",
                "--regexp",
                pattern,
            ]
            if params.include:
                args += ["--glob", str(params.include)]
            args.append(str(search_root))
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            code = proc.returncode if proc.returncode is not None else 0
            text = stdout.decode()
            if not text and code not in (0, 1, 2):
                return ToolResult(title="grep", output="No files found.", metadata={})
            lines = [ln for ln in text.splitlines() if ln.strip()]
            entries: list[tuple[str, int, str]] = []
            for ln in lines:
                try:
                    filepath, linenum, linetext = ln.split("|", 3)[:3]
                    entries.append((filepath, int(linenum), linetext))
                except Exception:
                    continue
            # Sort by mtime desc
            try:
                entries.sort(key=lambda e: os.stat(e[0]).st_mtime, reverse=True)
            except Exception:
                pass

            truncated = False
            if len(entries) > MAX_RESULTS:
                entries = entries[:MAX_RESULTS]
                truncated = True

            out_lines: list[str] = []
            for fp, n, text in entries:
                snippet = (
                    text if len(text) <= MAX_LINE_LENGTH else text[:MAX_LINE_LENGTH]
                )
                if len(text) > MAX_LINE_LENGTH:
                    snippet += "..."
                out_lines.append(f"{fp}:\n  Line {n}: {snippet}")
            output = f"Found {len(entries)} matches\n" + "\n".join(out_lines)
            if truncated:
                output += "\n... results truncated; refine your query."
            return output
        except FileNotFoundError:
            # Fallback: Python regex across files
            try:
                regex = re.compile(pattern)
            except re.error as exc:
                return f"Invalid regex: {exc}"

            files: list[Path] = []
            target = search_root
            if target.is_file():
                files = [target]
            else:
                for root, _, filenames in os.walk(target):
                    for name in filenames:
                        files.append(Path(root) / name)

            matches: list[tuple[str, int, str]] = []
            for fp in files:
                try:
                    with open(fp, encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, start=1):
                            if regex.search(line):
                                matches.append((str(fp), i, line.rstrip("\n")))
                                if len(matches) >= MAX_RESULTS:
                                    break
                except Exception:
                    continue
            if not matches:
                return "No files found."
            out_lines = [f"{fp}:\n  Line {n}: {txt}" for fp, n, txt in matches]
            return f"Found {len(matches)} matches\n" + "\n".join(out_lines)
