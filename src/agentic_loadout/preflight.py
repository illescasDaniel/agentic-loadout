"""Checks that need no writes. All problems are collected and reported together before anything is touched."""

from __future__ import annotations

import shutil
from collections.abc import Callable

from .options import Options
from .files import read_json


def check(opts: Options, coder_keys: list[str], which: Callable[[str], str | None] = shutil.which) -> list[str]:
    problems = []
    needs_uv = opts.wants("agemem") or "python" in coder_keys
    needs_npx = opts.wants("sdd") or opts.wants("worktree") or "typescript" in coder_keys
    if needs_uv and which("uvx") is None:
        problems.append("`uvx` not found (needed for agemem and the Python coder). Install uv: https://docs.astral.sh/uv/")
    if needs_npx and which("npx") is None:
        problems.append("`npx` not found (needed for the sdd and worktree skills and the TypeScript coder). Install Node.js 20+.")
    if opts.memory_model not in (None, "jev", "qsiv"):
        problems.append(f"--memory-model must be jev or qsiv (got {opts.memory_model!r})")
    config = opts.project / ".agemem/config.json"
    if opts.wants("agemem") and opts.memory_model and config.is_file():
        project_config, _ = read_json(config)
        provider = project_config.get("decision_backend")
        if provider is not None and provider != opts.memory_model:
            problems.append(f"--memory-model {opts.memory_model} conflicts with the project's existing "
                            f"Agemem provider {provider!r}; leave out --memory-model to preserve it.")
    if opts.entire_upload_sessions and (not opts.wants("entire") or opts.no_hooks):
        problems.append("--entire-upload-sessions requires Entire and hooks")
    if not opts.project.is_dir():
        problems.append(f"{opts.project} is not a directory")
    return problems
