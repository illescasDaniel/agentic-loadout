"""Personal mode: remember what the project looked like before the run, and afterwards (a) add every file the run
created to `.git/info/exclude` and (b) list the files that already existed and were changed, which git can't hide.
Everything stays inside the project."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

BLOCK_START = "# agent-loadout"
# Existing files a run may change; they're hashed to notice edits. New files are found by listing, not hashing.
WATCHED = (".mcp.json", ".cursor/mcp.json", ".codex/config.toml", ".codex/hooks.json", ".claude/settings.json",
           ".claude/settings.local.json", "AGENTS.md", "CLAUDE.md", "CLAUDE.local.md", ".gitignore")


def _git(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True, check=False)


def is_git_repo(project: Path) -> bool:
    try:
        return _git(project, "rev-parse", "--git-dir").returncode == 0
    except FileNotFoundError:
        return False


@dataclass
class Snapshot:
    files: set[str] = field(default_factory=set)  # tracked + untracked-not-ignored, relative posix paths
    hashes: dict[str, str] = field(default_factory=dict)
    tracked: set[str] = field(default_factory=set)
    dirty: set[str] = field(default_factory=set)  # tracked files that differ from HEAD


def snapshot(project: Path) -> Snapshot:
    snap = Snapshot()
    if not is_git_repo(project):
        return snap
    snap.tracked = set(filter(None, _git(project, "ls-files", "-z").stdout.split("\0")))
    others = set(filter(None, _git(project, "ls-files", "-z", "--others", "--exclude-standard").stdout.split("\0")))
    snap.files = snap.tracked | others
    diff = _git(project, "diff", "HEAD", "--name-only", "-z")
    if diff.returncode != 0:  # no commit yet
        diff = _git(project, "diff", "--name-only", "-z")
    snap.dirty = set(filter(None, diff.stdout.split("\0")))
    # Hash the files a run is known to edit, plus tracked files that were already modified (a further edit is invisible
    # to the dirty list). Any other tracked file that becomes dirty is caught by the list.
    for rel in {*WATCHED, *snap.dirty}:
        path = project / rel
        if path.is_file():
            snap.hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snap


def _topmost_new(rel: str, before: set[str]) -> tuple[str, bool]:
    """The topmost directory of `rel` that held no file before the run, or the file itself."""
    parts = rel.split("/")
    for depth in range(1, len(parts)):
        prefix = "/".join(parts[:depth]) + "/"
        if not any(f.startswith(prefix) for f in before):
            return "/" + prefix, True
    return "/" + rel, False


@dataclass
class Report:
    excluded: list[str] = field(default_factory=list)
    changed_existing: list[str] = field(default_factory=list)  # existing files we or a tool edited
    changed_tracked: list[str] = field(default_factory=list)  # subset of changed_existing that git tracks
    not_git: bool = False


def finish(project: Path, before: Snapshot, hide: bool, dry_run: bool = False) -> Report:
    report = Report()
    if not is_git_repo(project):
        report.not_git = True
        return report
    after = snapshot(project)
    new = sorted(after.files - before.files)
    entries: list[str] = []
    for rel in new:
        entry, _ = _topmost_new(rel, before.files)
        if entry not in entries:
            entries.append(entry)
    edited = {rel for rel, digest in after.hashes.items() if rel in before.hashes and before.hashes[rel] != digest}
    report.changed_tracked = sorted((after.dirty - before.dirty | edited) & after.tracked)
    report.changed_existing = sorted(edited | set(report.changed_tracked))
    if hide and entries and not dry_run:
        exclude = Path(_git(project, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude").stdout.strip())
        original = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        present = set(original.splitlines())
        entries = [e for e in entries if e not in present]
        if entries:
            sep = "" if not original or original.endswith("\n\n") else "\n" if original.endswith("\n") else "\n\n"
            exclude.parent.mkdir(parents=True, exist_ok=True)
            exclude.write_text(original + sep + BLOCK_START + "\n" + "\n".join(entries) + "\n", encoding="utf-8")
    report.excluded = entries if hide else []
    return report


def explain_changes(report: Report, hide: bool) -> list[str]:
    """Plain-language lines for the final message about files that already existed and were changed."""
    lines = []
    for rel in report.changed_existing:
        tracked = rel in report.changed_tracked
        if tracked and hide:
            lines.append(f"{rel}: already tracked by git and was edited, so it can't be hidden. See `git diff {rel}`. "
                         f"Commit it, hide your local edit with `git update-index --skip-worktree {rel}`, or revert it "
                         f"with `git checkout -- {rel}`.")
        else:
            lines.append(f"{rel}: existed before and was edited by this run. Review it before committing.")
    return lines
