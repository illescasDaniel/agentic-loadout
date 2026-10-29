"""The subagents: generic ones from the shipped assets, the code-grader from the installed sdd skill, and the shared
workflow file. Agents are authored in Claude Code's format and converted for Cursor and Codex."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

from . import pins
from .files import Ctx, write_bytes
from .vendors import VENDORS, _split, agent_filename, convert_agent, workflow_path

ASSETS = Path(__file__).parent / "assets"
SKILL_DIRS = (".claude/skills", ".agents/skills", ".cursor/skills", ".codex/skills")
MEMORY_WRITE_TOOLS = ("capture", "remember", "index", "maintain")


def write_agent(ctx: Ctx, tools: list[str], name: str, claude_format: bytes) -> None:
    for tool in tools:
        dest = ctx.project / VENDORS[tool].agents_dir / agent_filename(tool, name)
        try:
            data = convert_agent(tool, claude_format)
            if tool == "codex":
                fields = tomllib.loads(data.decode("utf-8"))
                if not all(isinstance(fields.get(k), str) and fields[k].strip()
                           for k in ("name", "description", "developer_instructions")):
                    raise ValueError("agent needs a name, description and developer_instructions")
        except (ValueError, yaml.YAMLError) as exc:
            raise SystemExit(f"error: cannot generate agent {dest}: {exc}") from exc
        write_bytes(ctx, dest, data)


def without_memory(source: str) -> str:
    """Drop every agemem tool name from an agent file (used with --without agemem)."""
    source = re.sub(r",\s*mcp__agemem__\w+", "", source)
    return (source.replace("If the `project_memory_recall` tool is available", "If a memory-recall tool is available")
            .replace("`memory/` or agemem", "`memory/`"))


def installed_grader_body(project: Path) -> str | None:
    """Body of the code-grader that ships inside the installed sdd skill, so the two can't drift."""
    for folder in SKILL_DIRS:
        path = project / folder / pins.SDD_SKILL_NAME / "agents" / "code-grader.md"
        if path.is_file():
            return _split(path.read_text(encoding="utf-8"))[1]
    return None


def grader_bytes(ctx: Ctx, memory: bool) -> bytes | None:
    body = installed_grader_body(ctx.project)
    if body is None:
        if ctx.dry_run:
            ctx.log("would use", "code-grader", f"body from the installed {pins.SDD_SKILL_NAME} skill")
            return None
        raise SystemExit(f"error: the {pins.SDD_SKILL_NAME} skill (agents/code-grader.md) was not found; "
                         "re-run, or use --without sdd")
    head = (ASSETS / "agents" / "code-grader.head.md").read_text(encoding="utf-8")
    head = head if memory else without_memory(head)
    return (head + body).encode("utf-8")


def install_agents(ctx: Ctx, tools: list[str], sdd: bool, memory: bool) -> None:
    for agent in sorted((ASSETS / "agents").glob("*.md")):
        if agent.name.endswith(".head.md"):
            continue
        text = agent.read_text(encoding="utf-8")
        write_agent(ctx, tools, agent.stem, (text if memory else without_memory(text)).encode("utf-8"))
    if sdd:
        grader = grader_bytes(ctx, memory)
        if grader is not None:
            write_agent(ctx, tools, "code-grader", grader)
    workflow = (ASSETS / "development-workflow.md").read_text(encoding="utf-8")
    write_bytes(ctx, ctx.project / workflow_path(tools), workflow.encode("utf-8"))
