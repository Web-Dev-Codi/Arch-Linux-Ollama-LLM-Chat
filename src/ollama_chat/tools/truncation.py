from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

try:  # Lazy import only when writing files
    import aiofiles  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    aiofiles = None  # type: ignore[assignment]

MAX_LINES = 2000
MAX_BYTES = 50 * 1024  # 50 KB
OUTPUT_DIR = Path.home() / ".local" / "share" / "ollamaterm" / "tool-output"
RETENTION_SECONDS = 7 * 24 * 60 * 60  # 7 days


@dataclass
class TruncateResult:
    content: str
    truncated: bool
    output_path: str | None = None


def _agent_has_task_tool(agent: str | None) -> bool:
    # Without full permission plumbing available in this standalone package,
    # conservatively return False. Callers can still follow the generic hint.
    return False


async def _write_full_output(full_text: str) -> str | None:
    """Persist full text to OUTPUT_DIR; return file path or None on failure."""
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        name = f"tool_{int(time.time() * 1000)}.txt"
        path = OUTPUT_DIR / name
        if aiofiles is None:
            path.write_text(full_text)
        else:  # pragma: no cover - requires aiofiles
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(full_text)
        return str(path)
    except Exception:
        return None


async def truncate_output(
    text: str,
    direction: str = "head",  # "head" | "tail"
    agent: str | None = None,
    max_lines: int = MAX_LINES,
    max_bytes: int = MAX_BYTES,
) -> TruncateResult:
    """
    Apply line and byte caps. If truncated, persist the full text to disk and
    append a helpful hint to the preview.
    """
    if not text:
        return TruncateResult(content="", truncated=False, output_path=None)

    encoded = text.encode("utf-8", errors="ignore")
    lines = text.splitlines()

    if len(lines) <= max_lines and len(encoded) <= max_bytes:
        return TruncateResult(content=text, truncated=False, output_path=None)

    truncated = []
    total_bytes = 0

    iterable = enumerate(lines) if direction == "head" else enumerate(reversed(lines))
    for _, line in iterable:
        candidate = ("\n".join(truncated + [line])).encode("utf-8", errors="ignore")
        if len(truncated) + 1 > max_lines or len(candidate) > max_bytes:
            break
        truncated.append(line)
        total_bytes = len(candidate)

    if direction != "head":
        truncated.reverse()

    preview = "\n".join(truncated)
    hidden_lines = max(0, len(lines) - len(truncated))
    hidden_bytes = max(0, len(encoded) - total_bytes)

    out_path = await _write_full_output(text)

    has_task = _agent_has_task_tool(agent)
    if has_task:
        hint = (
            "Use the explore agent with Read/Grep to inspect the full output, "
            "or open the saved file if available."
        )
    else:
        hint = (
            "Refine your query or use read with offset/limit to page through the file."
        )

    suffix = (
        f"\n... {hidden_lines} lines / {hidden_bytes} bytes truncated ...\n\n{hint}"
    )
    return TruncateResult(content=preview + suffix, truncated=True, output_path=out_path)


async def cleanup_old_outputs() -> None:
    """
    Delete files in OUTPUT_DIR older than RETENTION_SECONDS. Filename format:
    tool_{epoch_ms}. Unknown filenames are ignored.
    """
    if not OUTPUT_DIR.exists():
        return
    now = time.time()
    for entry in OUTPUT_DIR.iterdir():
        try:
            if not entry.is_file():
                continue
            stem = entry.stem  # e.g. tool_1700000000000
            if not stem.startswith("tool_"):
                continue
            ts_ms = int(stem.split("_", 1)[1])
            age = now - (ts_ms / 1000.0)
            if age > RETENTION_SECONDS:
                try:
                    entry.unlink(missing_ok=True)
                except Exception:
                    continue
        except Exception:
            continue
