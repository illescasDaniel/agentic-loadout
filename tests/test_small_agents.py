import json
import tomllib

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


def test_all_small_coders_set_high_effort(repo):
    code, output = full(repo, tools=("claude", "codex"), with_coders=["python", "typescript", "swift"],
                        without=frozenset({"agemem", "sdd", "worktree"}))
    assert code == 0, output
    for name in ("coder-small", "coder-python-small", "coder-typescript-small", "coder-swift-small"):
        claude = yaml.safe_load((repo / f".claude/agents/{name}.md").read_text().split("---", 2)[1])
        codex = tomllib.loads((repo / f".codex/agents/{name}.toml").read_text())
        assert (claude["model"], claude["effort"]) == ("haiku", "high")
        assert (codex["model"], codex["model_reasoning_effort"]) == ("gpt-6-luna", "high")


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
