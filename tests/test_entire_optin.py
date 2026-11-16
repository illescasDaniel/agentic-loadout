"""Entire is opt-in (--with entire / --entire), kept for a project that already uses it, and degrades to a clear message
when the CLI is missing or too old."""

import json
import subprocess

import pytest

from agentic_loadout import cli, entire, install
from agentic_loadout.options import Options
from tests.conftest import FakeExecutor, make_system, prompter

MARKER_SECTION = "<!-- agentic-loadout:begin entire -->\n## Entire session history\n\nold text\n<!-- agentic-loadout:end entire -->\n"
LEAN = frozenset({"sdd", "worktree", "agents", "coders", "docs"})


class EntireExecutor(FakeExecutor):
    def __call__(self, cmd, cwd, env):
        if cmd[:3] == ["entire", "status", "--json"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps({"enabled": True, "checkpoint_push_disabled": True}), "")
        return super().__call__(cmd, cwd, env)


def run(repo, binaries=("entire", "npx"), version="0.13.2", dry_run=False, **kw):
    out = []
    kw = {"without": LEAN, **kw}
    opts = Options(project=repo, tools=["claude"], no_input=True, yes=True, dry_run=dry_run, **kw)
    executor = EntireExecutor()
    code = install.run_install(opts, prompter(yes=True, no_input=True), make_system(binaries=binaries, entire_version=version)[0],
                               executor, out.append)
    return code, "\n".join(out), executor


def parse(monkeypatch, repo, *argv):
    seen = {}
    monkeypatch.setattr(cli, "run_install", lambda opts, prompter: seen.setdefault("opts", opts) and 0)
    code = cli.main([str(repo), *argv, "--tools", "claude"])
    return code, seen["opts"]


def test_the_flags_turn_entire_on_and_do_not_disturb_the_language_coders(monkeypatch, repo):
    assert parse(monkeypatch, repo)[1].entire is False
    for argv in (["--entire"], ["--with", "entire"]):
        opts = parse(monkeypatch, repo, *argv)[1]
        assert opts.entire is True and opts.with_coders is None and opts.entire_upload_sessions is False
    opts = parse(monkeypatch, repo, "--with", "go,python")[1]
    assert opts.entire is False and sorted(opts.with_coders) == ["go", "python"]
    opts = parse(monkeypatch, repo, "--with", "go,entire")[1]
    assert opts.entire is True and opts.with_coders == ["go"]
    opts = parse(monkeypatch, repo, "--with", "entire", "--without", "coders")[1]
    assert opts.entire is True and opts.with_coders is None and "coders" in opts.without
    assert parse(monkeypatch, repo, "--without", "entire")[1].entire is False


def test_contradictory_flags_are_rejected(monkeypatch, repo):
    for argv in (["--entire", "--without", "entire"], ["--with", "entire", "--without", "entire"],
                 ["--with", "go", "--without", "coders"]):
        with pytest.raises(SystemExit, match="contradict"):
            parse(monkeypatch, repo, *argv)


def test_entire_flag_is_not_an_abbreviation_of_the_upload_flag(monkeypatch, repo):
    opts = parse(monkeypatch, repo, "--entire")[1]
    assert opts.entire and not opts.entire_upload_sessions
    assert parse(monkeypatch, repo, "--entire-upload-sessions")[1].entire_upload_sessions is True


def test_missing_cli_says_how_to_install_it_what_was_skipped_and_the_run_goes_on(repo):
    code, out, executor = run(repo, binaries=("npx",), entire=True)
    assert code == 0, out
    assert "`entire` CLI is not installed" in out and "brew install --cask entireio/tap/entire" in out
    assert "https://entire.com/install.sh" in out and "--with entire" in out and "Skipped: checkpoint capture" in out
    assert not any(c[0] == "entire" for c, _env in executor.calls) and not (repo / ".entire").exists()
    rules = (repo / "AGENTS.md").read_text()
    assert "Entire session history" not in rules and "--entire" not in rules and "Project memory (memory-1)" in rules
    assert (repo / ".claude/skills/memory-1/SKILL.md").is_file()


def test_an_older_cli_is_refused_with_the_minimum_version(repo):
    code, out, executor = run(repo, entire=True, version="0.9.4")
    assert code == 0, out
    assert "0.9.4" in out and "0.10.0" in out and "0.12.2 and 0.13.2" in out and "Upgrade it" in out
    assert not any(c[0] == "entire" for c, _env in executor.calls)
    assert "Entire session history" not in (repo / "AGENTS.md").read_text()


def test_the_minimum_version_and_the_unreadable_version_case():
    assert entire.MIN_VERSION == (0, 10, 0)
    assert entire.cli_problem(make_system(binaries=("entire",), entire_version="0.10.0")[0]) is None
    assert entire.cli_problem(make_system(binaries=("entire",), entire_version="0.13.2-nightly.5")[0]) is None
    assert entire.cli_problem(make_system(binaries=("entire",), entire_version="0.9.9")[0])
    assert entire.cli_problem(make_system(binaries=("entire",), entire_version="1.0.0")[0]) is None
    system = make_system(binaries=("entire",))[0]
    system.run = lambda cmd: subprocess.CompletedProcess(cmd, 0, "something unexpected", "")
    assert entire.cli_problem(system) is None


def test_a_supported_cli_enables_capture_and_writes_the_rules_with_the_flag(repo):
    code, out, executor = run(repo, entire=True)
    assert code == 0, out
    assert any(c[:2] == ["entire", "enable"] for c, _env in executor.calls)
    rules = (repo / "AGENTS.md").read_text()
    assert "## Entire session history" in rules and "memory/sessions --entire`" in rules


def test_a_project_with_the_entire_section_keeps_entire_on_and_says_so(repo):
    (repo / "AGENTS.md").write_text("# mine\n\n" + MARKER_SECTION)
    code, out, executor = run(repo)
    assert code == 0, out
    assert "Entire stays on" in out and any(c[:2] == ["entire", "enable"] for c, _env in executor.calls)
    rules = (repo / "AGENTS.md").read_text()
    assert "old text" not in rules and "memory/sessions --entire`" in rules and rules.count("agentic-loadout:begin entire") == 1


def test_the_marker_in_claude_local_md_counts_too(repo):
    (repo / "CLAUDE.local.md").write_text(MARKER_SECTION)
    code, out, _executor = run(repo, personal_settings=True)
    assert code == 0, out
    assert "Entire stays on" in out


def test_without_entire_turns_it_off_and_removes_the_rules_section(repo):
    (repo / "AGENTS.md").write_text("# mine\n\n" + MARKER_SECTION)
    code, out, executor = run(repo, without=LEAN | {"entire"})
    assert code == 0, out
    rules = (repo / "AGENTS.md").read_text()
    assert "Entire session history" not in rules and "--entire" not in rules and "# mine" in rules
    assert not any(c[0] == "entire" for c, _env in executor.calls) and "entire disable" in out
    assert run(repo, without=LEAN | {"entire"})[0] == 0 and (repo / "AGENTS.md").read_text() == rules


def test_a_marked_project_on_a_machine_without_the_cli_keeps_its_shared_rules(repo):
    (repo / "AGENTS.md").write_text("# mine\n\n" + MARKER_SECTION)
    code, out, executor = run(repo, binaries=("npx",))
    assert code == 0, out
    assert "not installed" in out and not any(c[0] == "entire" for c, _env in executor.calls)
    rules = (repo / "AGENTS.md").read_text()
    assert "## Entire session history" in rules and "memory/sessions --entire`" in rules


def test_dry_run_with_entire_only_reads_the_version(repo):
    code, out, executor = run(repo, entire=True, dry_run=True)
    assert code == 0 and executor.calls == [] and "would run  entire enable" in out
    assert not (repo / ".entire").exists() and "memory" not in [p.name for p in repo.iterdir()]


def test_upload_flag_needs_entire_to_be_requested(repo):
    code, out, _executor = run(repo, entire_upload_sessions=True)
    assert code == 1 and "--with entire" in out
