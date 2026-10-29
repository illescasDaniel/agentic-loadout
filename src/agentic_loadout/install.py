"""The install flows: the full run and the standalone `coders` command. Every step is idempotent; a re-run after a
failure is the recovery path."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import coders, git_state, pins
from .agents import ASSETS, install_agents
from .brew import System
from .files import Ctx, read_json, write_json
from .instructions import Section, apply_sections
from .mcp_config import servers_in
from .options import Options
from .preflight import check
from .runners import Executor, agemem_command, default_executor, run, skills_command, skills_env
from .ui import Prompter
from .vendors import VENDORS, workflow_path

AGEMEM_WRITES = {"claude": [".mcp.json", ".claude/settings.json"], "cursor": [".cursor/mcp.json"],
                 "codex": [".codex/config.toml", ".codex/hooks.json"]}  # checked in Phase 0 (PLAN.md §8a)
AGEMEM_PERSONAL_WRITES = {**AGEMEM_WRITES, "claude": [".mcp.json", ".claude/settings.local.json"]}  # --local-settings
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


def _tail_rules(opts: Options) -> list[Section]:
    sections = []
    if opts.wants("agemem"):
        sections.append(Section("memory", (ASSETS / "templates" / "memory-rules.md").read_text(encoding="utf-8").strip()))
    if opts.wants("sdd"):
        sections.append(Section("sdd", (ASSETS / "templates" / "sdd-rules.md").read_text(encoding="utf-8").strip()))
    if opts.wants("worktree"):
        sections.append(Section("worktree", (ASSETS / "templates" / "worktree-rules.md").read_text(encoding="utf-8").strip()))
    return sections


def install_settings(ctx: Ctx, opts: Options) -> None:
    """Claude Code only: `--model`. (agemem itself turns Claude's auto-memory off.)"""
    if "claude" not in opts.tools or not opts.model:
        return
    target = ctx.project / ".claude" / ("settings.local.json" if opts.personal_settings else "settings.json")
    data, indent = read_json(target, ctx)
    if data.get("model") != opts.model:
        data["model"] = opts.model
        write_json(ctx, target, data, indent, [f"model={opts.model}"])


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
    if opts.wants("agemem") and opts.memory_model is None:
        opts.memory_model = prompter.ask("Agemem decision provider (jev needs an API key later, qsiv runs locally)", ("jev", "qsiv"), "jev")
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
        if opts.wants("agemem"):
            run(agemem_command(opts), opts, executor, ctx.lines.append)
            writes = AGEMEM_PERSONAL_WRITES if opts.personal_settings else AGEMEM_WRITES
            ctx.lines.append(f"             writes {_writes(writes, opts.selected(), 'memory/', '.agemem/')}")
            if opts.memory_model == "jev":
                ctx.note("Memory with the jev provider needs an API key: set AGEMEM_JEV_API_KEY in your environment or "
                         "put it in ~/.config/agemem/config.yaml (agemem created that file). Never paste it into a chat.")
        if opts.wants("sdd"):
            run(skills_command(opts), opts, executor, ctx.lines.append, skills_env())
            ctx.lines.append(f"             writes {_writes(_skill_writes(pins.SDD_SKILL_NAME), opts.selected(), 'skills-lock.json')}")
        if opts.wants("worktree"):
            run(skills_command(opts, pins.WORKTREE_SKILL, pins.WORKTREE_SKILL_REF), opts, executor, ctx.lines.append, skills_env())
            ctx.lines.append(f"             writes {_writes(_skill_writes(pins.WORKTREE_SKILL_NAME), opts.selected(), 'skills-lock.json')}")
        sections = _rules(opts)
        if opts.wants("agents"):
            install_agents(ctx, opts.selected(), opts.wants("sdd"), opts.wants("agemem"))
        sections += coders.install(ctx, opts, plan, system, opts.wants("agemem"))
        sections += _tail_rules(opts)
        apply_sections(ctx, opts.selected(), opts.personal_settings, sections, opts.claude_compat)
        install_settings(ctx, opts)
        ctx.apply()
    except SystemExit as exc:
        out("\n".join(ctx.lines))
        out(str(exc))
        out("Nothing is rolled back; fix the problem and re-run (every step is idempotent).")
        return 1
    ctx.note("Restart or reload your client(s) and approve the new MCP servers and hooks when asked.")
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
    memory = "agemem" in servers_in(ctx, opts.selected()[0]) or (opts.project / ".agemem").is_dir()
    plan = coders.prepare(ctx, opts, prompter, system, requested)
    problems = check(Options(opts.project, opts.tools, without=frozenset({"agemem", "sdd"}), memory_model=opts.memory_model), plan.keys)
    if problems:
        out("Cannot continue:\n" + "\n".join(f"  - {p}" for p in problems))
        return 1
    if not plan.keys:
        out("\n".join(ctx.lines + ["No coders installed."] + [f"  - {n}" for n in ctx.notes]))
        return 0
    before = git_state.snapshot(opts.project)
    try:
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
