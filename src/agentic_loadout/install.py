"""The install flows: the full run and the standalone `coders` command. Every step is idempotent; a re-run after a
failure is the recovery path."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from . import coders, entire, git_state, legacy, pins
from .agents import ASSETS, SKILL_DIRS as AGENT_SKILL_DIRS, install_agents, install_tier_agents
from .brew import System
from .files import Ctx, read_json, write_bytes, write_json
from .instructions import Section, apply_sections
from .options import Options
from .preflight import check
from .runners import Executor, default_executor, run, skills_command, skills_env
from .ui import Prompter
from .vendors import VENDORS, workflow_path

ENTIRE_SESSIONS_SCRIPT = ".agents/scripts/entire_sessions.py"
SKILL_DIRS = {"claude": ".claude/skills", "cursor": ".agents/skills", "codex": ".agents/skills"}


def _skill_writes(name: str) -> dict[str, list[str]]:
    return {tool: [f"{folder}/{name}/"] for tool, folder in SKILL_DIRS.items()}


def _writes(table: dict[str, list[str]], tools: list[str], *always: str) -> str:
    return ", ".join(dict.fromkeys([*always, *(p for t in tools for p in table[t])]))


def _rules(opts: Options) -> list[Section]:
    sections = []
    if opts.wants("agents"):
        names = [f"`{VENDORS[t].agents_dir}/`" for t in opts.selected()]
        dirs = ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1]
        body = (ASSETS / "templates" / "agents-rules.md").read_text(encoding="utf-8").strip()
        sections.append(Section("agents", body.replace("{{AGENTS_DIRS}}", dirs).replace("{{WORKFLOW}}", workflow_path(opts.tools))))
    return sections


def _template(name: str) -> str:
    return (ASSETS / "templates" / name).read_text(encoding="utf-8").strip()


def skill_dir(opts: Options) -> str:
    """Where the project-local skills live for the first selected client (the others get identical copies)."""
    return SKILL_DIRS[opts.selected()[0]]


def memory_present(project: Path) -> bool:
    """memory-1 is the project's memory: its skill is installed, or its status file exists."""
    return (project / "memory" / "NOW.md").is_file() or any(
        (project / folder / pins.MEMORY_SKILL_NAME / "SKILL.md").is_file() for folder in AGENT_SKILL_DIRS)


def _tail_rules(opts: Options) -> list[Section]:
    sections = []
    if opts.wants("memory"):
        old = _template("memory-legacy.md") if legacy.has_legacy_memory(opts.project) else ""
        body = _template("memory-rules.md").replace("{{LEGACY}}", old).replace("{{SKILL_DIR}}", skill_dir(opts))
        sections.append(Section("memory", re.sub(r"\n{3,}", "\n\n", body)))
    if opts.wants("docs"):
        sections.append(Section("docs", _template("docs-rules.md").replace("{{SKILL_DIR}}", skill_dir(opts))))
    if opts.wants("sdd"):
        sections.append(Section("sdd", _template("sdd-rules.md")))
    if opts.wants("worktree"):
        sections.append(Section("worktree", _template("worktree-rules.md")))
    return sections


def _entire_rules(opts: Options) -> Section:
    sessions = "\n" + _template("entire-sessions.md") + "\n" if opts.wants("memory") else ""
    return Section("entire", _template("entire-rules.md").replace("{{SESSIONS}}", sessions))


def install_settings(ctx: Ctx, opts: Options) -> None:
    """Claude Code only: `--model`, and turning off Claude's built-in auto-memory when memory-1 is the project's memory."""
    if "claude" not in opts.tools:
        return
    shared, personal = (ctx.project / ".claude" / n for n in ("settings.json", "settings.local.json"))
    target = personal if opts.personal_settings else shared
    data, indent = read_json(target, ctx)
    changes = []
    if opts.model and data.get("model") != opts.model:
        data["model"] = opts.model
        changes.append(f"model={opts.model}")
    # A value the user set in either project settings file is left alone (agemem used to do the same).
    if opts.wants("memory") and "autoMemoryEnabled" not in data and not any(
            "autoMemoryEnabled" in read_json(p, ctx)[0] for p in (shared, personal) if p != target):
        data["autoMemoryEnabled"] = False
        changes.append("autoMemoryEnabled=false")
    if changes:
        write_json(ctx, target, data, indent, changes)


def summary(ctx: Ctx, opts: Options, report: git_state.Report | None, out: Callable[[str], None]) -> None:
    out("\n".join(ctx.lines))
    if opts.dry_run:
        out("\nDry run: nothing was written.")
    if report is not None:
        if report.not_git and opts.hide:
            out("\nThis is not a git repository, so nothing could be hidden from git.")
        elif report.excluded:
            out(f"\nAdded {len(report.excluded)} entries to .git/info/exclude (this clone only):")
            out("\n".join(f"  {e}" for e in report.excluded))
        for line in git_state.explain_changes(report, opts.hide):
            ctx.warn(line)
    if ctx.warnings:
        out("\nReview:\n" + "\n".join(f"  - {w}" for w in ctx.warnings))
    if ctx.notes:
        out("\nNext:\n" + "\n".join(f"  - {n}" for n in ctx.notes))


def _run_install(opts: Options, prompter: Prompter, system: System | None = None, executor: Executor = default_executor,
                out: Callable[[str], None] = print) -> int:
    system = system or System()
    ctx = Ctx(opts.project, dry_run=opts.dry_run, force=opts.force)
    # Preflight: ask every question and check every tool before the first write.
    plan = coders.prepare(ctx, opts, prompter, system, opts.with_coders)
    problems = check(opts, plan.keys)
    if problems:
        out("Cannot continue:\n" + "\n".join(f"  - {p}" for p in problems))
        return 1
    before = git_state.snapshot(opts.project)
    if opts.dry_run:
        out("Dry run. Project scope only; these are the commands and the files they write:")
    try:
        if opts.wants("memory"):
            legacy.migrate(ctx, opts, executor)
            run(skills_command(opts, pins.MEMORY_SKILL, pins.MEMORY_SKILL_REF, pins.MEMORY_SKILL_NAME),
                opts, executor, ctx.lines.append, skills_env())
            ctx.lines.append(f"             writes {_writes(_skill_writes(pins.MEMORY_SKILL_NAME), opts.selected(), 'skills-lock.json')}")
        if opts.wants("docs"):
            run(skills_command(opts, pins.DOCS_SKILL, pins.DOCS_SKILL_REF, pins.DOCS_SKILL_NAME),
                opts, executor, ctx.lines.append, skills_env())
            ctx.lines.append(f"             writes {_writes(_skill_writes(pins.DOCS_SKILL_NAME), opts.selected(), 'skills-lock.json')}")
        if opts.wants("sdd"):
            run(skills_command(opts), opts, executor, ctx.lines.append, skills_env())
            ctx.lines.append(f"             writes {_writes(_skill_writes(pins.SDD_SKILL_NAME), opts.selected(), 'skills-lock.json')}")
        if opts.wants("worktree"):
            run(skills_command(opts, pins.WORKTREE_SKILL, pins.WORKTREE_SKILL_REF), opts, executor, ctx.lines.append, skills_env())
            ctx.lines.append(f"             writes {_writes(_skill_writes(pins.WORKTREE_SKILL_NAME), opts.selected(), 'skills-lock.json')}")
        entire_enabled = entire.install(ctx, opts, executor, system.which("entire") is not None)
        sections = _rules(opts)
        if entire_enabled:
            sections.append(_entire_rules(opts))
            if opts.wants("memory"):
                write_bytes(ctx, ctx.project / ENTIRE_SESSIONS_SCRIPT, (ASSETS / "scripts" / "entire_sessions.py").read_bytes())
        if opts.wants("agents"):
            install_agents(ctx, opts.selected(), opts.wants("sdd"), opts.wants("memory"))
        if opts.wants("agents") or plan.keys:
            install_tier_agents(ctx, opts.selected(), opts.wants("memory"), opts.wants("agents"), True)
        sections += coders.install(ctx, opts, plan, system, opts.wants("memory"))
        sections += _tail_rules(opts)
        apply_sections(ctx, opts.selected(), opts.personal_settings, sections, opts.claude_compat)
        install_settings(ctx, opts)
        ctx.apply()
        if entire_enabled:
            entire.verify(ctx, opts, executor)
    except SystemExit as exc:
        out("\n".join(ctx.lines))
        out(str(exc))
        out("Nothing is rolled back; fix the problem and re-run (every step is idempotent).")
        return 1
    ctx.note("Restart or reload your client(s) so they pick up the new skills, subagents and rules; approve any new MCP servers or hooks when asked.")
    report = git_state.finish(opts.project, before, opts.hide, opts.dry_run)
    summary(ctx, opts, report, out)
    return 0


def _run_coders(opts: Options, requested: list[str] | None, list_only: bool, prompter: Prompter, system: System | None = None,
               out: Callable[[str], None] = print) -> int:
    system = system or System()
    ctx = Ctx(opts.project, dry_run=opts.dry_run, force=opts.force)
    if list_only:
        out(coders.list_coders(ctx, opts))
        return 0
    memory = memory_present(opts.project)
    plan = coders.prepare(ctx, opts, prompter, system, requested)
    problems = check(Options(opts.project, opts.tools, without=frozenset({"memory", "docs", "sdd", "worktree"})), plan.keys)
    if problems:
        out("Cannot continue:\n" + "\n".join(f"  - {p}" for p in problems))
        return 1
    if not plan.keys:
        out("\n".join(ctx.lines + ["No coders installed."] + [f"  - {n}" for n in ctx.notes]))
        return 0
    before = git_state.snapshot(opts.project)
    try:
        install_tier_agents(ctx, opts.selected(), memory, False, True)
        sections = coders.install(ctx, opts, plan, system, memory)
        apply_sections(ctx, opts.selected(), opts.personal_settings, sections, opts.claude_compat)
        ctx.apply()
    except SystemExit as exc:
        out("\n".join(ctx.lines))
        out(str(exc))
        return 1
    ctx.note("Restart or reload your client(s) and approve the new MCP servers when asked.")
    summary(ctx, opts, git_state.finish(opts.project, before, opts.hide, opts.dry_run), out)
    return 0


def run_install(opts: Options, prompter: Prompter, system: System | None = None, executor: Executor = default_executor,
                out: Callable[[str], None] = print) -> int:
    try:
        return _run_install(opts, prompter, system, executor, out)
    except SystemExit as exc:  # a config we can't parse, an unreadable file: report it, never a traceback
        out(str(exc))
        return 1


def run_coders(opts: Options, requested: list[str] | None, list_only: bool, prompter: Prompter, system: System | None = None,
               out: Callable[[str], None] = print) -> int:
    try:
        return _run_coders(opts, requested, list_only, prompter, system, out)
    except SystemExit as exc:
        out(str(exc))
        return 1
