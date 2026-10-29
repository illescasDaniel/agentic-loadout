from agent_loadout.files import Ctx
from agent_loadout.instructions import Section, apply_sections, choose_targets

SEC = Section("agents", "## Agents and delegation\n\nText.")


def run(repo, tools, personal, sections=(SEC,), **kw):
    ctx = Ctx(repo)
    apply_sections(ctx, tools, personal, list(sections), **kw)
    ctx.apply()
    return ctx


def test_given_nothing_when_shared_then_agents_md_created(tmp_path):
    run(tmp_path, ["cursor"], False)
    assert "agent-loadout:begin agents" in (tmp_path / "AGENTS.md").read_text()


def test_given_claude_md_when_shared_then_claude_md_gets_sections_and_agents_md_untouched(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# rules\n")
    (tmp_path / "AGENTS.md").write_text("# other\n")
    run(tmp_path, ["claude"], False)
    assert "Agents and delegation" in (tmp_path / "CLAUDE.md").read_text()
    assert (tmp_path / "AGENTS.md").read_text() == "# other\n"


def test_given_claude_md_and_cursor_when_shared_then_both_files_get_sections(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# rules\n")
    run(tmp_path, ["claude", "cursor"], False)
    assert "Agents and delegation" in (tmp_path / "AGENTS.md").read_text()


def test_given_claude_md_is_only_an_import_when_shared_then_agents_md_is_the_target(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("@AGENTS.md\n")
    assert choose_targets(Ctx(tmp_path), ["claude"], False) == [tmp_path / "AGENTS.md"]


def test_given_agents_md_target_when_claude_without_import_then_warns_and_compat_writes_import(tmp_path):
    ctx = run(tmp_path, ["claude"], False)
    assert any("@AGENTS.md" in w for w in ctx.warnings)
    run(tmp_path, ["claude"], False, claude_compat=True)
    assert (tmp_path / "CLAUDE.md").read_text().startswith("@AGENTS.md")


def test_given_personal_claude_only_with_agents_md_then_local_file_imports_agents_md(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# mine\n")
    run(tmp_path, ["claude"], True)
    assert (tmp_path / "CLAUDE.local.md").read_text().startswith("@AGENTS.md\n")
    assert (tmp_path / "AGENTS.md").read_text() == "# mine\n"


def test_given_personal_with_claude_md_then_local_file_has_no_import(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# rules\n")
    run(tmp_path, ["claude"], True)
    assert not (tmp_path / "CLAUDE.local.md").read_text().startswith("@AGENTS.md")


def test_given_personal_with_cursor_then_agents_md_is_used_and_user_is_warned(tmp_path):
    ctx = run(tmp_path, ["claude", "cursor"], True)
    assert (tmp_path / "AGENTS.md").exists() and not (tmp_path / "CLAUDE.local.md").exists()
    assert any("tracked" in w for w in ctx.warnings)


def test_given_a_rerun_then_sections_are_replaced_not_duplicated(tmp_path):
    run(tmp_path, ["cursor"], False)
    run(tmp_path, ["cursor"], False, sections=[Section("agents", "## Agents and delegation\n\nNew text.")])
    text = (tmp_path / "AGENTS.md").read_text()
    assert text.count("agent-loadout:begin agents") == 1 and "New text." in text and "\nText." not in text


def test_given_user_has_same_heading_without_markers_then_it_is_skipped_with_a_warning(tmp_path):
    (tmp_path / "AGENTS.md").write_text("## Agents and delegation\n\nMine.\n")
    ctx = run(tmp_path, ["cursor"], False)
    assert (tmp_path / "AGENTS.md").read_text() == "## Agents and delegation\n\nMine.\n"
    assert any("your rules win" in w for w in ctx.warnings)


def test_given_crlf_file_then_line_endings_are_kept(tmp_path):
    (tmp_path / "AGENTS.md").write_bytes(b"# mine\r\n")
    run(tmp_path, ["cursor"], False)
    assert b"\r\n" in (tmp_path / "AGENTS.md").read_bytes() and b"\n\n" not in (tmp_path / "AGENTS.md").read_bytes().replace(b"\r\n", b"")
