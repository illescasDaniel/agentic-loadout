import json
import subprocess

from agentic_loadout import coders, install, pins, preflight
from agentic_loadout.files import Ctx
from agentic_loadout.options import Options
from agentic_loadout.runners import agemem_command, skills_command
from tests.conftest import FakeExecutor, make_system, prompter


def porcelain(repo):
    return subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True).stdout


def full(repo, tools=("claude",), executor=None, out=None, **kw):
    kw = {"yes": True, "no_input": True, **kw}
    opts = Options(project=repo, tools=list(tools), memory_model="jev", **kw)
    lines = out if out is not None else []
    code = install.run_install(opts, prompter(yes=opts.yes, no_input=opts.no_input), make_system()[0], executor or FakeExecutor(), lines.append)
    return code, "\n".join(lines)


def with_python_and_web(repo):
    (repo / "pyproject.toml").write_text("[project]\n")
    (repo / "package.json").write_text("{}")


def test_commands_are_project_scoped_and_pinned(repo):
    opts = Options(project=repo, tools=["claude", "cursor"], memory_model="qsiv", no_hooks=True)
    assert agemem_command(opts) == ["uvx", "--python", "3.12", "agemem@0.2.1", "project", "init", "--mcp", "claude", "cursor",
                                    "--model", "qsiv", "--no-hooks", "--no-input"]
    skills = skills_command(opts)
    assert "-g" not in skills and "--global" not in skills and "--copy" in skills and "skills@1.7.4" in skills
    assert skills.count("-a") == 2 and "claude-code" in skills and any("#" in part for part in skills)


def test_given_personal_claude_only_then_git_status_is_empty(repo):
    with_python_and_web(repo)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=x", "commit", "-qm", "m"], check=True)
    executor = FakeExecutor()
    code, out = full(repo, executor=executor, personal_settings=True)
    assert code == 0, out
    assert porcelain(repo) == ""
    assert (repo / "CLAUDE.local.md").read_text().startswith("@AGENTS.md")
    assert (repo / "AGENTS.md").read_text() == "# mine\n"
    assert executor.calls[1][1]["DISABLE_TELEMETRY"] == "1"


def test_given_personal_with_cursor_then_only_agents_md_shows_and_is_explained(repo):
    code, out = full(repo, tools=("claude", "cursor"), personal_settings=True)
    assert code == 0, out
    assert porcelain(repo).split() == ["M", "AGENTS.md"]
    assert "AGENTS.md is tracked" in out or "If AGENTS.md is tracked" in out


def test_given_existing_tracked_mcp_json_then_edit_is_explained(repo):
    (repo / ".mcp.json").write_text('{"mcpServers": {"mine": {"command": "x"}}}\n')
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=x", "commit", "-qm", "m"], check=True)
    (repo / "pyproject.toml").write_text("[project]\n")
    code, out = full(repo, personal_settings=True, executor=FakeExecutor(), with_coders=["python"])
    assert code == 0, out
    assert ".mcp.json: already tracked by git" in out and "skip-worktree" in out
    assert json.loads((repo / ".mcp.json").read_text())["mcpServers"]["mine"] == {"command": "x"}


def test_given_dry_run_then_nothing_runs_or_changes(repo):
    with_python_and_web(repo)
    executor = FakeExecutor()
    before = porcelain(repo)
    code, out = full(repo, executor=executor, dry_run=True)
    assert code == 0 and executor.calls == [] and porcelain(repo) == before
    assert "would run  uvx" in out and "would create .claude/agents/coder-python.md" in out


def test_given_full_install_then_no_jevmem_anywhere_and_grader_comes_from_the_skill(repo):
    with_python_and_web(repo)
    code, out = full(repo)
    assert code == 0, out
    grader = (repo / ".claude/agents/code-grader.md").read_text()
    assert grader.rstrip().endswith("# Grader body") and "model: opus" in grader
    for path in (repo / ".claude").rglob("*.md"):
        assert "jevmem" not in path.read_text().lower(), path
    assert "jevmem" not in (repo / ".agents/development-workflow.md").read_text().lower()
    assert not (repo / ".claude/settings.json").exists()
    assert "Project memory with Agemem" in (repo / "AGENTS.md").read_text()


def test_given_without_sdd_and_agemem_then_neither_runs_and_agents_have_no_memory_tools(repo):
    executor = FakeExecutor()
    code, out = full(repo, executor=executor, without=frozenset({"sdd", "agemem", "coders", "worktree"}))
    assert code == 0, out
    assert executor.calls == [] and not (repo / ".claude/agents/code-grader.md").exists()
    assert "agemem" not in (repo / ".claude/agents/coder.md").read_text()
    assert "Phase Gate" not in (repo / "AGENTS.md").read_text()


def test_given_missing_uvx_then_preflight_fails_before_any_write(repo, monkeypatch):
    opts = Options(project=repo, memory_model="jev")
    problems = preflight.check(opts, [], which=lambda name: None)
    assert any("uvx" in p for p in problems) and any("npx" in p for p in problems)
    monkeypatch.setattr(install, "check", lambda *_a, **_k: problems)
    executor = FakeExecutor()
    code, out = full(repo, executor=executor)
    assert code == 1 and "Cannot continue" in out and executor.calls == [] and porcelain(repo) == ""


def test_given_rerun_then_nothing_changes(repo):
    with_python_and_web(repo)
    full(repo)
    snapshot = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.relative_to(repo).parts}
    code, out = full(repo)
    assert code == 0, out
    assert {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.relative_to(repo).parts} == snapshot


def run_coders(repo, requested, tools=("claude",), system=None, answers=(), **kw):
    out = []
    opts = Options(project=repo, tools=list(tools), **kw)
    code = install.run_coders(opts, requested, False, prompter(*answers, yes=opts.yes, no_input=opts.no_input),
                              system or make_system()[0], out.append)
    return code, "\n".join(out)


def test_given_coder_then_agent_mcp_and_rule_are_installed_together(repo):
    code, out = run_coders(repo, ["python"], tools=("claude", "cursor", "codex"))
    assert code == 0, out
    assert "mcp__codenav__rename_symbol" in (repo / ".claude/agents/coder-python.md").read_text()
    assert (repo / ".cursor/agents/coder-python.md").exists() and (repo / ".codex/agents/coder-python.toml").exists()
    assert "codenav" in json.loads((repo / ".mcp.json").read_text())["mcpServers"]
    assert "codenav" in json.loads((repo / ".cursor/mcp.json").read_text())["mcpServers"]
    assert "mcp_servers.codenav" in (repo / ".codex/config.toml").read_text()
    assert "coder-python" in (repo / "AGENTS.md").read_text()


def test_given_detected_language_and_yes_answer_then_coder_is_installed(repo):
    (repo / "pyproject.toml").write_text("")
    code, out = run_coders(repo, None, answers=("y",))
    assert code == 0 and (repo / ".claude/agents/coder-python.md").exists()


def test_given_no_input_without_yes_then_nothing_is_installed_and_command_is_printed(repo):
    (repo / "pyproject.toml").write_text("")
    code, out = run_coders(repo, None, no_input=True)
    assert code == 0 and not (repo / ".claude/agents/coder-python.md").exists() and not (repo / ".mcp.json").exists()
    assert "agentic-loadout coders python" in out


def test_given_invalid_mcp_json_then_the_coder_is_not_left_half_installed(repo):
    (repo / ".mcp.json").write_text("{nope")
    code, out = run_coders(repo, ["python"])
    assert code == 1 and not (repo / ".claude/agents/coder-python.md").exists()
    assert "coder-python" not in (repo / "AGENTS.md").read_text()


def test_given_swift_on_linux_then_config_is_written_and_user_is_told(repo):
    code, out = run_coders(repo, ["swift"], tools=("claude", "cursor"))
    assert code == 0 and (repo / ".claude/agents/coder-swift.md").exists()
    assert "macOS" in out
    assert json.loads((repo / ".mcp.json").read_text())["mcpServers"]["codenav-swift"]["env"] == {"CODENAV_SWIFT_WRITE": "1"}


def test_given_swift_on_mac_with_brew_and_yes_flag_then_brew_still_asks(repo):
    system, calls = make_system("Darwin", binaries=("brew",), brew_prefix="/opt/homebrew")
    code, out = run_coders(repo, ["swift"], tools=("claude", "cursor"), system=system, answers=("n",), yes=True)
    assert code == 0
    assert ["brew", "install", "illescasDaniel/tap/codenav-swift-mcp"] not in calls  # --yes alone never installs it
    cursor = json.loads((repo / ".cursor/mcp.json").read_text())["mcpServers"]["codenav-swift"]
    assert cursor["command"] == "/opt/homebrew/bin/codenav-swift-mcp"


def test_given_src_layout_then_codenav_gets_source_root(repo):
    (repo / "src").mkdir()
    run_coders(repo, ["python"])
    assert json.loads((repo / ".mcp.json").read_text())["mcpServers"]["codenav"]["env"] == {"CODENAV_MCP_SOURCE_ROOT": "src"}


def test_status_reports_partial_and_installed(repo):
    ctx = Ctx(repo)
    opts = Options(project=repo)
    coder = coders.CODERS["python"]
    assert coders.status(ctx, coder, ["claude"]) == "absent"
    run_coders(repo, ["python"])
    assert coders.status(Ctx(repo), coder, ["claude"]) == "installed"
    (repo / ".claude/agents/coder-python.md").unlink()
    assert coders.status(Ctx(repo), coder, ["claude"]) == "partial"
    assert "partial" in coders.list_coders(Ctx(repo), opts)


def test_given_tracked_skills_lock_edited_by_skills_then_it_is_explained(repo):
    (repo / "skills-lock.json").write_text('{"version": 1}\n')
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=x", "commit", "-qm", "m"], check=True)
    code, out = full(repo, personal_settings=True)
    assert code == 0, out
    assert "skills-lock.json: already tracked by git" in out


def test_given_personal_settings_then_agemem_writes_local_claude_settings(repo):
    opts = Options(project=repo, tools=["claude"], memory_model="jev", personal_settings=True)
    assert agemem_command(opts)[-2:] == ["--local-settings", "--no-input"]
    assert "--local-settings" not in agemem_command(Options(project=repo, tools=["claude"], memory_model="jev"))


def test_given_shared_mode_then_no_absolute_path_warning(repo):
    code, out = full(repo, dry_run=True)
    assert code == 0, out
    assert "absolute project path" not in out
    assert ".claude/settings.json" in out and ".claude/settings.local.json" not in out


def test_given_yes_then_memory_model_is_not_asked(repo):
    opts = Options(project=repo, yes=True)
    p = prompter(yes=True)
    install.run_install(opts, p, make_system()[0], FakeExecutor(), lambda _l: None)
    assert opts.memory_model == "jev" and not p.asked


def test_given_worktree_component_then_skill_is_installed_pinned_and_rules_added(repo):
    executor = FakeExecutor()
    code, out = full(repo, executor=executor)
    assert code == 0, out
    adds = [c for c, _env in executor.calls if "add" in c]
    assert any(f"{pins.WORKTREE_SKILL}#{pins.WORKTREE_SKILL_REF}" in c for c in adds)
    assert all("-g" not in c for c in adds)
    agents_md = (repo / "AGENTS.md").read_text()
    assert "## Isolated worktrees" in agents_md and "/worktree apply" in agents_md


def test_given_without_worktree_then_neither_skill_nor_rules(repo):
    executor = FakeExecutor()
    code, out = full(repo, executor=executor, without=frozenset({"worktree"}))
    assert code == 0, out
    assert not any(pins.WORKTREE_SKILL in " ".join(c) for c, _env in executor.calls)
    assert "Isolated worktrees" not in (repo / "AGENTS.md").read_text()
