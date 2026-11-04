"""Add MCP servers to a project's config files: `.mcp.json` (Claude), `.cursor/mcp.json` (Cursor) and
`.codex/config.toml` (Codex). Existing entries win and the rest of each file is kept."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from .files import Ctx, read_json, write_json
from .vendors import VENDORS, codex_server_block, cursor_server

LEGACY_GO_BINARY = "/home/daniel/Projects/Code/MCPs/codenav-go-mcp/codenav-go-mcp"


def migrate_legacy_go_server(ctx: Ctx, tool: str, server: dict) -> None:
    """Replace only the exact WIP launcher we previously generated; preserve user settings."""
    path = ctx.project / VENDORS[tool].mcp_file
    if not ctx.exists(path):
        return
    if tool == "codex":
        text = ctx.read(path).decode("utf-8")
        existing = _parse_toml(path, text).get("mcp_servers", {}).get("codenav-go", {})
        if not isinstance(existing, dict) or existing.get("command") != LEGACY_GO_BINARY or "args" in existing:
            return
        pattern = r'(?ms)^\[mcp_servers\.codenav-go\][ \t]*\r?\n(.*?)(?=^\[|\Z)'
        match = re.search(pattern, text)
        if not match:
            ctx.warn(f"{path}: old Go MCP launcher was not migrated; update it manually.")
            return
        block = match.group(0)
        newline = "\r\n" if "\r\n" in block else "\n"
        old_line = r'(?m)^command[ \t]*=[ \t]*' + re.escape(json.dumps(LEGACY_GO_BINARY)) + r'[ \t]*(?=\r?$)'
        replacement = 'command = "go"' + newline + 'args = ' + json.dumps(server["args"])
        if "startup_timeout_sec" not in existing and "startup_timeout_ms" not in existing:
            replacement += newline + f'startup_timeout_sec = {server["startup_timeout_sec"]}'
        updated, count = re.subn(old_line, lambda _: replacement, block, count=1)
        if count != 1:
            ctx.warn(f"{path}: old Go MCP launcher was not migrated; update it manually.")
            return
        text = text[:match.start()] + updated + text[match.end():]
        _parse_toml(path, text)
        ctx.write(path, text.encode("utf-8"))
        ctx.log(ctx.verb(path), path, "migrated WIP Go MCP launcher")
        return
    data, indent = read_json(path, ctx)
    servers = data.get("mcpServers", {})
    existing = servers.get("codenav-go", {}) if isinstance(servers, dict) else {}
    if not isinstance(existing, dict) or existing.get("command") != LEGACY_GO_BINARY or "args" in existing:
        return
    existing["command"] = server["command"]
    existing["args"] = list(server["args"])
    write_json(ctx, path, data, indent, ["migrated WIP Go MCP launcher"])


def servers_in(ctx: Ctx, tool: str) -> dict:
    """Servers already registered for `tool` in the project (empty when the file doesn't exist)."""
    path = ctx.project / VENDORS[tool].mcp_file
    if tool == "codex":
        if not ctx.exists(path):
            return {}
        return _parse_toml(path, ctx.read(path).decode("utf-8")).get("mcp_servers", {})
    return read_json(path, ctx)[0].get("mcpServers", {})


def add_servers(ctx: Ctx, tool: str, servers: dict[str, dict]) -> list[str]:
    """Register `servers` ({key: Claude-format server}) for `tool`. Returns the keys that were added."""
    path = ctx.project / VENDORS[tool].mcp_file
    if tool == "codex":
        return _add_codex(ctx, path, servers)
    data, indent = read_json(path, ctx)
    registered = data.setdefault("mcpServers", {})
    if not isinstance(registered, dict):
        raise SystemExit(f"error: {path}: mcpServers must be an object")
    added = []
    for key, server in servers.items():
        if key not in registered:
            registered[key] = cursor_server(server) if tool == "cursor" else server
            added.append(key)
    write_json(ctx, path, data, indent, [f"{k} server" for k in added])
    return added


def _parse_toml(path: Path, text: str) -> dict:
    try:
        config = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"error: {path} is not valid TOML ({exc}); fix it or move it away and re-run")
    if not isinstance(config.get("mcp_servers", {}), dict):
        raise SystemExit(f"error: {path}: mcp_servers must be a table")
    return config


def _add_codex(ctx: Ctx, path: Path, servers: dict[str, dict]) -> list[str]:
    """Append [mcp_servers.<key>] tables; existing entries and the rest of the file are kept."""
    existed = ctx.exists(path)
    text = ctx.read(path).decode("utf-8") if existed else ""
    registered = _parse_toml(path, text).get("mcp_servers", {})
    todo = {k: v for k, v in servers.items() if k not in registered}
    if not todo:
        ctx.log("unchanged", path)
        return []
    updated = text.rstrip("\n") + ("\n\n" if text.strip() else "") + "\n".join(codex_server_block(k, v) for k, v in todo.items())
    _parse_toml(path, updated)
    ctx.write(path, updated.encode("utf-8"))
    ctx.log(ctx.verb(path), path, "+ " + ", ".join(f"{k} server" for k in todo))
    return list(todo)
