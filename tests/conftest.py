import json
import subprocess
from pathlib import Path

import pytest

from agentic_loadout.brew import System
from agentic_loadout.options import Options
from agentic_loadout.ui import Prompter


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "AGENTS.md").write_text("# mine\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=a@b", "-c", "user.name=x", "commit", "-qm", "init"], check=True)
    return tmp_path


def make_system(system="Linux", binaries=(), brew_prefix="/opt/homebrew", brew_ok=True):
    calls = []

    def run(cmd):
        calls.append(list(cmd))
        if list(cmd) == ["brew", "--prefix"]:
            return subprocess.CompletedProcess(cmd, 0, brew_prefix + "\n", "")
        return subprocess.CompletedProcess(cmd, 0 if brew_ok else 1, "", "boom")

    return System(system=lambda: system, which=lambda name: f"/usr/bin/{name}" if name in binaries else None, run=run), calls


def prompter(*answers, **kw):
    given = list(answers)
    asked = []

    def fake_input(question):
        asked.append(question)
        return given.pop(0) if given else ""

    p = Prompter(input_fn=fake_input, **kw)
    p.asked = asked
    return p


class FakeExecutor:
    """Stands in for uvx / npx: records the command and writes the files the real tool would (Phase 0, PLAN.md §8a)."""

    def __init__(self):
        self.calls = []

    def __call__(self, cmd, cwd, env):
        self.calls.append((list(cmd), env))
        if "agemem@0.1.1" in cmd:
            (cwd / "memory").mkdir(exist_ok=True)
            (cwd / "memory" / "activeContext.md").write_text("x")
            (cwd / ".agemem").mkdir(exist_ok=True)
            path = cwd / ".mcp.json"
            data = json.loads(path.read_text()) if path.exists() else {}
            data.setdefault("mcpServers", {})["agemem"] = {"command": "uvx"}
            path.write_text(json.dumps(data, indent=2) + "\n")
        elif "add" in cmd:
            skill = cwd / ".claude/skills/sdd-feature"
            (skill / "agents").mkdir(parents=True, exist_ok=True)
            (skill / "SKILL.md").write_text("x")
            (skill / "agents/code-grader.md").write_text("---\nname: code-grader\ndescription: d\n---\n\n# Grader body\n")
            (cwd / "skills-lock.json").write_text("{}")
        return subprocess.CompletedProcess(cmd, 0, "", "")


@pytest.fixture
def opts(repo):
    return Options(project=repo, tools=["claude"], no_input=True, yes=True)
