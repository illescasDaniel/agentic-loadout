"""Rule sections in the project's instruction file (AGENTS.md / CLAUDE.md / CLAUDE.local.md).

Each section is wrapped in `<!-- agentic-loadout:begin NAME -->` markers, so a re-run replaces it in place and the user
can delete it. A heading the user already has without our markers is never touched or moved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .files import Ctx

IMPORT_RE = re.compile(r"^\s*@AGENTS\.md\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Section:
    name: str  # marker name: agents, memory, sdd, coder-python ...
    body: str  # starts with a heading line

    @property
    def heading(self) -> str:
        return self.body.lstrip().splitlines()[0].lstrip("#").strip()

    @property
    def block(self) -> str:
        return f"<!-- agentic-loadout:begin {self.name} -->\n{self.body.strip()}\n<!-- agentic-loadout:end {self.name} -->"


def _marker_re(name: str) -> re.Pattern[str]:
    return re.compile(rf"<!-- agentic-loadout:begin {re.escape(name)} -->.*?<!-- agentic-loadout:end {re.escape(name)} -->", re.DOTALL)


def _has_heading(text: str, heading: str) -> bool:
    return any(m.group(1).strip() == heading for m in re.finditer(r"^#{1,6}[ \t]+(.+)$", text, re.MULTILINE))


def is_import_stub(text: str) -> bool:
    """CLAUDE.md that does nothing but import AGENTS.md."""
    return bool(text.strip()) and all(line.strip() in ("", "@AGENTS.md") for line in text.splitlines())


def choose_targets(ctx: Ctx, tools: list[str], personal: bool) -> list[Path]:
    """The file(s) the sections go to (rules in §4 of PLAN.md)."""
    agents_md, claude_md, local_md = (ctx.project / n for n in ("AGENTS.md", "CLAUDE.md", "CLAUDE.local.md"))
    others = [t for t in tools if t != "claude"]
    if personal and not others:
        return [local_md]
    if personal:
        if "claude" in tools:
            ctx.warn("--personal-settings: the rules are in AGENTS.md because Cursor and Codex have no personal project "
                     "instruction file. If AGENTS.md is tracked, the edit shows in git.")
        return [agents_md]
    if claude_md.exists() and not is_import_stub(claude_md.read_text(encoding="utf-8")):
        # Cursor and Codex don't read CLAUDE.md, so they get the same sections in AGENTS.md.
        return [claude_md, agents_md] if others else [claude_md]
    return [agents_md]


def apply_sections(ctx: Ctx, tools: list[str], personal: bool, sections: list[Section], claude_compat: bool = False) -> None:
    if not sections:
        return
    targets = choose_targets(ctx, tools, personal)
    for target in targets:
        _write_target(ctx, target, sections, personal)
    agents_md, claude_md = ctx.project / "AGENTS.md", ctx.project / "CLAUDE.md"
    if "claude" in tools and agents_md in targets and not personal:
        if claude_compat:
            _import_agents_md(ctx, claude_md)
        elif not (ctx.exists(claude_md) and IMPORT_RE.search(ctx.read(claude_md).decode("utf-8"))):
            ctx.warn("Claude Code reads CLAUDE.md, not AGENTS.md: add a line `@AGENTS.md` to CLAUDE.md (or re-run with "
                     "--claude-compat) so it sees these rules.")


def _write_target(ctx: Ctx, target: Path, sections: list[Section], personal: bool) -> None:
    existed = ctx.exists(target)
    raw = ctx.read(target) if existed else b""
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if personal and target.name == "CLAUDE.local.md" and not text.strip():
        agents_md, claude_md = ctx.project / "AGENTS.md", ctx.project / "CLAUDE.md"
        if ctx.exists(agents_md) and not ctx.exists(claude_md):
            text = "@AGENTS.md\n"  # CLAUDE.local.md hides AGENTS.md from Claude unless it imports it
    changed = []
    for section in sections:
        pattern = _marker_re(section.name)
        if pattern.search(text):
            updated = pattern.sub(lambda _m: section.block, text, count=1)
            if updated != text:
                text = updated
                changed.append(f"{section.name} (updated)")
            continue
        if _has_heading(text, section.heading):
            ctx.warn(f"{target.name} already has a '{section.heading}' section; left unchanged (your rules win). "
                     "Review it against the agentic-loadout version if you want both.")
            continue
        text = text.rstrip("\n") + ("\n\n" if text.strip() else "") + section.block + "\n"
        changed.append(section.name)
    if not changed:
        ctx.log("unchanged", target)
        return
    ctx.write(target, (text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))
    ctx.log(ctx.verb(target), target, "+ " + ", ".join(changed))


def _import_agents_md(ctx: Ctx, claude_md: Path) -> None:
    existed = ctx.exists(claude_md)
    text = ctx.read(claude_md).decode("utf-8") if existed else ""
    if IMPORT_RE.search(text):
        return
    ctx.write(claude_md, ("@AGENTS.md\n" + (("\n" + text) if text.strip() else "")).encode("utf-8"))
    ctx.log(ctx.verb(claude_md), claude_md, "+ @AGENTS.md import")
