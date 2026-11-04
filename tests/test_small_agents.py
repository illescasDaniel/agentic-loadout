import json
import tomllib

import pytest
import yaml

from tests.test_install import full, run_coders


def test_install_tiers_for_all_clients_and_preserve_customizations(repo):
    opts = dict(tools=("claude", "cursor", "codex"), with_coders=["python"],
                without=frozenset({"agemem", "sdd", "worktree"}))
    code, output = full(repo, **opts)
    assert code == 0, output
    claude = (repo / ".claude/agents/coder-python-small.md").read_text()
    front = yaml.safe_load(claude.split("---", 2)[1])
    assert front["model"] == "haiku" and front["effort"] == "high"
    assert "mcp__codenav__rename_symbol" in front["tools"]
    codex = tomllib.loads((repo / ".codex/agents/coder-python-small.toml").read_text())
    assert codex["model"] == "gpt-6-luna" and codex["model_reasoning_effort"] == "high"
    reviewer = tomllib.loads((repo / ".codex/agents/code-reviewer.toml").read_text())
    assert reviewer["model"] == "gpt-6.1-terra" and reviewer["developer_instructions"].startswith("You are read-only")
    cursor = yaml.safe_load((repo / ".cursor/agents/code-reviewer.md").read_text().split("---", 2)[1])
    assert cursor["readonly"] and cursor["model"] == "gpt-6.1-terra"
    assert "coder-python-small" in (repo / "AGENTS.md").read_text()
    assert len(json.loads((repo / ".mcp.json").read_text())["mcpServers"]) == 1
    custom = repo / ".claude/agents/coder-python.md"
    custom.write_text("custom\n")
    (repo / ".claude/agents/coder-python-small.md").unlink()
    code, output = full(repo, **opts)
    assert code == 0 and custom.read_text() == "custom\n" and "skipped" in output
    assert (repo / ".claude/agents/coder-python-small.md").exists()
    code, output = full(repo, **opts, force=True)
    assert code == 0 and custom.read_text() != "custom\n"


def test_standalone_coder_and_without_agents(repo):
    code, output = run_coders(repo, ["python"])
    assert code == 0, output
    assert (repo / ".claude/agents/coder-python-small.md").exists()
    assert (repo / ".claude/agents/code-reviewer.md").exists()
    assert not (repo / ".claude/agents/coder-small.md").exists()
    assert "delegation-tiers.md" in (repo / "AGENTS.md").read_text()
    code, output = full(repo, with_coders=["python"], without=frozenset({"agents", "sdd", "agemem", "worktree"}))
    assert code == 0, output
    assert not (repo / ".claude/agents/coder-small.md").exists()


def test_dry_run_does_not_install_tiers(repo):
    code, output = full(repo, with_coders=["python"], dry_run=True,
                        without=frozenset({"sdd", "agemem", "worktree"}))
    assert code == 0 and "coder-python-small" in output
    assert not (repo / ".claude").exists()


def test_existing_agent_outputs_match_baseline(repo):
    import hashlib
    from pathlib import Path

    code, output = full(repo, tools=("claude", "cursor", "codex"), with_coders=["python"],
                        without=frozenset({"agemem", "sdd", "worktree"}))
    assert code == 0, output
    baseline = json.loads((Path(__file__).parent / "baseline-agent-hashes.json").read_text())
    for path, digest in baseline.items():
        assert hashlib.sha256((repo / path).read_bytes()).hexdigest() == digest, path


def test_go_coder_installs_both_tiers_and_navigation_for_all_clients(repo):
    from agentic_loadout import pins

    code, output = run_coders(repo, ["go"], tools=("claude", "cursor", "codex"))
    assert code == 0, output
    claude = yaml.safe_load((repo / ".claude/agents/coder-go-small.md").read_text().split("---", 2)[1])
    assert claude["model"] == "haiku" and "mcp__codenav-go__rename_symbol" in claude["tools"]
    assert (repo / ".claude/agents/coder-go.md").exists()
    codex = tomllib.loads((repo / ".codex/agents/coder-go-small.toml").read_text())
    assert codex["model"] == "gpt-6-luna" and codex["model_reasoning_effort"] == "high"
    assert (repo / ".codex/agents/coder-go.toml").exists()
    server = tomllib.loads((repo / ".codex/config.toml").read_text())["mcp_servers"]["codenav-go"]
    assert server["args"] == ["run", pins.CODENAV_GO_SPEC] and server["startup_timeout_sec"] == 60
    assert json.loads((repo / ".mcp.json").read_text())["mcpServers"]["codenav-go"]["command"] == "go"
    cursor = json.loads((repo / ".cursor/mcp.json").read_text())["mcpServers"]["codenav-go"]
    assert cursor["env"]["CODENAV_GO_MCP_WORKSPACE"] == "${workspaceFolder}"
    assert "coder-go-small" in (repo / "AGENTS.md").read_text()
    assert "downloads the public MCP" in output


def test_go_rerun_migrates_only_the_wip_launcher_and_preserves_environment(repo):
    from agentic_loadout import pins
    from agentic_loadout.mcp_config import LEGACY_GO_BINARY

    (repo / ".codex").mkdir()
    (repo / ".codex/config.toml").write_text(
        f'[mcp_servers.codenav-go]\ncommand = "{LEGACY_GO_BINARY}"\n'
        'env = { CODENAV_GO_MCP_BUILD_FLAGS = "-tags=gtk3" }\n')
    (repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"codenav-go": {
        "command": LEGACY_GO_BINARY, "env": {"CODENAV_GO_MCP_BUILD_FLAGS": "-tags=gtk3"}}}}))
    before = (repo / ".codex/config.toml").read_bytes()
    code, output = run_coders(repo, ["go"], tools=("claude", "codex"), dry_run=True)
    assert code == 0, output
    assert (repo / ".codex/config.toml").read_bytes() == before
    code, output = run_coders(repo, ["go"], tools=("claude", "codex"))
    assert code == 0, output
    codex = tomllib.loads((repo / ".codex/config.toml").read_text())["mcp_servers"]["codenav-go"]
    claude = json.loads((repo / ".mcp.json").read_text())["mcpServers"]["codenav-go"]
    for config in (codex, claude):
        assert config["command"] == "go" and config["args"] == ["run", pins.CODENAV_GO_SPEC]
        assert config["env"]["CODENAV_GO_MCP_BUILD_FLAGS"] == "-tags=gtk3"
    assert codex["startup_timeout_sec"] == 60
    code, output = run_coders(repo, ["go"], tools=("claude", "codex"))
    assert code == 0 and "migrated WIP" not in output


def test_go_rerun_preserves_custom_mcp_launcher(repo):
    (repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"codenav-go": {"command": "/custom/go-server"}}}))
    code, output = run_coders(repo, ["go"])
    assert code == 0, output
    assert json.loads((repo / ".mcp.json").read_text())["mcpServers"]["codenav-go"] == {"command": "/custom/go-server"}


@pytest.mark.parametrize("timeout", ["startup_timeout_sec = 90", "startup_timeout_ms = 90000"])
def test_go_migration_preserves_custom_codex_startup_timeout(repo, timeout):
    from agentic_loadout.mcp_config import LEGACY_GO_BINARY

    (repo / ".codex").mkdir()
    (repo / ".codex/config.toml").write_text(f'[mcp_servers.codenav-go]\ncommand = "{LEGACY_GO_BINARY}"\n{timeout}\n')
    code, output = run_coders(repo, ["go"], tools=("codex",))
    assert code == 0, output
    server = tomllib.loads((repo / ".codex/config.toml").read_text())["mcp_servers"]["codenav-go"]
    assert server["command"] == "go" and server[timeout.split(" = ")[0]] == int(timeout.split(" = ")[1])
    assert not ("startup_timeout_ms" in server and "startup_timeout_sec" in server)
