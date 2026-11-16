"""Checks that need no writes. All problems are collected and reported together before anything is touched."""

from __future__ import annotations

import shutil
from collections.abc import Callable

from .options import Options


def check(opts: Options, coder_keys: list[str], which: Callable[[str], str | None] = shutil.which) -> list[str]:
    problems = []
    needs_uv = "python" in coder_keys
    needs_npx = any(opts.wants(c) for c in ("sdd", "worktree")) or "typescript" in coder_keys
    if needs_uv and which("uvx") is None:
        problems.append("`uvx` not found (needed for the Python coder). Install uv: https://docs.astral.sh/uv/")
    if needs_npx and which("npx") is None:
        problems.append("`npx` not found (needed for the sdd and worktree skills and the TypeScript coder). Install Node.js 20+.")
    if "go" in coder_keys and which("go") is None:
        problems.append("`go` not found (needed to run the Go coder's codenav-go MCP). Install Go: https://go.dev/dl/")
    if opts.entire_upload_sessions and (not opts.wants("entire") or opts.no_hooks):
        problems.append("--entire-upload-sessions requires Entire (add --with entire) and hooks")
    if not opts.project.is_dir():
        problems.append(f"{opts.project} is not a directory")
    return problems
