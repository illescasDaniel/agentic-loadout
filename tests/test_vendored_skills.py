"""The vendored memory-1 and docs-1 copies: stripping the loadout blocks gives the recorded upstream files back byte for
byte, the manifest covers every file, and the pins name the commits the copies were made from."""

import hashlib
import importlib.util
import re
import sys
from pathlib import Path

from agentic_loadout import pins
from agentic_loadout.agents import ASSETS

SYNC = Path(__file__).parent.parent / "scripts/sync_skills.py"
spec = importlib.util.spec_from_file_location("sync_skills", SYNC)
sync_skills = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sync_skills  # dataclasses look the module up by name while it is executed
spec.loader.exec_module(sync_skills)

SKILLS = ASSETS / "skills"
DOC = (SKILLS / "UPSTREAM.md").read_text(encoding="utf-8")
MANIFEST = {m[1]: (m[2], m[3] == "yes") for m in re.finditer(r"^\| `([^`/]+/[^`]+)` \| `([0-9a-f]{64})` \| (yes|no) \|$", DOC, re.MULTILINE)}


def vendored_files():
    return {p.relative_to(SKILLS).as_posix() for p in SKILLS.rglob("*") if p.is_file() and p.name != "UPSTREAM.md" and "__pycache__" not in p.parts}


def test_the_manifest_lists_exactly_the_vendored_files():
    assert set(MANIFEST) == vendored_files()
    assert {"memory-1/SKILL.md", "memory-1/scripts/export_sessions.py", "memory-1/scripts/memory_check.py",
            "memory-1/templates/.gitignore", "docs-1/SKILL.md", "docs-1/scripts/docs_index.py"} <= set(MANIFEST)


def test_stripping_the_marked_blocks_reproduces_the_recorded_upstream_hashes():
    for path, (digest, adapted) in MANIFEST.items():
        data = (SKILLS / path).read_bytes()
        if adapted:
            assert b"agentic-loadout:begin" in data, path
            data = sync_skills.strip_blocks(data.decode("utf-8")).encode("utf-8")
        else:
            assert b"agentic-loadout:" not in data, path
        assert hashlib.sha256(data).hexdigest() == digest, path


def test_only_the_files_the_overlays_name_are_adapted():
    named = {f"{i.skill}/{i.file}" for i in sync_skills.load_overlays(sync_skills.OVERLAYS_DIR)}
    assert {p for p, (_d, adapted) in MANIFEST.items() if adapted} == named


def test_the_pins_are_the_commits_recorded_in_upstream_md():
    assert f"`{pins.MEMORY_SKILL_REF}`" in DOC and f"`{pins.DOCS_SKILL_REF}`" in DOC
    assert len(pins.MEMORY_SKILL_REF) == len(pins.DOCS_SKILL_REF) == 40


def test_the_shipped_overlay_manifest_parses_and_every_anchor_is_a_single_nonblank_line():
    inserts = sync_skills.load_overlays(sync_skills.OVERLAYS_DIR)
    assert inserts and all(i.before.strip() and "\n" not in i.before for i in inserts)
