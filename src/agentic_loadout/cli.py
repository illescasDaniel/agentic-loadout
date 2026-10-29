"""Command line: `agentic-loadout [PATH] [flags]` for the full install, `agentic-loadout coders [LANGUAGE ...]` for the
language coders alone."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .coders import parse_languages
from .install import run_coders, run_install
from .options import COMPONENTS, Options
from .ui import Prompter
from .vendors import detect_tools, parse_tools


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--tools", help="comma-separated clients: claude,cursor,codex (default: detected from the project)")
    p.add_argument("--personal-settings", action="store_true", help="keep every change out of git (project-local files only)")
    p.add_argument("--git-exclude", action="store_true", help="list the files this run created in .git/info/exclude")
    p.add_argument("--claude-compat", action="store_true", help="write `@AGENTS.md` into CLAUDE.md so Claude Code reads AGENTS.md")
    p.add_argument("--dry-run", action="store_true", help="print what would run and change; write nothing")
    p.add_argument("--no-input", action="store_true", help="never ask; install nothing that needs a confirmation")
    p.add_argument("--yes", "-y", action="store_true", help="accept the detected suggestions (Homebrew is still asked)")
    p.add_argument("--allow-brew", action="store_true", help="allow the Homebrew install of codenav-swift-mcp without asking")
    p.add_argument("--force", action="store_true", help="overwrite agent files you edited")
    p.add_argument("--version", action="version", version=f"agentic-loadout {__version__}")


def main_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentic-loadout", description="Set up memory, skills, subagents and language coders in a project.",
                                epilog="Run `agentic-loadout coders --help` to add language coders on their own.")
    p.add_argument("path", nargs="?", default=".", help="project root (default: .)")
    _common(p)
    p.add_argument("--with", dest="with_", metavar="LANGS", help="language coders: python,swift,typescript or all (default: detect and confirm)")
    p.add_argument("--without", metavar="PARTS", help=f"leave parts out: {','.join(COMPONENTS)}")
    p.add_argument("--memory-model", choices=("jev", "qsiv"), help="agemem decision provider (default: ask; jev with --no-input)")
    p.add_argument("--no-hooks", action="store_true", help="do not install agemem's lifecycle hooks")
    p.add_argument("--model", help="Claude project model alias for .claude/settings.json (settings.local.json with --personal-settings)")
    return p


def coders_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentic-loadout coders", description="Install language coders: the coder-<lang> subagent, "
                                "its code-navigation MCP and the routing rule, always together.")
    p.add_argument("languages", nargs="*", help="python, swift, typescript or all (default: detect and confirm)")
    p.add_argument("--path", default=".", help="project root (default: .)")
    p.add_argument("--list", action="store_true", help="show the catalogue, what is detected and what is installed")
    _common(p)
    return p


def _options(args: argparse.Namespace, path: str) -> Options:
    project = Path(path).expanduser().resolve()
    tools = parse_tools(args.tools) if args.tools else (detect_tools(project) if project.is_dir() else ["claude"])
    return Options(project=project, tools=tools, personal_settings=args.personal_settings, git_exclude=args.git_exclude,
                   claude_compat=args.claude_compat, dry_run=args.dry_run, no_input=args.no_input, yes=args.yes,
                   allow_brew=args.allow_brew, force=args.force)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "coders":
        args = coders_parser().parse_args(argv[1:])
        opts = _options(args, args.path)
        requested = parse_languages(args.languages) if args.languages else None
        return run_coders(opts, requested, args.list, Prompter(opts.yes, opts.no_input))
    args = main_parser().parse_args(argv)
    opts = _options(args, args.path)
    parts = [p.strip().lower() for p in (args.without or "").split(",") if p.strip()]
    unknown = [p for p in parts if p not in COMPONENTS]
    if unknown:
        raise SystemExit(f"error: --without takes {', '.join(COMPONENTS)} (got {', '.join(unknown)})")
    opts.without, opts.memory_model, opts.no_hooks, opts.model = frozenset(parts), args.memory_model, args.no_hooks, args.model
    if args.with_:
        if "coders" in parts:
            raise SystemExit("error: --with and --without coders contradict each other")
        opts.with_coders = parse_languages([args.with_])
    return run_install(opts, Prompter(opts.yes, opts.no_input))


if __name__ == "__main__":
    raise SystemExit(main())
