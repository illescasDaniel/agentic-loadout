"""The external installers agent-loadout hands work to. Each one is a pure "build the command" function plus a thin
executor, so `--dry-run` can print exactly what would run and tests can check the command lines."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from . import pins
from .options import Options

SKILLS_AGENT_NAMES = {"claude": "claude-code", "cursor": "cursor", "codex": "codex"}
Executor = Callable[[Sequence[str], Path, dict[str, str]], subprocess.CompletedProcess]


def agemem_command(opts: Options) -> list[str]:
    cmd = ["uvx", "--python", pins.AGEMEM_PYTHON, pins.AGEMEM, "project", "init", "--mcp", *opts.selected(),
           "--model", opts.memory_model or "jev"]
    if opts.no_hooks:
        cmd.append("--no-hooks")
    return [*cmd, "--no-input"]


def skills_command(opts: Options, repo: str = pins.SDD_SKILL, ref: str = pins.SDD_SKILL_REF) -> list[str]:
    cmd = ["npx", "-y", pins.SKILLS, "add", f"{repo}#{ref}"]
    for tool in opts.selected():
        cmd += ["-a", SKILLS_AGENT_NAMES[tool]]
    # --copy: no symlink may point outside the project. Never -g (global).
    return [*cmd, "-y", "--copy"]


def skills_env() -> dict[str, str]:
    return {"DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1"}


def default_executor(cmd: Sequence[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), cwd=cwd, env={**os.environ, **env}, capture_output=True, text=True, check=False)


def run(cmd: Sequence[str], opts: Options, executor: Executor, log: Callable[[str], None], env: dict[str, str] | None = None) -> None:
    shown = " ".join(cmd)
    if opts.dry_run:
        log(f"  would run  {shown}")
        return
    log(f"  running    {shown}")
    result = executor(cmd, opts.project, env or {})
    if result.returncode != 0:
        tail = ((result.stderr or "") + (result.stdout or "")).strip()[-600:]
        raise SystemExit(f"error: `{shown}` failed (exit {result.returncode}).\n{tail}")
