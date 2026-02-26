from __future__ import annotations

from pathlib import Path


async def assert_external_directory(
    ctx,
    target: str | None,
    bypass: bool = False,
    kind: str = "file",  # "file" | "directory"
) -> None:
    """
    Ask the user for approval when operating outside the project/worktree roots.
    The project directory is derived from ctx.extra.get("project_dir") or CWD.
    """
    if target is None or bypass:
        return

    try:
        target_path = Path(target).resolve()
    except Exception:
        # If the path cannot be resolved, fall back to asking for the parent dir.
        target_path = Path(str(target)).expanduser()

    project_dir_text = str(ctx.extra.get("project_dir", "."))
    worktree_text = str(ctx.extra.get("worktree", project_dir_text))
    project_dir = Path(project_dir_text).expanduser().resolve()
    worktree = Path(worktree_text).expanduser().resolve()

    # If target is inside project_dir or worktree, no approval required.
    def _inside(root: Path, child: Path) -> bool:
        try:
            return root == child or root in child.parents
        except Exception:
            return False

    if _inside(project_dir, target_path) or _inside(worktree, target_path):
        return

    parent_dir = target_path if kind == "directory" else target_path.parent
    glob = str(parent_dir / "*")
    await ctx.ask(
        permission="external_directory",
        patterns=[glob],
        always=[glob],
        metadata={"filepath": str(target_path), "parentDir": str(parent_dir)},
    )
