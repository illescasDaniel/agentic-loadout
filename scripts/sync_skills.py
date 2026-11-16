#!/usr/bin/env python3
"""Refresh the vendored memory-1 and docs-1 skills from their upstream repositories.

agentic-loadout ships its own copies of the two skills (src/agentic_loadout/assets/skills/). This script rebuilds them:

  1. reads every file of `skills/<name>/` at the given commit of the upstream checkout (from git objects, so uncommitted
     edits in the checkout never leak in; the checkout is only read),
  2. re-applies the loadout parts kept in scripts/overlays/ (insertions between `agentic-loadout:begin NAME` and
     `agentic-loadout:end NAME` marker lines), and fails loudly when an anchor line is gone or ambiguous,
  3. checks that stripping the marked blocks gives the upstream file back byte for byte,
  4. replaces the vendored tree, rewrites UPSTREAM.md (what differs, plus a manifest of upstream file hashes) and moves
     the pins in src/agentic_loadout/pins.py to the full commit ids.

usage: scripts/sync_skills.py --memory-1 CHECKOUT [--memory-1-commit REF] --docs-1 CHECKOUT [--docs-1-commit REF]
                              [--check] [--dry-run]
REF defaults to HEAD of the checkout. --check writes nothing and exits 1 when the vendored files, UPSTREAM.md or the
pins differ from what a sync would produce. Standard library only (Python 3.11+).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "src/agentic_loadout/assets/skills"
PINS_FILE = ROOT / "src/agentic_loadout/pins.py"
OVERLAYS_DIR = Path(__file__).resolve().parent / "overlays"

SKILLS = {  # skill name -> (pins.py variable, upstream repository)
    "memory-1": ("MEMORY_SKILL_REF", "illescasDaniel/memory-1-skill"),
    "docs-1": ("DOCS_SKILL_REF", "illescasDaniel/docs-1-skill"),
}

BEGIN = re.compile(r"^[ \t]*(?:#|<!--)[ \t]*agentic-loadout:begin[ \t]+(\S+)")
END = re.compile(r"^[ \t]*(?:#|<!--)[ \t]*agentic-loadout:end[ \t]+(\S+)")
STYLES = {"py": ("# ", ""), "md": ("<!-- ", " -->")}


class SyncError(SystemExit):
    """A failure the maintainer has to look at; printed as one message, exit status 1."""

    def __init__(self, message: str):
        super().__init__(f"error: {message}")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strip_blocks(text: str) -> str:
    """Remove every marked block, and the blank lines right after its end marker, to get the upstream text back.

    A block is inserted directly before a non-blank upstream line; any blank lines that follow its end marker belong to
    the block (they keep the spacing readable) and go with it."""
    out: list[str] = []
    open_name: str | None = None
    skip_blank = False
    for line in text.splitlines(keepends=True):
        if open_name is not None:
            if BEGIN.match(line):
                raise SyncError(f"nested marker `{line.strip()}` inside block {open_name!r}")
            end = END.match(line)
            if end:
                if end[1] != open_name:
                    raise SyncError(f"block {open_name!r} is closed by an end marker for {end[1]!r}")
                open_name, skip_blank = None, True
            continue
        if skip_blank and not line.strip():
            continue
        skip_blank = False
        begin = BEGIN.match(line)
        if begin:
            open_name = begin[1]
            continue
        if END.match(line):
            raise SyncError(f"end marker without a begin: {line.strip()!r}")
        out.append(line)
    if open_name is not None:
        raise SyncError(f"block {open_name!r} is never closed")
    return "".join(out)


@dataclass(frozen=True)
class Insert:
    skill: str
    file: str
    name: str
    before: str  # exact upstream line (no line ending) the block goes in front of; must occur exactly once
    body: str
    style: str = "py"
    blank_after: int = 0
    description: str = ""


def load_overlays(overlays_dir: Path) -> list[Insert]:
    manifest = overlays_dir / "overlays.toml"
    if not manifest.is_file():
        return []
    entries = tomllib.loads(manifest.read_text(encoding="utf-8")).get("insert", [])
    inserts = []
    for entry in entries:
        try:
            body_path = overlays_dir / entry["body"]
            inserts.append(Insert(skill=entry["skill"], file=entry["file"], name=entry["name"], before=entry["before"],
                                  body=body_path.read_text(encoding="utf-8"), style=entry.get("style", "py"),
                                  blank_after=int(entry.get("blank_after", 0)), description=entry.get("description", "")))
        except KeyError as exc:
            raise SyncError(f"{manifest}: an [[insert]] entry lacks {exc}") from exc
        except OSError as exc:
            raise SyncError(f"{manifest}: cannot read the body of {entry.get('name')!r}: {exc}") from exc
        if inserts[-1].style not in STYLES:
            raise SyncError(f"{manifest}: unknown style {inserts[-1].style!r} (use {', '.join(STYLES)})")
        if not inserts[-1].before.strip():
            raise SyncError(f"{manifest}: the anchor line of {inserts[-1].name!r} is blank")
    return inserts


def apply_inserts(text: str, inserts: list[Insert], where: str) -> str:
    """Put each block in front of its anchor line. Anchors are looked up in the upstream text only, so a block can
    never make another block's anchor ambiguous."""
    lines = text.splitlines(keepends=True)
    placed: dict[int, list[str]] = {}
    for ins in inserts:
        hits = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == ins.before]
        if len(hits) != 1:
            raise SyncError(f"overlay {ins.name!r} cannot be applied to {where}: the anchor line {ins.before!r} occurs "
                            f"{len(hits)} times in the upstream file (it must occur exactly once). Upstream changed; "
                            "update scripts/overlays/overlays.toml.")
        i = hits[0]
        if i in placed:
            raise SyncError(f"overlays {ins.name!r} and another block share the anchor line {ins.before!r} in {where}")
        indent = re.match(r"[ \t]*", lines[i])[0]
        nl = "\r\n" if lines[i].endswith("\r\n") else "\n"
        head, tail = STYLES[ins.style]
        body = ins.body.replace("\r\n", "\n")
        body = body if body.endswith("\n") else body + "\n"
        block = [f"{indent}{head}agentic-loadout:begin {ins.name}{tail}{nl}"]
        block += [line.replace("\n", nl) for line in body.splitlines(keepends=True)]
        block += [f"{indent}{head}agentic-loadout:end {ins.name}{tail}{nl}"] + [nl] * ins.blank_after
        placed[i] = block
    out: list[str] = []
    for i, line in enumerate(lines):
        out += placed.get(i, [])
        out.append(line)
    return "".join(out)


def git(checkout: Path, *args: str, text: bool = True) -> str | bytes:
    done = subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=text, check=False)
    if done.returncode != 0:
        detail = (done.stderr if text else done.stderr.decode(errors="replace")).strip()
        raise SyncError(f"`git -C {checkout} {' '.join(args)}` failed: {detail}")
    return done.stdout


def read_upstream(checkout: Path, ref: str, skill: str) -> tuple[str, dict[str, bytes]]:
    """(full commit id, {path relative to the skill folder: bytes}) for `skills/<skill>/` at `ref`."""
    if not checkout.is_dir():
        raise SyncError(f"{checkout} is not a directory")
    commit = git(checkout, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()
    listing = git(checkout, "ls-tree", "-r", "-z", commit, f"skills/{skill}/", text=False)
    files: dict[str, bytes] = {}
    for entry in filter(None, listing.split(b"\0")):
        meta, _, raw_path = entry.partition(b"\t")
        mode, kind, blob = meta.decode().split()
        path = raw_path.decode()
        if kind != "blob" or mode not in ("100644", "100755"):
            raise SyncError(f"{checkout}: {path} at {commit[:7]} is a {kind} with mode {mode}; only regular files are copied")
        files[path.removeprefix(f"skills/{skill}/")] = git(checkout, "cat-file", "blob", blob, text=False)
    if "SKILL.md" not in files:
        raise SyncError(f"{checkout}: no skills/{skill}/SKILL.md at {commit[:7]}")
    return commit, files


@dataclass
class Built:
    commit: str
    upstream: dict[str, bytes]
    result: dict[str, bytes]
    adapted: dict[str, list[Insert]] = field(default_factory=dict)


def build(skill: str, commit: str, upstream: dict[str, bytes], inserts: list[Insert]) -> Built:
    mine = [i for i in inserts if i.skill == skill]
    by_file: dict[str, list[Insert]] = {}
    for ins in mine:
        if ins.file not in upstream:
            raise SyncError(f"overlay {ins.name!r} targets {skill}/{ins.file}, which does not exist upstream at {commit[:7]}")
        by_file.setdefault(ins.file, []).append(ins)
    result = dict(upstream)
    for path, items in by_file.items():
        try:
            original = upstream[path].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SyncError(f"{skill}/{path} is not UTF-8 text and cannot take an overlay") from exc
        patched = apply_inserts(original, items, f"{skill}/{path}")
        if strip_blocks(patched) != original:
            raise SyncError(f"stripping the marked blocks from {skill}/{path} does not give the upstream file back")
        result[path] = patched.encode("utf-8")
    return Built(commit, upstream, result, by_file)


def upstream_doc(built: dict[str, Built]) -> str:
    out = ["# Upstream skills", "",
           ("agentic-loadout ships adapted copies of two Agent Skills. Each copy is made from the skill's own repository at "
            "the commit below; those repositories are never changed from here. Do not edit these folders by hand: "
            "`scripts/sync_skills.py` rebuilds them."), "",
           "| Skill | Upstream repository | Commit |", "|---|---|---|"]
    for name, b in built.items():
        repo = SKILLS[name][1]
        out.append(f"| `{name}` | https://github.com/{repo} | `{b.commit}` |")
    out += ["", "## What differs from upstream", "",
            ("Every difference is an insertion between an `agentic-loadout:begin NAME` and an `agentic-loadout:end NAME` marker "
             "line (`#` comments in Python, HTML comments in Markdown). Removing the marked blocks, and the blank lines right "
             "after each end marker, gives the upstream file byte for byte. Nothing else is changed."), ""]
    any_diff = False
    for name, b in built.items():
        for path, items in sorted(b.adapted.items()):
            for ins in items:
                any_diff = True
                out.append(f"- `{name}/{path}`, block `{ins.name}`: {ins.description or 'no description'}")
    if not any_diff:
        out.append("- Nothing: the copies are identical to upstream.")
    out += ["", "## Manifest", "",
            "`sha256` is the hash of the upstream file (without the marked blocks).", "",
            "| File | sha256 | Differs |", "|---|---|---|"]
    for name, b in built.items():
        for path in sorted(b.upstream):
            out.append(f"| `{name}/{path}` | `{sha256(b.upstream[path])}` | {'yes' if path in b.adapted else 'no'} |")
    out += ["", "## Refresh", "",
            "```bash",
            "python3 scripts/sync_skills.py --memory-1 ../memory-1-skill --memory-1-commit <commit> \\",
            "                               --docs-1 ../docs-1-skill --docs-1-commit <commit>",
            "```", "",
            ("Add `--check` to verify without writing. The script fails when an overlay anchor line no longer exists "
             "upstream; fix `scripts/overlays/overlays.toml` and run it again."), ""]
    return "\n".join(out)


def new_pins(text: str, built: dict[str, Built]) -> str:
    for name, b in built.items():
        variable = SKILLS[name][0]
        text, count = re.subn(rf'(?m)^({variable} = )"[^"\n]*"[^\n]*$', lambda m, commit=b.commit: f'{m[1]}"{commit}"', text)
        if count != 1:
            raise SyncError(f"{PINS_FILE} must contain exactly one `{variable} = \"...\"` line (found {count})")
    return text


def planned_files(built: dict[str, Built], skills_dir: Path, pins_file: Path) -> dict[Path, bytes]:
    files: dict[Path, bytes] = {}
    for name, b in built.items():
        for path, data in b.result.items():
            files[skills_dir / name / path] = data
    files[skills_dir / "UPSTREAM.md"] = upstream_doc(built).encode("utf-8")
    files[pins_file] = new_pins(pins_file.read_text(encoding="utf-8"), built).encode("utf-8")
    return files


def existing_files(built: dict[str, Built], skills_dir: Path) -> set[Path]:
    return {p for name in built for p in (skills_dir / name).rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def sync(specs: dict[str, tuple[Path, str]], skills_dir: Path = SKILLS_DIR, pins_file: Path = PINS_FILE,
         overlays_dir: Path = OVERLAYS_DIR, check: bool = False, dry_run: bool = False, log=print) -> list[str]:
    """Returns the list of paths that differ from what is on disk (all of them are written unless check or dry_run)."""
    inserts = load_overlays(overlays_dir)
    unknown = {i.skill for i in inserts} - set(specs)
    if unknown:
        raise SyncError(f"overlays exist for {', '.join(sorted(unknown))} but no checkout was given for it")
    built = {}
    for name, (checkout, ref) in specs.items():
        commit, files = read_upstream(checkout, ref, name)
        built[name] = build(name, commit, files, inserts)
    planned = planned_files(built, skills_dir, pins_file)
    stale = existing_files(built, skills_dir) - set(planned)
    def shown(p: Path) -> str:
        return p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p)

    different = [p for p, data in planned.items() if not p.is_file() or p.read_bytes() != data]
    removed = sorted(stale)
    report = [shown(p) for p in [*different, *removed]]
    for path in different:
        log(f"  changed  {shown(path)}")
    for path in removed:
        log(f"  removed  {shown(path)}")
    if check or dry_run:
        return report
    for path in different:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(planned[path])
    for path in removed:  # gone upstream: remove the vendored copy, then folders that became empty
        path.unlink()
        for parent in path.parents:
            if parent == skills_dir or any(parent.iterdir()):
                break
            parent.rmdir()
    return report


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--memory-1", dest="memory", type=Path, required=True, metavar="CHECKOUT", help="memory-1-skill checkout")
    ap.add_argument("--memory-1-commit", dest="memory_ref", default="HEAD", metavar="REF", help="commit to copy (default: HEAD)")
    ap.add_argument("--docs-1", dest="docs", type=Path, required=True, metavar="CHECKOUT", help="docs-1-skill checkout")
    ap.add_argument("--docs-1-commit", dest="docs_ref", default="HEAD", metavar="REF", help="commit to copy (default: HEAD)")
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 if a sync would change anything")
    ap.add_argument("--dry-run", action="store_true", help="list what would change; write nothing")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    specs = {"memory-1": (args.memory.resolve(), args.memory_ref), "docs-1": (args.docs.resolve(), args.docs_ref)}
    changes = sync(specs, check=args.check, dry_run=args.dry_run)
    if args.check:
        print("the vendored skills differ from the upstream commits" if changes else "the vendored skills match upstream plus overlays")
        return 1 if changes else 0
    print(f"{len(changes)} file(s) {'would change' if args.dry_run else 'updated'}" if changes else "no changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
