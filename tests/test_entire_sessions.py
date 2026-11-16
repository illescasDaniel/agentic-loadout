"""The Entire-to-memory/sessions adapter, against synthetic repositories that hold checkpoints the way Entire stores them
(one ref per checkpoint, or the entire/checkpoints/v1 branch). No Entire CLI is needed."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "src/agentic_loadout/assets/scripts/entire_sessions.py"
spec = importlib.util.spec_from_file_location("entire_sessions", SCRIPT)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

CODEX_ID = "01a1a3a8-af33-7792-91b3-777ab09edd59"
CLAUDE_ID = "5f0c2a1e-1111-4222-8333-444455556666"


def git(repo, *args, stdin=None):
    done = subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=x", *args],
                          input=stdin, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def make_tree(repo, files):
    """Write nested `files` ({path: bytes}) into git objects and return the root tree id."""
    entries = {}
    for path, data in files.items():
        head, _, rest = path.partition("/")
        entries.setdefault(head, {})[rest or ""] = data
    lines = []
    for name, sub in sorted(entries.items()):
        if "" in sub and len(sub) == 1:
            blob = subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"], input=sub[""],
                                  capture_output=True, check=True).stdout.decode().strip()
            lines.append(f"100644 blob {blob}\t{name}")
        else:
            lines.append(f"040000 tree {make_tree(repo, {k: v for k, v in sub.items()})}\t{name}")
    return git(repo, "mktree", stdin="\n".join(lines) + "\n")


def commit_ref(repo, ref, files):
    tree = make_tree(repo, files)
    commit = git(repo, "commit-tree", tree, "-m", "checkpoint")
    git(repo, "update-ref", ref, commit)


def compact(agent, turns, v=1):
    lines = []
    for i, (role, content) in enumerate(turns):
        lines.append(json.dumps({"v": v, "agent": agent, "cli_version": "0.0.0", "type": role,
                                 "ts": f"2026-11-0{3 + i // 50}T10:{i % 60:02d}:00.000Z", "content": content}))
    return ("\n".join(lines) + "\n").encode()


def text(s):
    return [{"text": s}]


def session_files(session_id, agent, turns, prefix="", v=1):
    return {f"{prefix}0/transcript.jsonl": compact(agent, turns, v),
            f"{prefix}0/metadata.json": json.dumps({"session_id": session_id, "agent": agent}).encode(),
            f"{prefix}0/full.jsonl": b"{}\n", f"{prefix}metadata.json": b"{}"}


TURNS = [("user", text("Why did we choose per-line requests?")),
         ("assistant", [{"type": "tool_use", "name": "Bash", "input": {"cmd": "SECRET-TOOL-OUTPUT"}}]),
         ("assistant", text("Batching dropped detection from 0.87 to 0.37.")),
         ("user", text("<system-reminder>injected</system-reminder>")),
         ("user", text("export TOKEN=abcd1234efgh5678ijkl")),
         ("assistant", [{"type": "text", "text": "Noted."}, {"type": "tool_use", "name": "x"}])]


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def run(repo, *args):
    return adapter.main(["--project", str(repo), "--out", str(repo / "memory/sessions"), *args])


def test_refs_backend_writes_prose_only_redacted_and_names_codex_by_last_eight(repo, capsys):
    commit_ref(repo, "refs/entire/checkpoints/7X/01AAAA", session_files(CODEX_ID, "codex", TURNS))
    assert run(repo) == 0
    files = sorted(p.name for p in (repo / "memory/sessions").glob("*.md"))
    assert files == ["2026-11-03-b09edd59.md"]
    body = (repo / "memory/sessions" / files[0]).read_text()
    assert "Batching dropped detection from 0.87 to 0.37." in body and "Noted." in body
    assert "SECRET-TOOL-OUTPUT" not in body and "injected" not in body and "abcd1234efgh5678ijkl" not in body
    assert "from Entire checkpoint 01AAAA" in body and "(codex" in body
    assert "1 new" in capsys.readouterr().err


def test_claude_session_is_named_by_first_eight_and_date_prefix_is_ignored(repo):
    commit_ref(repo, "refs/entire/checkpoints/7X/01AAAA", session_files("2026-11-03-" + CLAUDE_ID, "claude-code", TURNS))
    assert run(repo) == 0
    assert [p.name for p in (repo / "memory/sessions").glob("*.md")] == ["2026-11-03-5f0c2a1e.md"]


def test_several_checkpoints_of_one_session_use_the_most_complete_transcript(repo):
    commit_ref(repo, "refs/entire/checkpoints/7X/01AAAA", session_files(CODEX_ID, "codex", TURNS[:3]))
    commit_ref(repo, "refs/entire/checkpoints/MB/01BBBB", session_files(CODEX_ID, "codex", TURNS + [("user", text("Later question"))]))
    assert run(repo) == 0
    files = list((repo / "memory/sessions").glob("*.md"))
    assert len(files) == 1 and "Later question" in files[0].read_text()


def test_branch_backend_is_read_from_the_local_branch(repo):
    prefix = "ab/cdef0123456789/"
    commit_ref(repo, "refs/heads/entire/checkpoints/v1", session_files(CLAUDE_ID, "claude-code", TURNS, prefix=prefix))
    assert run(repo) == 0
    body = next((repo / "memory/sessions").glob("*.md")).read_text()
    assert "from Entire checkpoint abcdef0123456789" in body


def test_existing_session_file_is_kept_unless_update_is_given(repo):
    commit_ref(repo, "refs/entire/checkpoints/7X/01AAAA", session_files(CODEX_ID, "codex", TURNS))
    out = repo / "memory/sessions"
    out.mkdir(parents=True)
    # export_sessions.py already wrote this session, possibly under a slightly different date.
    (out / "2026-11-02-b09edd59.md").write_text("from the agent's own transcript")
    assert run(repo) == 0
    assert [p.name for p in out.glob("*.md")] == ["2026-11-02-b09edd59.md"]
    assert (out / "2026-11-02-b09edd59.md").read_text() == "from the agent's own transcript"
    assert run(repo, "--update") == 0
    assert "Batching dropped" in (out / "2026-11-02-b09edd59.md").read_text()


def test_fresh_archive_is_git_ignored_but_a_shared_archive_is_left_alone(repo):
    commit_ref(repo, "refs/entire/checkpoints/7X/01AAAA", session_files(CODEX_ID, "codex", TURNS))
    assert run(repo) == 0
    assert (repo / "memory/sessions/.gitignore").read_text().startswith("*")
    shared = repo / "other/sessions"
    shared.mkdir(parents=True)
    (shared / "2026-10-01-aaaaaaaa.md").write_text("an earlier shared session")
    assert adapter.main(["--project", str(repo), "--out", str(shared)]) == 0
    assert not (shared / ".gitignore").exists()


def test_unknown_transcript_format_is_skipped_with_a_warning(repo, capsys):
    commit_ref(repo, "refs/entire/checkpoints/7X/01AAAA", session_files(CODEX_ID, "codex", TURNS, v=2))
    assert run(repo) == 0
    assert not list((repo / "memory/sessions").glob("*.md"))
    err = capsys.readouterr().err
    assert "unsupported transcript format" in err and "1 skipped" in err


def test_no_checkpoints_and_not_a_repository_are_reported(repo, tmp_path_factory, capsys):
    assert run(repo) == 1 and "no Entire checkpoints" in capsys.readouterr().err
    assert adapter.main(["--project", str(tmp_path_factory.mktemp("plain")), "--out", "x"]) == 1
    assert "not a git repository" in capsys.readouterr().err


def test_dry_run_and_since_write_nothing_or_filter(repo):
    commit_ref(repo, "refs/entire/checkpoints/7X/01AAAA", session_files(CODEX_ID, "codex", TURNS))
    assert run(repo, "--dry-run") == 0
    assert not (repo / "memory").exists()
    assert run(repo, "--since", "2026-12-01") == 0
    assert not (repo / "memory").exists()


def test_the_script_only_reads_git_data(repo):
    commit_ref(repo, "refs/entire/checkpoints/7X/01AAAA", session_files(CODEX_ID, "codex", TURNS))
    before = git(repo, "for-each-ref")
    assert run(repo) == 0
    assert git(repo, "for-each-ref") == before
