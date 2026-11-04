import json
import shutil
import subprocess

import pytest

from agentic_loadout.install import run_install
from agentic_loadout.options import Options
from agentic_loadout import entire
from agentic_loadout.files import Ctx
from agentic_loadout.ui import Prompter
from tests.conftest import make_system


pytestmark = pytest.mark.skipif(shutil.which("entire") is None, reason="Entire CLI is not installed")


def install_entire(repo, **kwargs):
    opts = Options(project=repo, tools=["codex", "cursor"], no_input=True, yes=True,
                   without=frozenset({"agemem", "agents", "coders", "sdd", "worktree"}), **kwargs)
    output = []
    result = run_install(opts, Prompter(yes=True, no_input=True), make_system(binaries=("entire",))[0], out=output.append)
    return result, "\n".join(output)


def test_entire_disables_existing_local_override_and_installs_both_agents(repo):
    folder = repo / ".entire"
    folder.mkdir()
    (folder / "settings.local.json").write_text('{"strategy_options":{"push_sessions":true}}')
    code, out = install_entire(repo)
    assert code == 0, out
    assert json.loads((folder / "settings.local.json").read_text())["strategy_options"]["push_sessions"] is False
    assert (repo / ".codex/hooks.json").exists() and (repo / ".cursor/hooks.json").exists()
    assert "Entire session history" in (repo / "AGENTS.md").read_text()


def test_entire_explicit_upload_opt_in_and_revert_to_safe_default(repo):
    code, out = install_entire(repo, entire_upload_sessions=True)
    assert code == 0, out
    assert json.loads((repo / ".entire/settings.json").read_text())["strategy_options"]["push_sessions"] is True
    assert "transcripts may be visible" in out
    code, out = install_entire(repo)
    assert code == 0, out
    assert json.loads((repo / ".entire/settings.json").read_text())["strategy_options"]["push_sessions"] is False


def test_entire_dry_run_and_no_hooks_do_not_install(repo):
    code, out = install_entire(repo, dry_run=True)
    assert code == 0 and "would run  entire enable" in out
    assert not (repo / ".entire").exists()
    code, out = install_entire(repo, no_hooks=True)
    assert code == 0 and "--no-hooks" in out
    assert not (repo / ".entire").exists()


def test_local_opt_in_is_reset_to_safe_default(repo):
    folder = repo / ".entire"
    folder.mkdir()
    (folder / "settings.local.json").write_text('{"strategy_options":{"push_sessions":true}}')
    code, out = install_entire(repo, entire_upload_sessions=True)
    assert code == 0, out
    assert json.loads((folder / "settings.local.json").read_text())["strategy_options"]["push_sessions"] is True
    code, out = install_entire(repo)
    assert code == 0, out
    assert json.loads((folder / "settings.local.json").read_text())["strategy_options"]["push_sessions"] is False


def test_shared_configuration_keeps_uploads_disabled_in_new_worktree(repo, tmp_path):
    code, out = install_entire(repo)
    assert code == 0, out
    subprocess.run(["git", "-C", str(repo), "add", ".entire", ".codex/hooks.json", ".cursor/hooks.json"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "Add Entire config"], check=True)
    worktree = tmp_path.parent / (tmp_path.name + "-worktree")
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-qb", "pilot", str(worktree)], check=True)
    result = subprocess.run(["entire", "status", "--json"], cwd=worktree, check=True, capture_output=True, text=True)
    status = json.loads(result.stdout)
    assert status["enabled"] and status["checkpoint_push_disabled"] is True


def test_entire_fails_closed_when_upload_status_is_unknown(repo):
    opts = Options(project=repo)
    with pytest.raises(SystemExit, match="did not confirm"):
        entire.verify(Ctx(repo), opts, lambda cmd, cwd, env: subprocess.CompletedProcess(cmd, 0, '{"enabled":true}', ""))


def test_explicit_upload_request_requires_installed_cli(repo):
    opts = Options(project=repo, entire_upload_sessions=True)
    with pytest.raises(SystemExit, match="requires the Entire CLI"):
        entire.install(Ctx(repo), opts, lambda *_: None, False)
