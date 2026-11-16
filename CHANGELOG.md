# Changelog

## [0.7.2] - 2026-11-16

### Added
- memory-1's session export now reads [opencode](https://opencode.ai) sessions too (from its SQLite database, opened
  read-only; subagent sessions are skipped), next to Claude Code and Codex (memory-1 at `9572f47`).

## [0.7.1] - 2026-11-16

Found while upgrading a real project from 0.6.x.

### Fixed
- Agent files that were kept because you edited them, and that still tell agents to use agemem tools, are now named in
  the final review list with the two ways to fix them (`--force`, or have your agent remove the agemem instructions).
  Before, they were only reported as "differs from the shipped version".
- memory-1's session export no longer writes Codex subagent and automatic-review rollouts as sessions (memory-1 at
  `642ef0c`); in one project they were about half of the exported files.
- `export_sessions.py --entire --dry-run` no longer lists as new the Entire sessions that the same run would already
  write from the agent's own transcripts.

## [0.7.0] - 2026-11-16

### Breaking
- **agemem is no longer installed.** The agemem MCP server, its hooks, its `uvx` install and the `memory-wrapup` skill
  are gone, and so are the `project_memory_*` tools the rules and subagents used. Project memory is now plain Markdown in
  `memory/`, kept by the [memory-1](https://github.com/illescasDaniel/memory-1-skill) skill, and project docs by the
  [docs-1](https://github.com/illescasDaniel/docs-1-skill) skill. Memory no longer needs a server, a hook or `uv`.
  Re-running on a project set up with agemem removes the MCP entries, hooks and wrap-up skill, rewrites the memory rules
  section, and leaves `.agemem/` and `memory/activeContext.md`, `progress.md`, `decisions.md`, `archive.md` on disk, listed
  in the final message. Converting them is manual; the README has a prompt to paste into your coding agent.
- Entire session history is now **opt-in**: use `--with entire` (or `--entire`). It used to be on whenever the `entire`
  CLI was installed. A project whose rules already have the Entire section keeps it on (with a note); `--without entire`
  turns it off and removes that section. `--entire` is now an option of its own; it used to be an accepted abbreviation
  of `--entire-upload-sessions`, which must now be written out.
- The `.agents/scripts/entire_sessions.py` adapter is gone (removed on re-run when it is the script loadout installed).
  Its work is done by `export_sessions.py --entire`, part of the memory-1 skill copy.
- The Claude Code setting `autoMemoryEnabled: false` is no longer written. An existing value is left alone. The README now
  recommends setting it, so there is one shared memory in the repository.

### Changed
- memory-1 and docs-1 are shipped inside the package as adapted copies, each pinned to the upstream commit it was made
  from (`src/agentic_loadout/assets/skills/UPSTREAM.md`), and copied into `.claude/skills/` and `.agents/skills/`; they are
  no longer fetched with `npx skills`. A project that had them from `npx skills` gets one copy: the npx copy is replaced and
  its `skills-lock.json` entry removed. Node.js is needed only for the `sdd-feature` and `worktree` skills and the
  TypeScript coder.
- Each installed skill folder gets a `.loadout-manifest.json` with the hash of every file, so a later release updates
  the files you did not edit and keeps the ones you did (`--force` overwrites those too).
- Entire needs CLI 0.10.0 or newer (0.12.2 and 0.13.2 were tested). A missing or older CLI is reported with install
  instructions and what was skipped; the run continues.
- The architect, coder and workflow texts no longer name agemem tools.
- `--without agemem` is accepted as `--without memory` (new: `--without docs`); `--memory-model` is accepted and ignored,
  both with a notice.

### Added
- `export_sessions.py --entire` in the memory-1 copy adds sessions that only Entire has (read from git data, same format
  and redaction, never rewrites a file). It reads Entire's compact transcript format version 1 and warns on any other.
- `scripts/sync_skills.py` rebuilds the vendored skills from upstream checkouts at given commits and checks that removing
  the marked loadout blocks gives the upstream files back byte for byte.

## [0.6.1] - 2026-11-13

- Update agemem to 0.4.0: every recall returns a one-line summaries tier (one `>` abstract per
  `memory/*.md`, seeded by `agemem init`), and `project_memory_recall` accepts an optional `path`
  under `memory/` that scopes the bank and source layers to that subtree while notes stay global —
  measured 90–96% smaller packets at equal relevance against released 0.3.0.
- The memory rules section new projects receive teaches the abstract rule and `path`-scoped recall.

## [0.6.0] - 2026-11-10

- Update agemem to 0.3.0 and install its `memory-wrapup` skill (pinned, only that skill) whenever agemem is installed.
  The skill works agemem's pending queue with `project_memory_pending`, `project_memory_resolve` and
  `project_memory_dismiss`.
- Refresh the memory rules section to agemem's revised guidance (what memory is for, confidence marks, `CONFLICT:`
  lines, correcting stale notes, one topic file per parallel agent) and tell the main agent to suggest the wrap-up when a
  task is finished and before a push, before handing a commit to a subagent. Re-running updates the section in place.
- Subagents (`architect`, `coder`, `code-grader`, `code-reviewer`) may not call `project_memory_resolve` or
  `project_memory_dismiss`, in addition to the existing memory-writing tools.

## [0.5.0] - 2026-11-04

- Add normal and small Go coders with codenav-go MCP navigation and Go module/workspace detection. The public MCP runs
  through `go run ...@latest`; reruns migrate the previous WIP binary path while preserving environment settings.
- Add optional Entire checkpoint capture and agent guidance, enabled when Entire is installed. Automatic transcript
  uploads are disabled by default and require explicit opt-in.
- Update agemem to 0.2.2 and preserve existing project provider settings, including QSIV-to-Jev cascade, on reruns.
- Update the project image and installer prompt to explain how Entire complements agemem without requiring Entire hosting.

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
