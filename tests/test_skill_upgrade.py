"""Projects set up by an earlier state of this package: skills installed with `npx skills` (and listed in
skills-lock.json) and the old Entire adapter script are replaced, never duplicated."""

import json

from agentic_loadout import skills
from tests.conftest import FakeExecutor
from tests.test_install import full

LEAN = frozenset({"sdd", "worktree", "agents", "coders"})
BOTH = ("claude", "codex")


def lock(*names):
    return {"version": 1, "skills": {n: {"source": f"x/{n}", "ref": "abc", "sourceType": "github", "computedHash": "0"} for n in names}}


def npx_state(repo, folders=(".claude/skills", ".agents/skills"), names=("memory-1", "docs-1"), entries=None):
    for folder in folders:
        for name in names:
            (repo / folder / name / "scripts").mkdir(parents=True)
            (repo / folder / name / "SKILL.md").write_text("copy from npx skills")
            (repo / folder / name / "scripts/old_only.py").write_text("gone upstream")
    (repo / "skills-lock.json").write_text(json.dumps(lock(*(entries or names)), indent=2) + "\n")


def snapshot(repo):
    return {p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.relative_to(repo).parts}


def test_npx_copies_are_replaced_stale_files_go_and_their_lock_entries_are_removed(repo):
    npx_state(repo, entries=("memory-1", "docs-1", "sdd-feature", "worktree"))
    executor = FakeExecutor()
    code, out = full(repo, tools=("claude", "codex"), executor=executor, without=LEAN)
    assert code == 0, out
    for name in ("memory-1", "docs-1"):
        for folder in (".claude/skills", ".agents/skills"):
            assert {p.relative_to(repo / folder / name).as_posix(): p.read_bytes() for p in (repo / folder / name).rglob("*") if p.is_file() and p.name != skills.MANIFEST} \
                == skills.vendored_files(name)
    assert list(json.loads((repo / "skills-lock.json").read_text())["skills"]) == ["sdd-feature", "worktree"]
    assert executor.calls == [] and "the copy `npx skills` had installed" in out


def test_a_lock_that_only_listed_the_replaced_skills_is_deleted(repo):
    npx_state(repo)
    code, out = full(repo, tools=BOTH, without=LEAN)
    assert code == 0, out
    assert not (repo / "skills-lock.json").exists() and "skills-lock.json" in out


def test_the_upgrade_is_idempotent_and_a_dry_run_changes_nothing(repo):
    npx_state(repo)
    before = snapshot(repo)
    code, out = full(repo, tools=BOTH, without=LEAN, dry_run=True)
    assert code == 0 and snapshot(repo) == before and "would replace" in out and "would remove" in out
    full(repo, tools=BOTH, without=LEAN)
    after = snapshot(repo)
    code, out = full(repo, tools=BOTH, without=LEAN)
    assert code == 0 and snapshot(repo) == after and "installed" not in out and "replaced" not in out


def test_an_npx_copy_in_a_client_that_is_not_selected_is_left_and_its_lock_entry_kept(repo):
    npx_state(repo)
    code, out = full(repo, tools=("claude",), without=LEAN)
    assert code == 0, out
    assert (repo / ".agents/skills/memory-1/SKILL.md").read_text() == "copy from npx skills"
    assert (repo / ".claude/skills/memory-1/SKILL.md").read_bytes() == skills.vendored_files("memory-1")["SKILL.md"]
    assert sorted(json.loads((repo / "skills-lock.json").read_text())["skills"]) == ["docs-1", "memory-1"]
    assert "not selected" in out
    code, out = full(repo, tools=("claude", "codex"), without=LEAN)
    assert code == 0 and not (repo / "skills-lock.json").exists()
    assert (repo / ".agents/skills/memory-1/SKILL.md").read_bytes() == skills.vendored_files("memory-1")["SKILL.md"]


def test_a_skill_copy_the_user_edited_is_kept_unless_force_is_given(repo):
    full(repo, without=LEAN)
    edited = repo / ".claude/skills/memory-1/SKILL.md"
    edited.write_text("my edits")
    code, out = full(repo, without=LEAN)
    assert code == 0 and edited.read_text() == "my edits" and "use --force" in out
    code, out = full(repo, without=LEAN, force=True)
    assert code == 0 and edited.read_bytes() == skills.vendored_files("memory-1")["SKILL.md"]


def test_the_old_entire_adapter_script_is_removed_on_rerun(repo):
    script = repo / ".agents/scripts/entire_sessions.py"
    script.parent.mkdir(parents=True)
    script.write_text('#!/usr/bin/env python3\n"""Fill memory/sessions/ from the Entire checkpoints stored in this repository\'s git data.\n"""\n')
    code, out = full(repo, without=LEAN)
    assert code == 0, out
    assert not script.exists() and not script.parent.exists() and "entire_sessions.py" in out


def test_a_file_at_the_old_script_path_that_is_not_ours_is_left_alone(repo):
    script = repo / ".agents/scripts/entire_sessions.py"
    script.parent.mkdir(parents=True)
    script.write_text("# my own script\n")
    code, out = full(repo, without=LEAN)
    assert code == 0 and script.read_text() == "# my own script\n" and "left alone" in out


def test_without_memory_and_docs_an_npx_state_is_not_touched(repo):
    npx_state(repo)
    before = snapshot(repo)
    code, _out = full(repo, without=LEAN | {"memory", "docs"})
    assert code == 0 and snapshot(repo) == before


def test_a_newer_release_updates_untouched_copies_and_keeps_edited_files(repo, monkeypatch):
    code, out = full(repo, tools=("claude",), executor=FakeExecutor(), without=LEAN)
    assert code == 0, out
    dest = repo / ".claude/skills/memory-1"
    (dest / "scripts/memory_check.py").write_text("my own edit")
    real = skills.vendored_files

    def newer(name):
        files = dict(real(name))
        if name == "memory-1":
            files["SKILL.md"] = files["SKILL.md"] + b"\nnew release line\n"
            files["scripts/memory_check.py"] = files["scripts/memory_check.py"] + b"# newer\n"
            del files["templates/LATER.md"]
        return files

    monkeypatch.setattr(skills, "vendored_files", newer)
    code, out = full(repo, tools=("claude",), executor=FakeExecutor(), without=LEAN)
    assert code == 0, out
    assert (dest / "SKILL.md").read_bytes().endswith(b"new release line\n")
    assert (dest / "scripts/memory_check.py").read_text() == "my own edit" and "use --force" in out
    assert not (dest / "templates/LATER.md").exists()
    before = snapshot(repo)
    code, out = full(repo, tools=("claude",), executor=FakeExecutor(), without=LEAN)
    assert code == 0 and snapshot(repo) == before


def test_kept_agent_files_that_still_name_agemem_tools_are_listed_for_review(repo):
    code, out = full(repo, tools=("claude",), executor=FakeExecutor(), without=frozenset({"sdd", "worktree", "coders"}))
    assert code == 0, out
    edited = repo / ".claude/agents/architect.md"
    edited.write_text(edited.read_text() + "\nUse mcp__agemem__project_memory_recall first.\n")
    code, out = full(repo, tools=("claude",), executor=FakeExecutor(), without=frozenset({"sdd", "worktree", "coders"}))
    assert code == 0 and "still tell agents to use agemem tools" in out and ".claude/agents/architect.md" in out
