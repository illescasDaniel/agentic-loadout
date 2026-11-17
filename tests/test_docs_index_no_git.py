"""docs_index.py must keep working when git is not installed (staleness is then simply unknown)."""
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "src/agentic_loadout/assets/skills/docs-1/scripts/docs_index.py"

DOC = """---
id: {id}
title: {title}
summary: {title} summary
type: reference
status: current
updated: 2026-10-01
verified: 2026-10-01
covers: [src/app.py]
related: []
supersedes:
superseded_by:
---
# {title}
{body}
"""


def run(project, *args):
    # An empty PATH hides git; the interpreter is called by its absolute path.
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=project, env={"PATH": str(project / "no-bin")},
                          capture_output=True, text=True, timeout=60)


def test_every_command_works_without_git(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.py").write_text("x = 1\n")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text(DOC.format(id="DOC-001", title="App", body="See [b](b.md)."))
    (docs / "b.md").write_text(DOC.format(id="DOC-001", title="Other", body="See [gone](gone.md)."))

    check = run(tmp_path, "check")
    assert check.returncode == 1, check.stderr
    assert "Traceback" not in check.stderr
    assert "duplicate id DOC-001" in check.stdout
    assert "broken link gone.md" in check.stdout

    write = run(tmp_path, "write")
    assert write.returncode == 0, write.stderr
    assert "DOC-001" in (docs / "INDEX.md").read_text()

    assert run(tmp_path, "next-id").stdout.strip() == "DOC-002"
    assert "docs/a.md" in run(tmp_path, "covers", "src/app.py").stdout

    verify = run(tmp_path, "verify", "DOC-001")
    assert verify.returncode == 0, verify.stderr
    assert "Traceback" not in verify.stderr
