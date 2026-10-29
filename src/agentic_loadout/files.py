"""File operations shared by the install steps. Writes are collected in `Ctx` and applied at the end, so --dry-run
and a failing check leave the project untouched."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Ctx:
    project: Path
    dry_run: bool = False
    force: bool = False
    lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # follow-up steps for the user, printed in the summary
    pending: dict[Path, bytes] = field(default_factory=dict)

    def exists(self, path: Path) -> bool:
        return path in self.pending or path.exists()

    def read(self, path: Path) -> bytes:
        return self.pending[path] if path in self.pending else path.read_bytes()

    def write(self, path: Path, data: bytes):
        if path.exists() and not path.is_file():
            raise SystemExit(f"error: {path} must be a file")
        for parent in path.parents:
            if parent.exists() and not parent.is_dir():
                raise SystemExit(f"error: {parent} must be a directory")
        self.pending[path] = data

    def apply(self):
        """Apply only after every generated file has been checked."""
        if self.dry_run:
            return
        for path, data in self.pending.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.pending.clear()

    def log(self, status: str, path: Path | str, note: str = "") -> None:
        shown = path
        if isinstance(path, Path):
            try:
                shown = path.relative_to(self.project).as_posix()
            except ValueError:
                shown = path
        self.lines.append(f"  {status:<10} {shown}{('  ' + note) if note else ''}")

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def note(self, message: str) -> None:
        if message not in self.notes:
            self.notes.append(message)

    def verb(self, path: Path) -> str:
        """Log verb for a write: planned in a dry run, past tense otherwise. "edit" only if the file is on disk."""
        existed = path.exists()
        if self.dry_run:
            return "would edit" if existed else "would create"
        return "edited" if existed else "created"


def write_bytes(ctx: Ctx, dest: Path, data: bytes) -> str:
    """Create `dest`, or replace it only with --force. Never overwrites a file that differs by default."""
    if ctx.exists(dest):
        if ctx.read(dest) == data:
            ctx.log("unchanged", dest)
            return "unchanged"
        if not ctx.force:
            ctx.log("skipped", dest, "differs from the shipped version (use --force to overwrite)")
            return "skipped"
        status = "replaced"
    else:
        status = "created"
    ctx.write(dest, data)
    ctx.log(status if not ctx.dry_run else f"would {status.removesuffix('d')}", dest)
    return status


def read_json(path: Path, ctx: Ctx | None = None) -> tuple[dict[str, Any], str]:
    """Return (data, indent). Missing file -> ({}, two spaces). Matches the file's existing indent style."""
    if not (ctx.exists(path) if ctx else path.exists()):
        return {}, "  "
    text = ctx.read(path).decode("utf-8") if ctx else path.read_text(encoding="utf-8")
    if not text.strip():
        return {}, "  "
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: {path} is not valid JSON ({exc}); fix it or move it away and re-run")
    if not isinstance(data, dict):
        raise SystemExit(f"error: {path} must contain a JSON object")
    indent = "\t" if "\n\t" in text else "  "
    return data, indent


def write_json(ctx: Ctx, path: Path, data: dict[str, Any], indent: str, changes: list[str]) -> None:
    if not changes:
        ctx.log("unchanged", path)
        return
    ctx.write(path, (json.dumps(data, indent=indent, ensure_ascii=False) + "\n").encode("utf-8"))
    ctx.log(ctx.verb(path), path, "+ " + ", ".join(changes))
