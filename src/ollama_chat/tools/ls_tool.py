from __future__ import annotations

from collections import defaultdict
import os
from pathlib import Path

from .abstracts import SearchTool
from .base import ParamsSchema, ToolContext

IGNORE_PATTERNS = [
    "node_modules/",
    "__pycache__/",
    ".git/",
    "dist/",
    "build/",
    "target/",
    "vendor/",
    "bin/",
    "obj/",
    ".idea/",
    ".vscode/",
    ".zig-cache/",
    "zig-out",
    ".coverage",
    "coverage/",
    "tmp/",
    "temp/",
    ".cache/",
    "cache/",
    "logs/",
    ".venv/",
    "venv/",
    "env/",
]
LIMIT = 100


class ListParams(ParamsSchema):
    path: str | None = None
    ignore: list[str] | None = None


class ListTool(SearchTool):
    id = "list"
    params_schema = ListParams

    async def perform_search(
        self, path: Path, params: ListParams, ctx: ToolContext
    ) -> str:
        search = path
        ignore = set(IGNORE_PATTERNS)
        for pat in params.ignore or []:
            if pat:
                ignore.add(pat)

        # Gather files under the search root
        files: list[Path] = []
        for root, dirnames, filenames in os.walk(search):
            # Skip ignored directories by prefix match
            dirnames[:] = [
                d
                for d in dirnames
                if not any(
                    (Path(root) / d).as_posix().endswith(p.rstrip("/")) for p in ignore
                )
            ]
            for name in filenames:
                files.append(Path(root) / name)
                if len(files) >= LIMIT:
                    break
            if len(files) >= LIMIT:
                break

        # Build tree structures
        dirs: set[Path] = set([search])
        files_by_dir: defaultdict[Path, list[str]] = defaultdict(list)
        for fp in files:
            dirs.add(fp.parent)
            files_by_dir[fp.parent].append(fp.name)

        # Ensure parents are included
        for d in list(dirs):
            for p in d.parents:
                if search in p.parents or p == search:
                    dirs.add(p)

        def render_dir(dir_path: Path, depth: int) -> str:
            indent = "  " * depth
            out = f"{indent}{dir_path.name}/\n" if depth > 0 else ""
            children = sorted(
                {d for d in dirs if d.parent == dir_path and d != dir_path},
                key=lambda p: p.name.lower(),
            )
            for child in children:
                out += render_dir(child, depth + 1)
            for fname in sorted(files_by_dir.get(dir_path, [])):
                out += f"{'  ' * (depth + 1)}{fname}\n"
            return out

        output = f"{str(search)}/\n" + render_dir(search, 0)
        return output.rstrip("\n")
