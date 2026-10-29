# Changelog

## [0.2.0] - 2026-10-29

- Requires agemem 0.2.0, whose MCP and hook entries no longer contain this machine's project path, so `.mcp.json`,
  `.cursor/mcp.json`, `.codex/config.toml` and the Claude hooks can be committed. The "absolute project path" warning is
  gone.
- agemem's Claude Code hooks and `autoMemoryEnabled: false` now go to the shared `.claude/settings.json`;
  `--personal-settings` passes agemem's `--local-settings` so they go to `.claude/settings.local.json` instead.
- Re-running on a project set up with 0.1.0 migrates agemem's entries (agemem replaces them and removes the old
  hooks from `.claude/settings.local.json`).

## [0.1.0] - 2026-10-29

First release.

- One command that installs a coding-agent setup into a project, for Claude Code, Cursor and Codex, writing only
  inside the project.
- Project memory through agemem (0.1.1+), which also turns off Claude Code's built-in auto-memory.
- The `sdd-feature` spec-driven development skill and the `worktree` skill, installed with `npx skills` at pinned
  commits.
- Subagents (`architect`, `coder`, `code-grader`, `utility`) and the workflow rules.
- Language coders (`coder-python`, `coder-typescript`, `coder-swift`) with their navigation MCPs, detected and
  confirmed, with a `coders` command.
- `--personal-settings` and `--git-exclude` keep the changes out of git; `--dry-run`, `--without`, `--yes` and
  `--no-input` for control and automation.
