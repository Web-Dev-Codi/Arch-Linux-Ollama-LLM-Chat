from __future__ import annotations

import os
from pathlib import Path

from .base import ParamsSchema, Tool, ToolContext, ToolResult


class SkillParams(ParamsSchema):
    name: str


class SkillTool(Tool):
    id = "skill"
    params_schema = SkillParams

    def _skill_dirs(self, ctx: ToolContext) -> list[Path]:
        dirs: list[Path] = []
        dirs.append(Path.home() / ".config" / "opencode" / "skills")
        project = ctx.project_root
        dirs.append(project / ".opencode" / "skills")
        for extra in ctx.extra.get("skill_dirs", []) or []:
            try:
                p = ctx.resolve_path(str(extra))
                dirs.append(p)
            except Exception:
                continue
        return dirs

    def _find_skill_file(self, name: str, dirs: list[Path]) -> Path | None:
        for base in dirs:
            candidate = base / name / "SKILL.md"
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _parse_skill_md(self, path: Path) -> tuple[str, str]:
        text = path.read_text(encoding="utf-8", errors="replace")
        desc = ""
        body = text
        if text.startswith("---\n"):
            try:
                end = text.index("\n---\n", 4)
                front = text[4:end]
                body = text[end + 5 :]
                for line in front.splitlines():
                    if line.lower().startswith("description:"):
                        desc = line.split(":", 1)[1].strip()
                        break
            except ValueError:
                pass
        return desc, body

    async def execute(self, params: SkillParams, ctx: ToolContext) -> ToolResult:
        dirs = self._skill_dirs(ctx)
        name = params.name.strip()
        await ctx.ask(permission="skill", patterns=[name], always=[name], metadata={})
        path = self._find_skill_file(name, dirs)
        if not path:
            available: list[str] = []
            for base in dirs:
                if base.exists():
                    for child in base.iterdir():
                        if (child / "SKILL.md").exists():
                            available.append(child.name)
            available.sort()
            return ToolResult(
                title="skill",
                output=f"Skill '{name}' not found. Available: {', '.join(available) if available else 'none'}",
                metadata={"ok": False},
            )

        desc, content = self._parse_skill_md(path)
        skill_dir = path.parent
        # List up to 10 files (excluding SKILL.md)
        files: list[str] = []
        for root, _dirs, fnames in os.walk(skill_dir):
            for fname in fnames:
                p = Path(root) / fname
                try:
                    if p.samefile(path):
                        continue
                except Exception:
                    if str(p) == str(path):
                        continue
                files.append(str(p.relative_to(skill_dir)))
                if len(files) >= 10:
                    break
            if len(files) >= 10:
                break

        base_url = skill_dir.as_uri()
        body = (
            f'<skill_content name="{name}">\n'
            f"# Skill: {name}\n\n{content}\n\n"
            f"Base directory: {base_url}\n"
            "Relative paths are relative to this base directory.\n\n"
            "<skill_files>\n"
            + "\n".join(f"<file>{f}</file>" for f in files)
            + "\n</skill_files>\n</skill_content>"
        )
        return ToolResult(
            title=f"skill: {name}", output=body, metadata={"description": desc}
        )
