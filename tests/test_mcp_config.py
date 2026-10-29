import json
import tomllib

import pytest

from agent_loadout.files import Ctx
from agent_loadout.mcp_config import add_servers

SERVER = {"type": "stdio", "command": "uvx", "args": ["--from", "codenav-mcp>=0.2.1,<0.3", "codenav-mcp"], "env": {"A": "1"}}


def merge(tmp_path, tool, servers):
    ctx = Ctx(tmp_path)
    added = add_servers(ctx, tool, servers)
    ctx.apply()
    return added


def test_given_existing_json_when_added_then_other_keys_and_entries_survive(tmp_path):
    (tmp_path / ".mcp.json").write_text('{"mcpServers": {"mine": {"command": "x"}}, "other": 1}')
    assert merge(tmp_path, "claude", {"codenav": SERVER}) == ["codenav"]
    data = json.loads((tmp_path / ".mcp.json").read_text())
    assert data["other"] == 1 and data["mcpServers"]["mine"] == {"command": "x"}
    assert data["mcpServers"]["codenav"]["args"][1] == "codenav-mcp>=0.2.1,<0.3"  # specifier kept intact
    assert data["mcpServers"]["codenav"]["env"] == {"A": "1"}


def test_given_existing_entry_then_it_wins(tmp_path):
    (tmp_path / ".mcp.json").write_text('{"mcpServers": {"codenav": {"command": "mine"}}}')
    assert merge(tmp_path, "claude", {"codenav": SERVER}) == []
    assert json.loads((tmp_path / ".mcp.json").read_text())["mcpServers"]["codenav"] == {"command": "mine"}


def test_given_cursor_then_type_field_is_dropped(tmp_path):
    merge(tmp_path, "cursor", {"codenav": SERVER})
    assert "type" not in json.loads((tmp_path / ".cursor/mcp.json").read_text())["mcpServers"]["codenav"]


def test_given_codex_then_toml_table_is_appended_and_rest_kept(tmp_path):
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex/config.toml").write_text('model = "x"\n\n[mcp_servers.mine]\ncommand = "y"\n')
    assert merge(tmp_path, "codex", {"codenav": SERVER}) == ["codenav"]
    data = tomllib.loads((tmp_path / ".codex/config.toml").read_text())
    assert data["model"] == "x" and data["mcp_servers"]["mine"]["command"] == "y"
    assert data["mcp_servers"]["codenav"]["args"] == ["--from", "codenav-mcp>=0.2.1,<0.3", "codenav-mcp"]
    assert data["mcp_servers"]["codenav"]["env"] == {"A": "1"}
    assert merge(tmp_path, "codex", {"codenav": SERVER}) == []


def test_given_invalid_json_then_it_fails_without_writing(tmp_path):
    (tmp_path / ".mcp.json").write_text("{nope")
    with pytest.raises(SystemExit):
        merge(tmp_path, "claude", {"codenav": SERVER})
    assert (tmp_path / ".mcp.json").read_text() == "{nope"
