# agent-loadout

One command that gives a project a coding-agent setup, for Claude Code, Cursor and Codex.

- **Memory:** [agemem](https://github.com/illescasDaniel/agemem) keeps current state, decisions and durable notes in
  `memory/`, so a new session picks up where the last one stopped. For Claude Code, agemem (0.1.1+) also
  disables Claude's built-in auto-memory for the project, to avoid double memory.
- **Spec-driven development:** the `sdd-feature` skill takes a feature through design, spec, tests, implementation and
  an independent grade, with an approval gate between phases.
- **Subagents:** an orchestrator delegates to `architect` (design), `coder` (implementation), `code-grader` (review)
  and `utility` (commits, checks), following one shared workflow.
- **Language coders:** `coder-python`, `coder-typescript` and `coder-swift` come with code-navigation MCPs, so they
  rename and refactor through the compiler or type checker instead of `grep` and `sed`.

Each piece is handed to the tool that already installs it; agent-loadout only writes what no tool covers.

Needs `uv` (agemem, Python coder) and Node.js 20+ (skill, TypeScript coder).

`--python 3.12` makes `uvx` use a tested Python instead of whichever is newest on your machine. For a reproducible run,
also pin the version: `uvx --python 3.12 agent-loadout@0.1.0 .`

## Use

```bash
uvx --python 3.12 agent-loadout .                  # detects your clients and languages, asks before installing
uvx --python 3.12 agent-loadout . --dry-run        # prints the commands and the files they write; changes nothing
uvx --python 3.12 agent-loadout . --personal-settings --yes
```

**Everything stays inside the project.** Nothing is written to `~/.claude`, `~/.codex`, `~/.cursor` or any user-wide
config. The two exceptions: agemem keeps its own private `~/.config/agemem/config.yaml` for the API key, and the Swift
coder's binary is installed with Homebrew, only after you say yes (even with `--yes`; `--allow-brew` skips the question).

Rules go to `AGENTS.md`, or to `CLAUDE.md` if the project already has one that isn't just an `@AGENTS.md` import. Each
section sits between `<!-- agent-loadout:begin NAME -->` markers, so re-running updates it in place.

## What gets installed

| Piece | Installed by |
|---|---|
| Project memory (`memory/`, notes, MCP, hooks) | [agemem](https://github.com/illescasDaniel/agemem) `project init` |
| Spec-driven development skill | `npx skills add illescasDaniel/sdd-feature-skill` |
| Subagents (`architect`, `coder`, `code-grader`, `utility`) and the workflow rules | agent-loadout |
| Language coders (`coder-python`, `coder-typescript`, `coder-swift`) with their navigation MCPs | agent-loadout |

### Language coders

A coder is one unit: the `coder-<lang>` subagent, the language's navigation MCP and a routing rule. They are always
installed together, because without the subagent's instructions the agent doesn't use the MCP.

```bash
uvx --python 3.12 agent-loadout coders                    # detect languages, confirm, install
uvx --python 3.12 agent-loadout coders python typescript  # or name them (python, typescript, swift, all)
uvx --python 3.12 agent-loadout coders --list             # catalogue, what is detected, what is installed
```

| Language | MCP | Detected by |
|---|---|---|
| python | codenav | `pyproject.toml`, `setup.py`, `requirements*.txt`, `Pipfile`, `uv.lock` |
| typescript | webnav | `package.json`, `tsconfig.json`, `jsconfig.json`, `deno.json` |
| swift | codenav-swift (needs the Homebrew binary, macOS) | `Package.swift`, `*.xcodeproj`, `*.xcworkspace`, `Podfile` |

### Keeping it out of git

`--personal-settings` writes rules to `CLAUDE.local.md` (Claude Code only; it starts with `@AGENTS.md` if you have one),
Claude settings to `.claude/settings.local.json`, and adds every file the run created to `.git/info/exclude`. A file
that already existed and was changed (for example a committed `.mcp.json`) can't be hidden by git, so the final message
lists it with your options. With Cursor or Codex selected the rules go to `AGENTS.md` and you are told.
`--git-exclude` does the exclusion without the personal files.

### Flags

`--tools claude,cursor,codex` · `--with python,swift,typescript|all` · `--without sdd|agemem|agents|coders` ·
`--memory-model jev|qsiv` · `--no-hooks` · `--model ALIAS` · `--claude-compat` · `--dry-run` · `--no-input` · `--yes` ·
`--allow-brew` · `--force`. With `--no-input` and no `--yes`/`--with`, no language coder is installed and the command to
run is printed.

The Jev key is never asked for here. Set `AGEMEM_JEV_API_KEY` or edit `~/.config/agemem/config.yaml`.

## Development

```bash
uv run pytest
```

The design and the decisions behind it are in [PLAN.md](PLAN.md). The real Homebrew path can only be checked on macOS.
