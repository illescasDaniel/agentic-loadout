"""opencode sessions in the adapted memory-1 export_sessions.py, read from synthetic SQLite databases (never the real one)."""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "src/agentic_loadout/assets/skills/memory-1/scripts/export_sessions.py"
spec = importlib.util.spec_from_file_location("export_sessions_opencode", SCRIPT)
exporter = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = exporter
spec.loader.exec_module(exporter)

MAIN_ID = "ses_aaaa1111bbbb2222"


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    empty = tmp_path / "home"
    monkeypatch.setattr(exporter, "HOME", empty)
    monkeypatch.setattr(exporter, "CLAUDE_ROOT", empty / ".claude/projects")
    monkeypatch.setattr(exporter, "CODEX_ROOT", empty / ".codex/sessions")
    path = tmp_path / "data" / "opencode" / "opencode.db"
    monkeypatch.setattr(exporter, "OPENCODE_DB", path)
    return path


def make_db(path, project):
    path.parent.mkdir(parents=True)
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE session_v2(id, project_id, parent_id, directory, title, time_created, time_updated)")
    db.execute("CREATE TABLE session_message(id, session_id, type, seq, time_created, data)")
    db.execute("INSERT INTO session_v2 VALUES (?, 'p', NULL, ?, 't', 1, 1)", (MAIN_ID, str(project / "sub")))
    db.execute("INSERT INTO session_v2 VALUES ('ses_child', 'p', ?, ?, 't', 1, 1)", (MAIN_ID, str(project)))
    messages = [
        ("user", {"text": "hello"}),
        ("assistant", {"content": [{"type": "reasoning", "text": "private thought"}, {"type": "tool", "name": "x"},
                                   {"type": "text", "text": "hi there"}]}),
        ("compaction", {"summary": "a summary"}),
        ("user", {"text": "bye"}),
    ]
    for sid in (MAIN_ID, "ses_child"):
        for seq, (kind, data) in enumerate(messages):
            db.execute("INSERT INTO session_message VALUES (?, ?, ?, ?, ?, ?)",
                       (f"{sid}-{seq}", sid, kind, seq, 1790000000000 + seq * 1000, json.dumps(data)))
    db.commit()
    db.close()


def test_exports_visible_conversation_and_skips_subagent_sessions(tmp_path, db_path):
    project = tmp_path / "proj"
    project.mkdir()
    make_db(db_path, project)
    found = exporter.find_sessions(project, None)
    assert [c for c, *_ in found] == ["opencode"]  # the subagent session is not listed
    client, path, reader = found[0]
    name, text = exporter.render(client, path, reader, 6000)
    assert name.endswith("-bbbb2222.md")
    assert "hello" in text and "hi there" in text and "bye" in text
    assert "private thought" not in text and "a summary" not in text and "(opencode)" in text
    assert exporter.render(client, path, reader, 6000)[1] == text  # same input, same output: unchanged on a re-run


def test_other_projects_and_a_missing_database_export_nothing(tmp_path, db_path, capsys):
    project = tmp_path / "proj"
    project.mkdir()
    assert exporter.find_sessions(project, None) == []  # no database at all
    make_db(db_path, project)
    assert exporter.find_sessions(tmp_path / "elsewhere", None) == []
    assert exporter.main(["--project", str(tmp_path / "elsewhere"), "--out", str(tmp_path / "out")]) == 1


def test_database_without_the_tables_is_skipped_with_a_note(tmp_path, db_path, capsys):
    db_path.parent.mkdir(parents=True)
    sqlite3.connect(db_path).close()
    assert exporter.find_sessions(tmp_path, None) == []
    assert "opencode" in capsys.readouterr().err
