"""Checks that need no writes. All problems are collected and reported together before anything is touched."""

from __future__ import annotations

import shutil
from collections.abc import Callable

from .options import Options


def check(opts: Options, coder_keys: list[str], which: Callable[[str], str | None] = shutil.which) -> list[str]:
    problems = []
    needs_uv = opts.wants("agemem") or "python" in coder_keys
    needs_npx = opts.wants("sdd") or "typescript" in coder_keys
    if needs_uv and which("uvx") is None:
        problems.append("`uvx` not found (needed for agemem and the Python coder). Install uv: https://docs.astral.sh/uv/")
    if needs_npx and which("npx") is None:
        problems.append("`npx` not found (needed for the sdd skill and the TypeScript coder). Install Node.js 20+.")
    if opts.memory_model not in (None, "jev", "qsiv"):
        problems.append(f"--memory-model must be jev or qsiv (got {opts.memory_model!r})")
    if not opts.project.is_dir():
        problems.append(f"{opts.project} is not a directory")
    return problems
