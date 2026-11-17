"""memory-1 and docs-1 replace agemem: how they are installed, the rules they add, and what happens to a project that
was set up with agemem (loadout 0.6.x)."""

import json
import subprocess
import tomllib

import pytest

from agentic_loadout import cli, install, pins, skills
from agentic_loadout.agents import ASSETS
from agentic_loadout.options import Options
from tests.conftest import FakeExecutor, make_system
from tests.test_install import full, porcelain

AGEMEM_ENTRY = {"command": "uvx", "args": ["--python", "3.12", "agemem@0.4.0", "mcp"]}
AGEMEM_HOOKS = {event: {"hooks": [{"type": "command", "command": f"uvx agemem hook x # agemem:{event}", "timeout": 10}]}
                for event in ("SessionStart", "UserPromptSubmit")}
ENTIRE_HOOK = {"hooks": [{"type": "command", "command": "entire hooks claude-code session-start"}]}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def agemem_project(repo):
    """What loadout 0.6.x plus agemem leave behind, next to entries that belong to other tools."""
    write_json(repo / ".mcp.json", {"mcpServers": {"agemem": AGEMEM_ENTRY, "mine": {"command": "x"}}})
    write_json(repo / ".cursor/mcp.json", {"mcpServers": {"agemem": {**AGEMEM_ENTRY, "args": ["agemem@0.4.0", "mcp", "--project", "${workspaceFolder}"]}}})
    (repo / ".codex").mkdir()
    (repo / ".codex/config.toml").write_text('[mcp_servers.other]\ncommand = "o"\n\n[mcp_servers.agemem]\ncommand = "uvx"\n'
                                             'args = ["agemem@0.4.0", "mcp"]\n\n[mcp_servers.agemem.env]\nA = "1"\n')
    write_json(repo / ".claude/settings.json", {"autoMemoryEnabled": False, "hooks": {
        "SessionStart": [{"hooks": AGEMEM_HOOKS["SessionStart"]["hooks"]}, ENTIRE_HOOK],
        "UserPromptSubmit": [AGEMEM_HOOKS["UserPromptSubmit"]]}})
    write_json(repo / ".codex/hooks.json", {"hooks": {"SessionStart": [AGEMEM_HOOKS["SessionStart"], ENTIRE_HOOK]}})
    (repo / ".agemem").mkdir()
    (repo / ".agemem/config.json").write_text('{"decision_backend":"jev"}\n')
    (repo / "memory").mkdir()
    (repo / "memory/activeContext.md").write_text("old state\n")
    (repo / ".claude/skills/memory-wrapup").mkdir(parents=True)
    (repo / ".claude/skills/memory-wrapup/SKILL.md").write_text("old skill")
    (repo / "AGENTS.md").write_text("# mine\n\n<!-- agentic-loadout:begin memory -->\n## Project memory with Agemem\n\n"
                                    "- call `project_memory_recall`\n<!-- agentic-loadout:end memory -->\n")


def test_memory_and_docs_skills_are_copied_from_the_shipped_files_without_npx(repo):
    executor = FakeExecutor()
    code, out = full(repo, executor=executor, tools=("claude", "cursor", "codex"))
    assert code == 0, out
    for name in ("memory-1", "docs-1"):
        for folder in (".claude/skills", ".agents/skills"):
            for rel, data in skills.vendored_files(name).items():
                assert (repo / folder / name / rel).read_bytes() == data, (folder, name, rel)
    assert (repo / ".claude/skills/memory-1/templates/.gitignore").is_file()
    installed = {c[c.index("add") + 1].split("#")[0] for c, _env in executor.calls if "add" in c}
    assert installed == {pins.SDD_SKILL, pins.WORKTREE_SKILL}  # memory-1 and docs-1 need no download
    assert not any("uvx" in c[0] for c, _env in executor.calls)


def test_the_shipped_pins_are_full_commit_ids_recorded_with_the_copies():
    assert len(pins.MEMORY_SKILL_REF) == len(pins.DOCS_SKILL_REF) == 40
    notes = (ASSETS / "skills/UPSTREAM.md").read_text()
    assert pins.MEMORY_SKILL_REF in notes and pins.DOCS_SKILL_REF in notes


def test_without_memory_or_docs_the_skill_and_its_rules_are_left_out(repo):
    executor = FakeExecutor()
    code, out = full(repo, executor=executor, without=frozenset({"docs"}))
    rules = (repo / "AGENTS.md").read_text()
    assert code == 0 and "Project memory (memory-1)" in rules and "Project docs" not in rules
    assert not (repo / ".claude/skills/docs-1").exists() and (repo / ".claude/skills/memory-1").exists()
    other = repo / "nomem"
    other.mkdir()
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    code, out = full(other, without=frozenset({"memory"}))
    assert code == 0 and "Project memory (memory-1)" not in (other / "AGENTS.md").read_text()
    assert not (other / ".claude/skills/memory-1").exists()
    assert "autoMemoryEnabled" not in (other / ".claude/settings.json").read_text() if (other / ".claude/settings.json").exists() else True


def test_rules_use_the_skill_folder_of_the_selected_client(repo):
    full(repo, tools=("claude",))
    assert "python3 .claude/skills/memory-1/scripts/export_sessions.py" in (repo / "AGENTS.md").read_text()
    assert "python3 .claude/skills/docs-1/scripts/docs_index.py covers" in (repo / "AGENTS.md").read_text()


def test_rules_for_codex_point_at_agents_skills_and_no_claude_settings_are_written(repo):
    code, out = full(repo, tools=("codex",))
    assert code == 0, out
    assert "python3 .agents/skills/memory-1/scripts/memory_check.py" in (repo / "AGENTS.md").read_text()
    assert not (repo / ".claude/settings.json").exists()


def test_claude_builtin_auto_memory_setting_is_never_written_and_an_existing_value_is_left_alone(repo):
    full(repo)
    assert not (repo / ".claude/settings.json").exists()
    other = repo / "other"
    other.mkdir()
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    write_json(other / ".claude/settings.json", {"autoMemoryEnabled": True, "model": "x"})
    write_json(other / ".claude/settings.local.json", {"autoMemoryEnabled": False})
    full(other, model="sonnet")
    assert json.loads((other / ".claude/settings.json").read_text()) == {"autoMemoryEnabled": True, "model": "sonnet"}
    assert json.loads((other / ".claude/settings.local.json").read_text()) == {"autoMemoryEnabled": False}


def test_upgrade_removes_only_agemem_entries_and_leaves_the_users_memory(repo):
    agemem_project(repo)
    executor = FakeExecutor()
    code, out = full(repo, tools=("claude", "cursor", "codex"), executor=executor, without=frozenset({"entire"}))
    assert code == 0, out
    assert json.loads((repo / ".mcp.json").read_text()) == {"mcpServers": {"mine": {"command": "x"}}}
    assert "agemem" not in json.loads((repo / ".cursor/mcp.json").read_text())["mcpServers"]
    config = tomllib.loads((repo / ".codex/config.toml").read_text())
    assert list(config["mcp_servers"]) == ["other"] and "agemem" not in (repo / ".codex/config.toml").read_text()
    claude = json.loads((repo / ".claude/settings.json").read_text())
    assert claude["hooks"] == {"SessionStart": [{"hooks": []}, ENTIRE_HOOK]} or claude["hooks"] == {"SessionStart": [ENTIRE_HOOK]}
    assert claude["autoMemoryEnabled"] is False
    assert json.loads((repo / ".codex/hooks.json").read_text()) == {"hooks": {"SessionStart": [ENTIRE_HOOK]}}
    assert any("remove" in c and pins.LEGACY_WRAPUP_SKILL_NAME in c for c, _env in executor.calls)
    assert not (repo / ".claude/skills/memory-wrapup").exists()
    # What the user stored is not deleted, and the final message says so.
    assert (repo / ".agemem/config.json").exists() and (repo / "memory/activeContext.md").read_text() == "old state\n"
    assert "Left on disk" in out and ".agemem/" in out and "memory/activeContext.md" in out
    rules = (repo / "AGENTS.md").read_text()
    assert "Agemem" not in rules and "project_memory" not in rules and "# mine" in rules
    assert "previous memory system (agemem)" in rules


def test_upgrade_is_idempotent(repo):
    agemem_project(repo)
    full(repo, tools=("claude", "cursor", "codex"), without=frozenset({"entire"}))
    snapshot = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.relative_to(repo).parts}
    executor = FakeExecutor()
    code, out = full(repo, tools=("claude", "cursor", "codex"), executor=executor, without=frozenset({"entire"}))
    assert code == 0 and {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.relative_to(repo).parts} == snapshot
    assert not any("remove" in c for c, _env in executor.calls)


def test_upgrade_dry_run_changes_nothing_and_shows_what_would_be_removed(repo):
    agemem_project(repo)
    before = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.relative_to(repo).parts}
    executor = FakeExecutor()
    code, out = full(repo, executor=executor, dry_run=True)
    assert code == 0 and executor.calls == []
    assert {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.relative_to(repo).parts} == before
    assert "removed the agemem server" in out and "would run  npx" in out and "remove memory-wrapup" in out


def test_agemem_server_of_a_client_that_is_not_selected_is_reported_not_edited(repo):
    agemem_project(repo)
    before = (repo / ".cursor/mcp.json").read_bytes()
    code, out = full(repo, tools=("claude",), without=frozenset({"entire"}))
    assert code == 0 and (repo / ".cursor/mcp.json").read_bytes() == before
    assert ".cursor/mcp.json still registers agemem" in out


def test_a_server_named_agemem_that_does_not_launch_agemem_is_left_alone(repo):
    write_json(repo / ".mcp.json", {"mcpServers": {"agemem": {"command": "my-own-thing"}}})
    code, out = full(repo)
    assert code == 0 and json.loads((repo / ".mcp.json").read_text())["mcpServers"] == {"agemem": {"command": "my-own-thing"}}
    assert "does not launch agemem" in out


def test_failure_to_remove_the_old_skill_is_a_warning_with_the_path(repo):
    agemem_project(repo)

    class Failing(FakeExecutor):
        def __call__(self, cmd, cwd, env):
            if "remove" in cmd:
                return subprocess.CompletedProcess(cmd, 1, "", "boom")
            return super().__call__(cmd, cwd, env)

    code, out = full(repo, executor=Failing(), without=frozenset({"entire"}))
    assert code == 0 and "Could not remove the old `memory-wrapup` skill" in out and ".claude/skills/memory-wrapup" in out


def test_without_memory_leaves_an_agemem_project_untouched(repo):
    agemem_project(repo)
    before = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.relative_to(repo).parts}
    code, out = full(repo, without=frozenset({"memory", "docs", "sdd", "worktree", "agents", "coders", "entire"}))
    assert code == 0 and {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.relative_to(repo).parts} == before


class EntireExecutor(FakeExecutor):
    def __call__(self, cmd, cwd, env):
        if cmd[:3] == ["entire", "status", "--json"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps({"enabled": True, "checkpoint_push_disabled": True}), "")
        return super().__call__(cmd, cwd, env)


def install_with_entire(repo, **kw):
    out = []
    opts = Options(project=repo, tools=["claude"], no_input=True, yes=True, **kw)
    code = install.run_install(opts, __import__("tests.conftest", fromlist=["prompter"]).prompter(yes=True, no_input=True),
                               make_system(binaries=("entire", "npx", "uvx"))[0], EntireExecutor(), out.append)
    return code, "\n".join(out)


def test_entire_with_memory_puts_the_flag_in_the_rules_and_installs_no_extra_script(repo):
    code, out = install_with_entire(repo, entire=True, without=frozenset({"sdd", "worktree", "agents", "coders"}))
    assert code == 0, out
    assert not (repo / ".agents/scripts").exists()
    rules = (repo / "AGENTS.md").read_text()
    assert "memory/sessions --entire`" in rules and "also adds sessions that only Entire has" in rules
    assert "Entire session history" in rules and "git grep" in rules and "refs/entire/checkpoints" in rules
    assert "entire_sessions.py" not in rules and "agemem" not in rules.lower() and "project_memory_remember" not in rules
    assert b"agentic-loadout:begin entire-code" in (repo / ".claude/skills/memory-1/scripts/export_sessions.py").read_bytes()


def test_entire_without_memory_has_no_session_archive_rules(repo):
    code, out = install_with_entire(repo, entire=True, without=frozenset({"memory", "docs", "sdd", "worktree", "agents", "coders"}))
    assert code == 0, out
    rules = (repo / "AGENTS.md").read_text()
    assert "Entire session history" in rules and "--entire" not in rules and "export_sessions" not in rules


def test_entire_is_off_by_default_and_the_default_memory_rules_have_no_entire_flag(repo):
    code, out = full(repo)
    rules = (repo / "AGENTS.md").read_text()
    assert code == 0 and "Entire session history" not in rules and "--entire" not in rules
    assert not (repo / ".entire").exists() and not (repo / ".agents/scripts").exists()


def test_without_entire_there_is_no_entire_text(repo):
    code, _out = full(repo, without=frozenset({"entire"}))
    assert code == 0 and "Entire" not in (repo / "AGENTS.md").read_text()


def test_cli_accepts_the_old_flags_with_a_notice(monkeypatch, repo, capsys):
    seen = {}
    monkeypatch.setattr(cli, "run_install", lambda opts, prompter: seen.setdefault("opts", opts) and 0)
    assert cli.main([str(repo), "--without", "agemem,worktree", "--memory-model", "jev", "--tools", "claude"]) == 0
    assert seen["opts"].without == frozenset({"memory", "worktree"})
    assert "agemem is no longer installed" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        cli.main([str(repo), "--without", "nonsense"])


def test_rules_and_agents_mention_no_agemem_tools():
    for path in ASSETS.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if path.name == "memory-legacy.md":
            continue
        text = text.replace(".agemem/", "")  # memory-1 names the old folder when it looks for a memory to migrate
        assert "project_memory" not in text and "mcp__agemem" not in text and "agemem" not in text.lower(), path


def test_nothing_in_the_default_install_needs_uvx(repo):
    from agentic_loadout import preflight
    assert preflight.check(Options(project=repo), [], which=lambda name: "/x" if name == "npx" else None) == []
    assert not porcelain(repo)
