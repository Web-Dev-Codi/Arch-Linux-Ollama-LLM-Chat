from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shlex
import signal
import subprocess

from .base import ParamsSchema, Tool, ToolContext, ToolResult

DEFAULT_TIMEOUT_MS = 120_000
MAX_METADATA_LENGTH = 30_000

# Minimal arity table used to build stable permission patterns
ARITY: dict[str, int] = {
    "cat": 1,
    "cd": 1,
    "chmod": 1,
    "chown": 1,
    "cp": 1,
    "echo": 1,
    "grep": 1,
    "kill": 1,
    "ls": 1,
    "mkdir": 1,
    "mv": 1,
    "rm": 1,
    "touch": 1,
    "which": 1,
    "git": 2,
    "npm": 2,
    "bun": 2,
    "docker": 2,
    "python": 2,
    "pip": 2,
    "cargo": 2,
    "go": 2,
    "make": 2,
    "yarn": 2,
    "npm run": 3,
    "bun run": 3,
    "git config": 3,
    "docker compose": 3,
}


class BashParams(ParamsSchema):
    command: str
    description: str  # short summary for live metadata
    timeout: int | None = None  # milliseconds; default DEFAULT_TIMEOUT_MS
    workdir: str | None = None  # defaults to project directory


class BashTool(Tool):
    id = "bash"
    params_schema = BashParams
    description = (
        "Executes a bash command with timeout and output caps. Use workdir instead of cd."
    )

    async def _kill_process_tree(self, proc: asyncio.subprocess.Process) -> None:
        try:
            if os.name == "nt":  # Windows
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)])
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass

    def _extract_tokens(self, command: str) -> list[str]:
        try:
            return shlex.split(command)
        except Exception:
            return command.strip().split()

    def _arity_prefix(self, tokens: list[str]) -> list[str]:
        for length in range(len(tokens), 0, -1):
            key = " ".join(tokens[:length])
            if key in ARITY:
                return tokens[: ARITY[key]]
        return tokens[:1]

    async def _check_external_dirs(self, tokens: list[str], cwd: Path, ctx: ToolContext) -> None:
        pathlike_cmds = {"cd", "rm", "cp", "mv", "mkdir", "touch", "chmod", "chown", "cat"}
        if not tokens:
            return
        if tokens[0] not in pathlike_cmds:
            return
        dirs: set[Path] = set()
        for tok in tokens[1:]:
            if tok.startswith("-"):
                continue
            p = Path(tok)
            if not p.is_absolute():
                p = (cwd / p).resolve()
            try:
                if p.is_dir():
                    target = p
                else:
                    target = p.parent
                dirs.add(target)
            except Exception:
                continue
        if not dirs:
            return
        globs = [str(d / "*") for d in dirs]
        await ctx.ask(
            permission="external_directory",
            patterns=globs,
            always=globs,
            metadata={},
        )

    async def execute(self, params: BashParams, ctx: ToolContext) -> ToolResult:
        command = params.command.strip()
        if not command:
            return ToolResult(title="bash", output="Empty command.", metadata={"ok": False})

        project_dir = Path(str(ctx.extra.get("project_dir", "."))).expanduser().resolve()
        cwd = Path(params.workdir or project_dir).expanduser().resolve()
        if not cwd.exists() or not cwd.is_dir():
            return ToolResult(title="bash", output="Invalid working directory.", metadata={"ok": False})

        tokens = self._extract_tokens(command)
        await self._check_external_dirs(tokens, cwd, ctx)

        # Ask permission with patterns and arity prefix
        prefix = " ".join(self._arity_prefix(tokens))
        await ctx.ask(
            permission="bash",
            patterns=[command],
            always=[prefix + " *"],
            metadata={},
        )

        extra_env: dict[str, str] = {}
        timeout_ms = int(params.timeout or DEFAULT_TIMEOUT_MS)
        timeout_sec = max(1.0, timeout_ms / 1000.0)

        # Spawn process in its own session/process group for reliable termination
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(cwd),
            env={**os.environ, **extra_env},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=(os.name != "nt"),
        )

        output_chunks: list[str] = []
        aborted = False
        timed_out = False

        async def _read_stream(stream: asyncio.StreamReader) -> None:
            while True:
                if ctx.abort.is_set():
                    break
                chunk = await stream.readline()
                if not chunk:
                    break
                output_chunks.append(chunk.decode(errors="ignore"))
                tail = ("".join(output_chunks))[-MAX_METADATA_LENGTH:]
                ctx.metadata(title="bash", metadata={"output": tail, "description": params.description})

        tasks = []
        if proc.stdout is not None:
            tasks.append(asyncio.create_task(_read_stream(proc.stdout)))
        if proc.stderr is not None:
            tasks.append(asyncio.create_task(_read_stream(proc.stderr)))

        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout_sec)
        except TimeoutError:
            timed_out = True
            await self._kill_process_tree(proc)
        if ctx.abort.is_set():
            aborted = True
            await self._kill_process_tree(proc)

        # Ensure readers finish
        await asyncio.gather(*tasks, return_exceptions=True)

        exit_code = proc.returncode if proc.returncode is not None else -1
        output = "".join(output_chunks)

        meta_note = []
        if timed_out:
            meta_note.append("timed out")
        if aborted:
            meta_note.append("aborted")
        status_part = f" status={','.join(meta_note)}" if meta_note else ""
        output += f"\n<bash_metadata> exit_code={exit_code}{status_part}</bash_metadata>"

        return ToolResult(title=f"bash: {command}", output=output, metadata={"exit_code": exit_code, "timed_out": timed_out, "aborted": aborted})
