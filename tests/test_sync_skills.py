"""scripts/sync_skills.py against synthetic upstream repositories and a synthetic copy of the vendored tree."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts/sync_skills.py"
spec = importlib.util.spec_from_file_location("sync_skills", SCRIPT)
sync = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sync  # dataclasses look the module up by name while it is executed
spec.loader.exec_module(sync)

SCRIPT_V1 = "import sys\n\nHOME = 1\n\n\ndef main():\n    args = parse()\n    if not args:\n        return 1\n    return 0\n"
SKILL_V1 = "---\nname: memory-1\n---\n\n# memory-1\n\nFirst paragraph.\n\nExport with the script.\n"
OVERLAYS = """
[[insert]]
skill = "memory-1"
file = "scripts/run.py"
name = "extra-code"
before = "def main():"
body = "extra-code.py"
blank_after = 2
description = "a helper"

[[insert]]
skill = "memory-1"
file = "scripts/run.py"
name = "extra-call"
before = "    return 0"
body = "extra-call.py"
description = "calls the helper"

[[insert]]
skill = "memory-1"
file = "SKILL.md"
name = "note"
before = "Export with the script."
body = "note.md"
style = "md"
blank_after = 1
description = "a paragraph"
"""


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=x", *args],
                          capture_output=True, text=True, check=True)
    return done.stdout.strip()


def make_upstream(root, skill, files, message="v1"):
    repo = root / f"{skill}-upstream"
    if not repo.exists():
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
    write_files(repo, skill, files)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return repo, git(repo, "rev-parse", "HEAD")


def write_files(repo, skill, files):
    base = repo / "skills" / skill
    if base.exists():  # a new commit replaces the whole skill folder
        for p in sorted(base.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
    for path, text in files.items():
        (base / path).parent.mkdir(parents=True, exist_ok=True)
        (base / path).write_text(text)


@pytest.fixture
def world(tmp_path):
    overlays = tmp_path / "overlays"
    overlays.mkdir()
    (overlays / "overlays.toml").write_text(OVERLAYS)
    (overlays / "extra-code.py").write_text("def helper():\n    return 'entire'\n")
    (overlays / "extra-call.py").write_text("    helper()\n")
    (overlays / "note.md").write_text("Also --entire, on request.\n")
    skills = tmp_path / "skills"
    pins = tmp_path / "pins.py"
    pins.write_text('MEMORY_SKILL_REF = "old"  # note\nDOCS_SKILL_REF = "old"\nOTHER = "keep"\n')
    memory, mem_commit = make_upstream(tmp_path, "memory-1", {"SKILL.md": SKILL_V1, "scripts/run.py": SCRIPT_V1, "templates/x.md": "x\n"})
    docs, docs_commit = make_upstream(tmp_path, "docs-1", {"SKILL.md": "---\nname: docs-1\n---\n\n# docs\n"})
    return {"root": tmp_path, "overlays": overlays, "skills": skills, "pins": pins, "memory": memory, "docs": docs,
            "mem_commit": mem_commit, "docs_commit": docs_commit}


def run(w, check=False, memory_ref=None, **kw):
    specs = {"memory-1": (w["memory"], memory_ref or w["mem_commit"]), "docs-1": (w["docs"], w["docs_commit"])}
    return sync.sync(specs, skills_dir=w["skills"], pins_file=w["pins"], overlays_dir=w["overlays"], check=check, log=lambda _m: None, **kw)


def test_sync_copies_both_skills_applies_the_blocks_and_records_the_pins(world):
    changed = run(world)
    assert changed
    script = (world["skills"] / "memory-1/scripts/run.py").read_text()
    assert "# agentic-loadout:begin extra-code\ndef helper():" in script
    assert "    # agentic-loadout:begin extra-call\n    helper()\n    # agentic-loadout:end extra-call\n    return 0\n" in script
    assert sync.strip_blocks(script) == SCRIPT_V1
    note = (world["skills"] / "memory-1/SKILL.md").read_text()
    assert "<!-- agentic-loadout:begin note -->\nAlso --entire, on request.\n<!-- agentic-loadout:end note -->\n\nExport with the script." in note
    assert sync.strip_blocks(note) == SKILL_V1
    assert (world["skills"] / "memory-1/templates/x.md").read_text() == "x\n" and (world["skills"] / "docs-1/SKILL.md").is_file()
    pins = world["pins"].read_text()
    assert f'MEMORY_SKILL_REF = "{world["mem_commit"]}"\n' in pins and f'DOCS_SKILL_REF = "{world["docs_commit"]}"\n' in pins
    assert 'OTHER = "keep"' in pins and "# note" not in pins
    doc = (world["skills"] / "UPSTREAM.md").read_text()
    assert world["mem_commit"] in doc and sync.sha256(SCRIPT_V1.encode()) in doc and "`memory-1/scripts/run.py`" in doc
    assert "a helper" in doc and "| `memory-1/templates/x.md` | `" in doc


def test_second_sync_changes_nothing_and_check_agrees(world):
    run(world)
    before = {p: p.read_bytes() for p in world["root"].rglob("*") if p.is_file() and ".git" not in p.parts}
    assert run(world) == [] and run(world, check=True) == []
    assert {p: p.read_bytes() for p in world["root"].rglob("*") if p.is_file() and ".git" not in p.parts} == before


def test_check_and_dry_run_report_but_write_nothing(world):
    assert run(world, check=True) and run(world, dry_run=True)
    assert not world["skills"].exists() and "old" in world["pins"].read_text()


def test_newer_upstream_commit_is_picked_up_and_files_deleted_upstream_disappear(world):
    run(world)
    changed = SCRIPT_V1.replace("HOME = 1", "HOME = 2")
    _repo, commit = make_upstream(world["root"], "memory-1", {"SKILL.md": SKILL_V1, "scripts/run.py": changed}, "v2")
    assert run(world, memory_ref=commit)
    script = (world["skills"] / "memory-1/scripts/run.py").read_text()
    assert "HOME = 2" in script and "agentic-loadout:begin extra-code" in script and sync.strip_blocks(script) == changed
    assert not (world["skills"] / "memory-1/templates").exists()
    assert f'MEMORY_SKILL_REF = "{commit}"' in world["pins"].read_text()


def test_uncommitted_edits_in_the_checkout_are_not_copied(world):
    (world["memory"] / "skills/memory-1/SKILL.md").write_text("edited, not committed\n")
    run(world)
    assert "edited" not in (world["skills"] / "memory-1/SKILL.md").read_text()


def test_a_missing_anchor_fails_loudly_and_writes_nothing(world):
    _repo, commit = make_upstream(world["root"], "memory-1", {"SKILL.md": SKILL_V1, "scripts/run.py": SCRIPT_V1.replace("def main():", "def run():")}, "renamed")
    with pytest.raises(SystemExit) as exc:
        run(world, memory_ref=commit)
    assert "extra-code" in str(exc.value) and "def main():" in str(exc.value) and "0 times" in str(exc.value)
    assert not world["skills"].exists() and "old" in world["pins"].read_text()


def test_an_ambiguous_anchor_fails_loudly(world):
    doubled = SCRIPT_V1 + "\n\ndef other():\n    return 0\n"
    _repo, commit = make_upstream(world["root"], "memory-1", {"SKILL.md": SKILL_V1, "scripts/run.py": doubled}, "doubled")
    with pytest.raises(SystemExit) as exc:
        run(world, memory_ref=commit)
    assert "2 times" in str(exc.value)


def test_an_overlay_for_a_file_that_is_gone_upstream_fails(world):
    _repo, commit = make_upstream(world["root"], "memory-1", {"SKILL.md": SKILL_V1}, "no script")
    with pytest.raises(SystemExit) as exc:
        run(world, memory_ref=commit)
    assert "does not exist upstream" in str(exc.value)


def test_an_unknown_commit_or_a_missing_pins_line_fails(world):
    with pytest.raises(SystemExit):
        run(world, memory_ref="deadbeef")
    world["pins"].write_text('MEMORY_SKILL_REF = "x"\n')
    with pytest.raises(SystemExit) as exc:
        run(world)
    assert "DOCS_SKILL_REF" in str(exc.value)


def test_strip_blocks_rejects_broken_markers_and_keeps_upstream_blanks():
    with pytest.raises(SystemExit):
        sync.strip_blocks("# agentic-loadout:begin a\nx\n")
    with pytest.raises(SystemExit):
        sync.strip_blocks("# agentic-loadout:begin a\n# agentic-loadout:end b\n")
    with pytest.raises(SystemExit):
        sync.strip_blocks("# agentic-loadout:end a\n")
    text = "a\n\n\n# agentic-loadout:begin n\nnew\n# agentic-loadout:end n\n\n\nb\n\n\nc\n"
    assert sync.strip_blocks(text) == "a\n\n\nb\n\n\nc\n"
    assert sync.strip_blocks("a\n\nb\n") == "a\n\nb\n"
