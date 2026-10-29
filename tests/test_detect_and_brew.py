from agentic_loadout.brew import plan_swift, run_plan, swift_binary_path
from agentic_loadout.detect import detect_languages
from tests.conftest import make_system, prompter


def test_given_marker_files_then_languages_are_detected(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "web").mkdir()
    (tmp_path / "web/package.json").write_text("{}")
    (tmp_path / "App.xcodeproj").mkdir()
    assert detect_languages(tmp_path) == ["python", "typescript", "swift"]


def test_given_vendored_dirs_then_they_are_ignored(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules/package.json").write_text("{}")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv/pyproject.toml").write_text("")
    assert detect_languages(tmp_path) == []


def test_given_linux_then_brew_is_not_offered(tmp_path):
    system, calls = make_system("Linux", binaries=("brew",))
    p = prompter()
    plan = plan_swift(tmp_path, p, system, allow_brew=True)
    assert plan.state == "not-macos" and not plan.install_binary and not p.asked and not calls


def test_given_binary_on_path_then_brew_is_skipped(tmp_path):
    system, _ = make_system("Darwin", binaries=("brew", "codenav-swift-mcp"))
    p = prompter()
    plan = plan_swift(tmp_path, p, system)
    assert plan.state == "present" and not p.asked


def test_given_no_brew_then_instructions_are_printed(tmp_path):
    system, _ = make_system("Darwin")
    plan = plan_swift(tmp_path, prompter(), system)
    assert plan.state == "no-brew" and "brew.sh" in plan.messages[0]


def test_given_yes_flag_then_brew_still_asks(tmp_path):
    system, _ = make_system("Darwin", binaries=("brew",))
    p = prompter("y", yes=True)
    plan = plan_swift(tmp_path, p, system)
    assert len(p.asked) == 1 and plan.install_binary


def test_given_no_input_then_brew_is_declined_without_asking(tmp_path):
    system, _ = make_system("Darwin", binaries=("brew",))
    plan = plan_swift(tmp_path, prompter(yes=True, no_input=True), system)
    assert plan.state == "declined" and not plan.install_binary


def test_given_declined_answer_then_nothing_is_installed(tmp_path):
    system, calls = make_system("Darwin", binaries=("brew",))
    plan = plan_swift(tmp_path, prompter("n"), system)
    assert plan.state == "declined" and run_plan(plan, system) == [] and not calls


def test_given_allow_brew_then_it_installs_without_asking(tmp_path):
    system, calls = make_system("Darwin", binaries=("brew",))
    p = prompter()
    plan = plan_swift(tmp_path, p, system, allow_brew=True)
    assert plan.install_binary and not p.asked
    assert run_plan(plan, system, lambda _l: None) == []
    assert calls == [["brew", "install", "illescasDaniel/tap/codenav-swift-mcp"]]


def test_given_failed_brew_then_error_is_returned(tmp_path):
    system, _ = make_system("Darwin", binaries=("brew",), brew_ok=False)
    plan = plan_swift(tmp_path, prompter(), system, allow_brew=True)
    assert "failed" in run_plan(plan, system, lambda _l: None)[0]


def test_given_xcode_project_without_build_server_then_offer_and_print_command(tmp_path):
    (tmp_path / "App.xcodeproj").mkdir()
    system, calls = make_system("Darwin", binaries=("brew", "codenav-swift-mcp"))
    plan = plan_swift(tmp_path, prompter("y"), system)
    assert plan.install_xcode_build_server
    assert any("xcode-build-server config" in m for m in plan.messages)
    run_plan(plan, system, lambda _l: None)
    assert calls == [["brew", "install", "xcode-build-server"]]  # the `config` command is never run


def test_given_cursor_then_swift_path_is_absolute(tmp_path):
    system, _ = make_system("Darwin", binaries=("brew",), brew_prefix="/usr/local")
    assert swift_binary_path(system) == "/usr/local/bin/codenav-swift-mcp"
