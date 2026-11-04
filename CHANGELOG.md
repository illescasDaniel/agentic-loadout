# Changelog

## [0.4.0] - 2026-11-04

- Add normal and small Go coders with codenav-go MCP navigation and Go module/workspace detection. The public MCP runs
  through `go run ...@latest`; reruns migrate the previous WIP binary path while preserving environment settings.
- Add optional Entire checkpoint capture and agent guidance, enabled when Entire is installed. Automatic transcript
  uploads are disabled by default and require explicit opt-in.
- Update agemem to 0.2.2 and preserve existing project provider settings, including QSIV-to-Jev cascade, on reruns.

## [0.3.0] - 2026-11-03

- Install small-model coder variants and an independent reviewer alongside standard coders, with shared language navigation and delegation guidance.
- Existing installations gain the new files on re-run. Customized generated files are preserved unless `--force` is used; omitted components are not deleted. Model availability and Cursor fallback depend on the account.

## [0.2.1] - 2026-10-29

- Requires agemem 0.2.1, which makes the shared memory store safe when several worktrees or processes write at once.

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
