"""The session archive of the adapted memory-1 export_sessions.py stays out of git and is shared across git worktrees.
Everything is synthetic: the agents' folders are monkeypatched to temporary ones, so no real transcript is read."""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "src/agentic_loadout/assets/skills/memory-1/scripts/export_sessions.py"
spec = importlib.util.spec_from_file_location("export_sessions_worktree", SCRIPT)
exporter = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = exporter
spec.loader.exec_module(exporter)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not on PATH")


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=x", *args],
                          capture_output=True, text=True, check=True)
    return done.stdout.strip()


@pytest.fixture
def claude_root(tmp_path, monkeypatch):
    home = tmp_path / "agent-home"
    monkeypatch.setattr(exporter, "HOME", home)
    monkeypatch.setattr(exporter, "CLAUDE_ROOT", home / ".claude/projects")
    monkeypatch.setattr(exporter, "CODEX_ROOT", home / ".codex/sessions")
    monkeypatch.setattr(exporter, "OPENCODE_DB", home / "opencode/opencode.db")
    return home / ".claude/projects"


def write_session(claude_root, cwd, sid):
    """A Claude Code transcript whose recorded working directory is `cwd`, in the folder Claude Code would use."""
    folder = claude_root / re.sub(r"[^A-Za-z0-9]", "-", str(cwd))
    folder.mkdir(parents=True, exist_ok=True)
    events = [{"type": "user", "cwd": str(cwd), "timestamp": "2026-11-01T10:00:00Z", "message": {"content": f"question {sid}"}},
              {"type": "assistant", "timestamp": "2026-11-01T10:01:00Z", "message": {"content": [{"type": "text", "text": "answer"}]}}]
    (folder / f"{sid}.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


def init_repo(path):
    path.mkdir(parents=True)
    git(path, "init", "-q")
    (path / "README.md").write_text("x")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "init")
    return path.resolve()


def test_a_fresh_repo_gets_a_gitignore_for_the_archive_and_no_session_file_shows_in_git(tmp_path, claude_root, monkeypatch):
    repo = init_repo(tmp_path / "proj")
    write_session(claude_root, repo, "aaaaaaaa-1111")
    monkeypatch.chdir(repo)
    assert exporter.main(["--project", str(repo)]) == 0
    assert (repo / "memory/.gitignore").read_text().splitlines() == ["/sessions"]
    assert not (repo / "memory/sessions/.gitignore").exists()
    assert list((repo / "memory/sessions").glob("*.md"))
    assert git(repo, "status", "--porcelain", "--untracked-files=all").splitlines() == ["?? memory/.gitignore"]
    # an existing memory/.gitignore keeps its lines; the rule is appended once
    (repo / "memory/.gitignore").write_text("scratch")
    assert exporter.main(["--project", str(repo), "--since", "2000-01-01"]) == 0
    (repo / "memory/sessions/2026-11-01-aaaaaaaa.md").write_text("old")
    assert exporter.main(["--project", str(repo)]) == 0
    assert (repo / "memory/.gitignore").read_text() == "scratch\n/sessions\n"


def test_b_linked_worktree_writes_to_the_main_checkout_and_both_see_every_session(tmp_path, claude_root, monkeypatch):
    main = init_repo(tmp_path / "main")
    (main / "memory").mkdir()
    (main / "memory/.gitignore").write_text("/sessions\n")
    git(main, "add", "-A")
    git(main, "commit", "-qm", "memory")
    wt = tmp_path / "elsewhere" / "wt"
    git(main, "worktree", "add", "-q", str(wt))
    wt = wt.resolve()
    write_session(claude_root, wt, "aaaaaaaa-1111")
    write_session(claude_root, main, "bbbbbbbb-2222")

    monkeypatch.chdir(wt)
    assert exporter.main(["--project", str(wt)]) == 0
    archive = main / "memory/sessions"
    assert sorted(p.name for p in archive.glob("*.md")) == ["2026-11-01-aaaaaaaa.md", "2026-11-01-bbbbbbbb.md"]
    assert git(main, "status", "--porcelain", "--untracked-files=all") == ""
    assert git(wt, "status", "--porcelain", "--untracked-files=all") == ""
    link = wt / "memory/sessions"
    if link.is_symlink():  # a symlink can fail on Windows without privileges; the export must not
        assert link.resolve() == archive.resolve()
        assert git(wt, "status", "--porcelain", "--untracked-files=all") == ""

    for p in archive.glob("*.md"):
        p.unlink()
    monkeypatch.chdir(main)
    assert exporter.main(["--project", str(main)]) == 0
    assert sorted(p.name for p in archive.glob("*.md")) == ["2026-11-01-aaaaaaaa.md", "2026-11-01-bbbbbbbb.md"]
    assert git(main, "status", "--porcelain", "--untracked-files=all") == ""


def test_an_explicit_out_is_respected_in_a_worktree(tmp_path, claude_root, monkeypatch):
    main = init_repo(tmp_path / "main")
    wt = tmp_path / "wt"
    git(main, "worktree", "add", "-q", str(wt))
    wt = wt.resolve()
    write_session(claude_root, wt, "aaaaaaaa-1111")
    assert exporter.main(["--project", str(wt), "--out", str(tmp_path / "mine")]) == 0
    assert (tmp_path / "mine/2026-11-01-aaaaaaaa.md").is_file()
    assert not (main / "memory").exists() and not (wt / "memory").exists()


def test_without_git_it_behaves_as_before(tmp_path, claude_root, monkeypatch):
    project = (tmp_path / "plain").resolve()
    project.mkdir()
    write_session(claude_root, project, "aaaaaaaa-1111")
    monkeypatch.chdir(project)
    monkeypatch.setenv("PATH", str(tmp_path / "no-git-here"))
    assert exporter.main(["--project", str(project)]) == 0
    assert (project / "memory/sessions/2026-11-01-aaaaaaaa.md").is_file()
    assert not (project / "memory/.gitignore").exists()
