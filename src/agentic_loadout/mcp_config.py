"""Add MCP servers to a project's config files: `.mcp.json` (Claude), `.cursor/mcp.json` (Cursor) and
`.codex/config.toml` (Codex). Existing entries win and the rest of each file is kept."""

from __future__ import annotations

import tomllib
from pathlib import Path

from .files import Ctx, read_json, write_json
from .vendors import VENDORS, codex_server_block, cursor_server


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
