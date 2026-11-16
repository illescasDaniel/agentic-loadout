"""Upgrading a project that was set up with loadout 0.6.x: agemem is no longer installed, so its leftovers are removed.

Only what agemem itself wrote is touched, and only where it can be recognised: the `agemem` MCP server entry whose
launcher names agemem, hook handlers whose command ends with agemem's `# agemem:<Event>` marker, and the
`memory-wrapup` skill folder. Entries of other tools (Entire's hooks, other MCP servers) are never edited. Nothing
agemem stored (`.agemem/`, `memory/*.md`, its user config) is deleted: that is the user's memory, and the final
message says what is left.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import pins
from .agents import SKILL_DIRS
from .files import Ctx, read_json, write_json
from .mcp_config import _parse_toml, servers_in
from .options import Options
from .runners import Executor, run, skills_env, skills_remove_command
from .vendors import TOOLS, VENDORS

HOOK_MARKERS = (" # agemem:SessionStart", " # agemem:UserPromptSubmit")
HOOK_FILES = {"claude": [".claude/settings.json", ".claude/settings.local.json"], "codex": [".codex/hooks.json"]}
BANK_FILES = ("activeContext.md", "progress.md", "decisions.md", "archive.md")  # agemem's memory bank in memory/


def bank_files(project: Path) -> list[str]:
    return [f"memory/{name}" for name in BANK_FILES if (project / "memory" / name).is_file()]


def has_legacy_memory(project: Path) -> bool:
    """True while agemem's own files are still in the project, so the rules can tell the agent to migrate them."""
    return (project / ".agemem").exists() or bool(bank_files(project))


def _is_agemem_entry(entry: object) -> bool:
    return isinstance(entry, dict) and "agemem" in json.dumps(entry)


def _remove_json_server(ctx: Ctx, tool: str) -> bool:
    path = ctx.project / VENDORS[tool].mcp_file
    if not ctx.exists(path):
        return False
    data, indent = read_json(path, ctx)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or "agemem" not in servers:
        return False
    if not _is_agemem_entry(servers["agemem"]):
        ctx.warn(f"{path.relative_to(ctx.project)}: an `agemem` server that does not launch agemem was left alone.")
        return False
    del servers["agemem"]
    write_json(ctx, path, data, indent, ["removed the agemem server"])
    return True


def _remove_toml_server(ctx: Ctx) -> bool:
    path = ctx.project / VENDORS["codex"].mcp_file
    if not ctx.exists(path):
        return False
    text = ctx.read(path).decode("utf-8")
    entry = _parse_toml(path, text).get("mcp_servers", {}).get("agemem")
    if entry is None:
        return False
    if not _is_agemem_entry(entry):
        ctx.warn(f"{path.relative_to(ctx.project)}: an `agemem` server that does not launch agemem was left alone.")
        return False
    updated, count = re.subn(r"(?ms)^\[mcp_servers\.agemem(?:\.[^\]\n]+)?\][ \t]*\r?\n.*?(?=^\[|\Z)", "", text)
    if not count:
        ctx.warn(f"{path.relative_to(ctx.project)}: the agemem server is not a plain [mcp_servers.agemem] table; remove it by hand.")
        return False
    updated = re.sub(r"(\r?\n){3,}", r"\1\1", updated).rstrip() + "\n" if updated.strip() else ""
    _parse_toml(path, updated)
    ctx.write(path, updated.encode("utf-8"))
    ctx.log(ctx.verb(path), path, "- removed the agemem server")
    return True


def _is_agemem_handler(handler: object) -> bool:
    return isinstance(handler, dict) and str(handler.get("command", "")).endswith(HOOK_MARKERS)


def _remove_hooks(ctx: Ctx, rel: str) -> bool:
    path = ctx.project / rel
    if not ctx.exists(path):
        return False
    data, indent = read_json(path, ctx)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False
    removed = 0
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept = []
        for group in groups:
            handlers = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(handlers, list):
                kept.append(group)
                continue
            remaining = [h for h in handlers if not _is_agemem_handler(h)]
            removed += len(handlers) - len(remaining)
            if remaining or not handlers:
                kept.append({**group, "hooks": remaining})
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not removed:
        return False
    if not hooks:
        del data["hooks"]
    write_json(ctx, path, data, indent, [f"removed {removed} agemem hook(s)"])
    return True


def _installed_wrapup_dirs(project: Path) -> list[str]:
    return [f"{folder}/{pins.LEGACY_WRAPUP_SKILL_NAME}" for folder in SKILL_DIRS
            if (project / folder / pins.LEGACY_WRAPUP_SKILL_NAME / "SKILL.md").is_file()]


def migrate(ctx: Ctx, opts: Options, executor: Executor) -> bool:
    """Remove agemem's MCP entries, hooks and wrap-up skill. Returns True if the project had agemem."""
    selected = opts.selected()
    changed = []
    for tool in TOOLS:
        in_scope = tool in selected
        present = "agemem" in servers_in(ctx, tool) if ctx.exists(ctx.project / VENDORS[tool].mcp_file) else False
        hook_files = [f for f in HOOK_FILES.get(tool, []) if ctx.exists(ctx.project / f)]
        if not in_scope:
            if present:
                ctx.warn(f"{VENDORS[tool].mcp_file} still registers agemem; {tool} is not selected, so it was not changed "
                         "(re-run with --tools including it, or edit the file).")
            continue
        if tool == "codex":
            if _remove_toml_server(ctx):
                changed.append(VENDORS[tool].mcp_file)
        elif _remove_json_server(ctx, tool):
            changed.append(VENDORS[tool].mcp_file)
        for rel in hook_files:
            if _remove_hooks(ctx, rel):
                changed.append(rel)
    wrapup = _installed_wrapup_dirs(ctx.project)
    if wrapup:
        try:
            run(skills_remove_command(pins.LEGACY_WRAPUP_SKILL_NAME), opts, executor, ctx.lines.append, skills_env())
            changed.append(f"removed skill {pins.LEGACY_WRAPUP_SKILL_NAME}")
        except SystemExit:
            ctx.warn(f"Could not remove the old `{pins.LEGACY_WRAPUP_SKILL_NAME}` skill; delete {', '.join(wrapup)} yourself "
                     "(it belongs to agemem and refers to tools that no longer exist).")
    found = bool(changed) or has_legacy_memory(ctx.project)
    if found:
        left = [p for p in (".agemem/" if (ctx.project / ".agemem").exists() else None, *bank_files(ctx.project)) if p]
        message = ("This project used agemem, which loadout no longer installs; its MCP server, hooks and wrap-up skill were "
                   "removed from this project" if changed else "This project used agemem, which loadout no longer installs")
        if left:
            message += f". Left on disk for you to migrate or delete: {', '.join(left)}"
        ctx.note(message + ". agemem's user config (~/.config/agemem) and model cache are outside the project and untouched.")
    return found
