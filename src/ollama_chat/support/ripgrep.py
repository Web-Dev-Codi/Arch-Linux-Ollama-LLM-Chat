from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import os
from pathlib import Path
import shutil

RG_BIN = Path.home() / ".local" / "share" / "ollamaterm" / "bin" / "rg"


async def filepath() -> str:
    """Return a path to a ripgrep binary if available.

    Preference order:
    1) RG_BIN path if present
    2) "rg" on PATH
    3) "ripgrep" on PATH

    Falls back to returning "rg" which may or may not exist at runtime.
    """
    if RG_BIN.exists():
        return str(RG_BIN)
    for name in ("rg", "ripgrep"):
        found = shutil.which(name)
        if found:
            return found
    return "rg"


async def files(
    cwd: str,
    glob: list[str] | None = None,
    follow: bool = True,
    hidden: bool = False,
    signal: asyncio.Event | None = None,
) -> AsyncIterator[str]:
    """Yield file paths using ripgrep if available, else Python fallback.

    Args roughly map to: rg --files [--follow] [--hidden] [--glob pat]... {cwd}
    """
    rg = await filepath()
    if shutil.which(Path(rg).name):
        args = [rg, "--files"]
        if follow:
            args.append("--follow")
        if hidden:
            args.append("--hidden")
        for pat in glob or []:
            args += ["--glob", pat]
        args.append(str(cwd))
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except Exception:
            proc = None
        if proc is not None and proc.stdout is not None:
            while True:
                if signal and signal.is_set():
                    break
                chunk = await proc.stdout.readline()
                if not chunk:
                    break
                yield chunk.decode().rstrip("\n")
            return

    # Fallback: walk the directory.
    for root, _dirnames, filenames in os.walk(cwd):
        for name in filenames:
            if signal and signal.is_set():
                return
            yield str(Path(root) / name)
