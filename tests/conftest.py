import json
import shutil
import subprocess
from pathlib import Path

import pytest

from agentic_loadout import pins
from agentic_loadout.brew import System
from agentic_loadout.options import Options
from agentic_loadout.ui import Prompter


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "AGENTS.md").write_bytes(b"# mine\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=a@b", "-c", "user.name=x", "commit", "-qm", "init"], check=True)
    return tmp_path


def make_system(system="Linux", binaries=(), brew_prefix="/opt/homebrew", brew_ok=True, entire_version="0.13.2"):
    calls = []

    def run(cmd):
        calls.append(list(cmd))
        if list(cmd) == ["brew", "--prefix"]:
            return subprocess.CompletedProcess(cmd, 0, brew_prefix + "\n", "")
        if list(cmd) == ["entire", "--version"]:
            return subprocess.CompletedProcess(cmd, 0, f"Entire CLI {entire_version}\nGo version: go1.27.3\nOS/Arch: linux/amd64\n", "")
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
    """Stands in for npx: records the command and writes the files the real skills CLI would (Phase 0, docs/original-implementation-plan.md §8a)."""

    def __init__(self):
        self.calls = []

    def __call__(self, cmd, cwd, env):
        self.calls.append((list(cmd), env))
        if "remove" in cmd:
            for folder in (".claude/skills", ".agents/skills"):
                shutil.rmtree(cwd / folder / cmd[cmd.index("remove") + 1], ignore_errors=True)
        elif "add" in cmd:
            name = cmd[cmd.index("-s") + 1] if "-s" in cmd else pins.SDD_SKILL_NAME
            for folder in (".claude/skills", ".agents/skills"):
                skill = cwd / folder / name
                skill.mkdir(parents=True, exist_ok=True)
                (skill / "SKILL.md").write_text("x")
            if name == pins.SDD_SKILL_NAME:
                (cwd / ".claude/skills" / name / "agents").mkdir(exist_ok=True)
                (cwd / ".claude/skills" / name / "agents/code-grader.md").write_bytes(
                    "---\nname: code-grader\ndescription: d\n---\n\n# Grader body\n".encode())
            (cwd / "skills-lock.json").write_text("{}")
        return subprocess.CompletedProcess(cmd, 0, "", "")


@pytest.fixture
def opts(repo):
    return Options(project=repo, tools=["claude"], no_input=True, yes=True)
