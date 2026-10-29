# agentic-loadout: implementation plan

**Goal:** one command that gives a project the agent-guild setup (orchestrator plus subagents, memory, SDD,
language-aware coders), with much less setup machinery. agent-guild clones, pins, converts and merges everything
itself (about 1,100 lines of installer). agentic-loadout **hands each piece to the tool that already installs it** and
keeps only the parts no external tool covers: subagents, instruction-file sections, and personal-mode bookkeeping.

**Hard rule: project scope only.** agentic-loadout writes only inside the target project, always. Nothing user-wide or
machine-wide: no `~/.claude.json`, `~/.claude/`, `~/.codex/`, `~/.cursor/`, no `claude mcp add -s local|user`, no
`npx skills add -g`, no global install-mcp target. Every external command is run with its project-level option, and a
command that has no project-level option for a client is not used for that client (the built-in writer is used
instead). This is not configurable and there is no per-machine mode. Two accepted exceptions, both outside the
project files we manage: agemem's own private user config for the Jev key (agemem manages it; agentic-loadout never
writes it, it only tells the user how to set it), and the Homebrew install of the codenav-swift-mcp binary, which only
ever runs after the user confirms it (§2a).

```bash
uvx agentic-loadout .                      # interactive: detects clients, asks a few questions
uvx agentic-loadout . --dry-run            # prints the commands and the instruction-file diff, writes nothing
uvx agentic-loadout . --with python,typescript --personal-settings --no-input
```

Status: implemented in `src/agentic_loadout` (WP 1-8 except the release workflow); Phase 0 results are in §8a. **Where the text below mentions install-mcp, it is superseded: install-mcp was dropped, the built-in merger does every MCP write.** `coders` takes the project root with `--path`. Sources this plan was written from (local checkouts, 2026-10-28):
`~/Projects/Code/Agents/claude-agents` (agent-guild 1.3.4), `~/Projects/Code/Python/agemem` (v0.1.0),
`~/Projects/Code/Skills/sdd-feature-skill`, `~/Projects/Code/MCPs/{codenav-mcp,webnav-ts-mcp}`. There is no local
codenav-swift-mcp checkout; its launch spec comes from agent-guild's `specialists.py`.

---

## 1. Components and who installs them

| Component | Installed by | Notes |
|---|---|---|
| **agemem** (memory: `memory/` bank, notes, MCP, hooks) | `uvx --python 3.12 agemem@0.1.1 project init --mcp <clients> --model <jev\|qsiv> [--no-hooks] --no-input` | Replaces agent-guild's memory-bank **and** jev-mem. Registers its own `agemem` MCP server for each client. Does **not** edit AGENTS.md, so we insert its section ourselves (from `agemem/docs/AGENT_INTEGRATION.md`) |
| **sdd-feature skill** | `npx skills@<pin> add illescasDaniel/sdd-feature-skill -a <agents> -y [--copy]` | Default on; `--without sdd` skips it |
| **worktree skill** | `npx skills@<pin> add illescasDaniel/worktree-skill#<sha> -a <agents> -y --copy` | Default on; `--without worktree` skips it. Modes `/worktree create\|save\|apply\|delete`; `create` records the parent branch, `apply` merges into it. Our `worktree` rule section decides *when* to propose it (ask once if the checkout is dirty or another worktree is active; offer save/apply/delete at the end) |
| **codenav-mcp** (Python) | `npx install-mcp@1.10.2 ... --client claude-code --local -y` (see §3 for the limits) | Detected (confirmed) or `--with python`. Spec: `uvx --from 'codenav-mcp>=0.2.1,<0.3' codenav-mcp`, optional env `CODENAV_MCP_SOURCE_ROOT` |
| **codenav-swift-mcp** | same, but needs env `CODENAV_SWIFT_WRITE=1` → built-in writer (install-mcp has no `--env`) | Detected or `--with swift`. Binary via Homebrew, only after the user confirms (§2a) |
| **webnav-ts-mcp** | same as codenav. Spec: `npx webnav-ts-mcp@0.2` | Detected (confirmed) or `--with typescript` |
| **Subagents** (orchestrator rules, architect, coder, code-grader, utility, language coders) | **agentic-loadout itself** (no external tool exists) | Ported from agent-guild, with jevmem references rewritten to agemem |
| **Instruction sections** | **agentic-loadout itself** | Marker-delimited, idempotent (§4) |

agemem tool names (from `agemem/mcp.py`): `project_memory_recall`, `project_memory_capture`, `project_memory_remember`,
`project_memory_index`, `project_memory_maintain`. Server key: `agemem`. So the Claude tool IDs are
`mcp__agemem__project_memory_recall` etc.

Don't register MCPs twice: agemem registers its own server, so install-mcp and the built-in writer handle only the
three nav servers.

---

## 2. CLI surface

Python package (`agentic-loadout`, run with `uvx`), argparse, no runtime dependencies beyond `tomlkit` (Codex TOML)
if needed. The external tools are subprocesses.

| Flag | Effect |
|---|---|
| `PATH` (default `.`) | Project root |
| `--tools claude,cursor,codex` | Override client detection (same detection rules as agent-guild: `.claude/` or `CLAUDE.md` → claude, `.cursor/` → cursor, `.codex/` or `.agents/skills/` → codex; none → claude) |
| `--with python,swift,typescript` / `--with all` | Language coders (subagent + nav MCP + routing rule, always together), for exactly these languages, no detection prompt. Without the flag: detect the project's languages and ask to confirm (§2a). `--without coders` skips the step |
| `--without sdd\|agemem\|agents` | Leave a component out. `sdd` also drops code-grader and the gate section |
| `--memory-model jev\|qsiv` | Passed to agemem `--model`. Interactive prompt if absent; with `--no-input`, default `jev` |
| `--no-hooks` | Passed to agemem |
| `--personal-settings` | Keep every change out of git (§5) |
| `--git-exclude` | Without `--personal-settings`: just list *created* files in `.git/info/exclude` (agent-guild's behaviour) |
| `--claude-compat` | Write `@AGENTS.md` into `CLAUDE.md` for older Claude Code |
| `--model ALIAS` | Claude project model (shared `.claude/settings.json`, or `settings.local.json` in personal mode) |
| `--dry-run` | Print every command it would run, the files each would touch (from §3's table), and the instruction-file diff. Runs no installer (agemem's own `mcp-install --dry-run`/`hooks-install --dry-run` may be invoked to show their exact output) |
| `--no-input` | Never prompt; fail early in preflight if a required choice is missing |
| `--force` | Overwrite our own agent files that the user edited |

Kept out on purpose (agent-guild flags we drop): `--sources-dir`, `--import-cursor-skills`, `--import-auto-memory`,
`--keep-auto-memory`, `--coders-only` (re-running with `--with` is enough, since every step is idempotent).

## 2a. Language coders: detection, confirmation and the `coders` command

A **language coder** is one indivisible unit of three parts, always installed together:

1. the `coder-<lang>` subagent (generic `coder.md` body + the language's navigation instructions, with the MCP's tools
   in its `tools:` allowlist so they load up front),
2. the language's navigation MCP server in the project's MCP config,
3. a routing rule in the instruction file (marker block `coder-<lang>`) that sends that language's work to the coder.

There is no "MCP only" option: without the subagent and its instructions the agent doesn't use the MCP (agent-guild's
experience: the tools arrive deferred and coders fall back to `grep`/`sed`). Removing one part means removing the
coder.

The full install runs this step by default: it detects the project's languages, asks to confirm, and installs the
matching coders (all three parts). The same step runs on its own at any time:

```bash
uvx agentic-loadout coders                       # detect languages, show what fits, ask to confirm
uvx agentic-loadout coders python                # just one
uvx agentic-loadout coders python typescript     # several
uvx agentic-loadout coders all                   # all three, no detection
uvx agentic-loadout coders --list                # catalogue, what's detected and what's already installed
```

`coders` takes the same `--tools`, `--personal-settings`, `--dry-run`, `--no-input` and `--yes` flags as the full run,
and the same rules: project files only, idempotent, existing server entries win. It works in a project where the full
install never ran: the coder is generated from the shipped `coder.md`, and the routing rule is written to the same
target file the full install would pick (§4). It does not install the other agents, agemem or the SDD skill.

### Catalogue (one table in `coders.py`, the only place to add a language)

| Key | Server name | Launch | Env | Prerequisites |
|---|---|---|---|---|
| `python` | `codenav` | `uvx --from 'codenav-mcp>=0.2.1,<0.3' codenav-mcp` | `CODENAV_MCP_SOURCE_ROOT` when the project has a `src/` layout (detected) | uv, Python 3.11+ |
| `typescript` | `webnav` | `npx webnav-ts-mcp@0.2` | — | Node 20+ |
| `swift` | `codenav-swift` | `codenav-swift-mcp` (absolute path `$(brew --prefix)/bin/codenav-swift-mcp` for Cursor, which doesn't inherit the shell `PATH`) | `CODENAV_SWIFT_WRITE=1` | macOS 13+, Swift toolchain, Homebrew binary |

### Detection (simple marker files, project root plus one level down)

- **python**: `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements*.txt`, `Pipfile`, `uv.lock`
- **typescript** (web: JS/TS/HTML/CSS): `package.json`, `tsconfig.json`, `jsconfig.json`, `deno.json`
- **swift**: `Package.swift`, `*.xcodeproj`, `*.xcworkspace`, `Podfile`, `Cartfile`

Several matches mean several suggestions (a monorepo with a Python backend and a web front end gets both). Skip
`node_modules/`, `.venv/`, `build/`, `Pods/`, `.git/`. No file counting or heuristics beyond this; if detection misses,
the user names the language. An already-installed server (entry present in the project config) is shown as installed
and not offered again.

### Confirmation

- Interactive: "Detected Python and TypeScript. Install codenav (Python) and webnav (TypeScript) MCPs + coders?
  [Y/n]", with the option to pick a subset.
- `--yes`: accept detected suggestions. `--no-input` without `--yes` or `--with`: install none, print the command.
- `--with`/explicit `coders <lang>`: no confirmation for the coder itself (the Homebrew question below still applies).

### Swift and Homebrew

codenav-swift-mcp is a binary installed with `brew install illescasDaniel/tap/codenav-swift-mcp` (from its README;
prebuilt arm64/Intel, puts the binary on `PATH`). This is a machine-wide install, so it **always asks first, even
with `--yes`**, unless `--allow-brew` is passed:

1. Not macOS → don't offer brew; write the server config only if the user explicitly asked for `swift`, and print that
   the binary is macOS-only.
2. `codenav-swift-mcp` already on `PATH` (`codenav-swift-mcp --version`) → skip brew.
3. `brew` missing → print the Homebrew and build-from-source instructions, write the config, mark as "needs binary".
4. Otherwise ask: "Install codenav-swift-mcp with Homebrew (`brew install illescasDaniel/tap/codenav-swift-mcp`)?
   [y/N]". Declined → config written, instructions printed.
5. Xcode project (`*.xcodeproj`/`*.xcworkspace`) without `buildServer.json` → also offer `brew install
   xcode-build-server` (separate confirmation) and print the `xcode-build-server config -project … -scheme …`
   command; never run that one (it needs the scheme, so the user picks it).

**Not testable on Linux:** unit-test the decision logic with `platform` and `shutil.which` stubbed; the real brew
path is a manual check on macOS (tracked in WP 7).

### Run order

1. **Preflight** (no writes): git repo? `uv`/`uvx` present (agemem, codenav), `node`/`npx` present (skills,
   install-mcp, webnav). Language detection and the coders confirmation happen here, before any write (§2a). The
   Homebrew question for Swift is also asked here; the brew install itself runs in step 5.
   Resolve clients, target instruction file, personal-mode strategy. If something is missing, print every problem at
   once and exit non-zero before touching anything.
2. **Snapshot** git state (`git status --porcelain --ignored -z` and the list of tracked files) for §5.
3. **agemem** `project init`.
4. **sdd skill** via `npx skills add`.
5. **Language coders**: nav MCPs via install-mcp (`--local`) / built-in writer, into the project's config files only (the coder agents and routing rules are written in steps 6 and 7).
6. **Agents**: copy/convert into `.claude/agents`, `.cursor/agents`, `.codex/agents` + `.agents/development-workflow.md`.
7. **Instruction sections** (§4).
8. **Claude settings**: `--model` only. `autoMemoryEnabled: false` is now set by agemem 0.1.1 itself (in `.claude/settings.local.json`, only when absent; it was ours before,
   as agent-guild does).
9. **Diff snapshot** → personal-mode exclusions and warnings (§5).
10. **Summary**: what each step did, skipped steps, files to review, the Jev key instructions, client restart and MCP
    approval steps.

A step that fails stops the run, prints what was already done and how to re-run. Every step is idempotent, so re-running
after a fix is the recovery path (no rollback machinery).

---

## 3. File-touch matrix (verify in Phase 0)

This is the table that decides whether `--personal-settings` can actually keep changes out of git. Items marked **?**
are unverified and are Phase 0 checks.

| Step | Client | Files written (shared mode) | Personal-mode strategy |
|---|---|---|---|
| agemem `project init` | all | `memory/*.md`, `.agemem/` (config + `.agemem/.gitignore` for `/local/`) | New untracked → `.git/info/exclude` |
| agemem MCP | claude | `.mcp.json` (key `agemem`) | Exclude if new, explain if it already existed |
| agemem MCP | cursor | `.cursor/mcp.json` | Exclude if new, explain if it already existed |
| agemem MCP | codex | `.codex/config.toml` | Same |
| agemem hooks | claude | `.claude/settings.local.json` | Normally git-ignored by Claude Code; check with `git check-ignore`, exclude if not |
| agemem hooks | codex | `.codex/hooks.json` | Exclude if new, explain if it already existed |
| `npx skills add` | each | **?** `.claude/skills/sdd-feature/`, `.agents/skills/…`, symlinks, maybe `skills-lock.json` | Exclude every created path. Use `--copy` so no symlink points outside the repo |
| install-mcp `--local` | claude-code | `./.mcp.json` | Exclude if new, explain if it already existed |
| install-mcp `--local` | cursor | `./.cursor/mcp.json` | Exclude if new, explain if it already existed |
| install-mcp | codex | **global** `~/.codex/config.toml` (no `localPath`; `--local` is silently ignored) | Never use install-mcp for Codex (breaks the project-only rule); built-in writer to `.codex/config.toml` |
| our agents | each | `.claude/agents/*.md`, `.cursor/agents/*.md`, `.codex/agents/*.toml`, `.agents/development-workflow.md` | Exclude (they're new files) |
| our instruction sections | — | see §4 | see §4 |
| our Claude settings | claude | `.claude/settings.json` | `.claude/settings.local.json` |

### install-mcp: verified limits (v1.10.2, read from its `dist/run.js`)

- **Codex has no project path**: `codex` only has a global `path` (`$CODEX_HOME/config.toml`), so `--local` writes to
  the user's global config.
- **No `--env`**: codenav-swift needs `CODENAV_SWIFT_WRITE=1`, codenav may need `CODENAV_MCP_SOURCE_ROOT`.
- **No dry-run.**
- Clients: `claude, cline, roo-cline, windsurf, witsy, enconvo, cursor, warp, gemini-cli, vscode, claude-code, goose,
  zed, codex, opencode`. `claude-code --local` → `./.mcp.json`; `cursor --local` → `./.cursor/mcp.json`.

**Decision:** use install-mcp only for claude-code and cursor in shared mode, for servers without env vars. Everything
else (Codex, env vars, and the merge for existing entries) goes through a small built-in JSON/TOML merger ported from
agent-guild (`files.py` + the MCP merge in `installer.py`, which already reuses matching entries from `.mcp.json` for
Codex). If that merger exists anyway, the implementer may decide in Phase 0 to drop install-mcp entirely; record the
decision in this file.

---

## 4. Instruction file rules

Sections we add, each wrapped in markers so re-runs replace them and the user can delete them:

```markdown
<!-- agentic-loadout:begin agents -->
## Agents and delegation
...
<!-- agentic-loadout:end agents -->
```

Sections: `agents` (orchestrator rules → `.agents/development-workflow.md`), `memory` (agemem's suggested workflow,
adapted), `sdd` (Phase Gate Protocol, unless `--without sdd`), one `coder-<lang>` routing rule per `--with`, and
`friction` (decide in Open decisions). If the target already has a heading with the same name **without** our markers,
skip it and warn (the user's rules win; nothing is moved or deleted).

### Target file

| Situation | Target |
|---|---|
| Shared mode, `CLAUDE.md` exists and is not just an `@AGENTS.md` import | `CLAUDE.md` |
| Shared mode, both exist and `CLAUDE.md` is only an `@AGENTS.md` stub | `AGENTS.md` |
| Shared mode, otherwise | `AGENTS.md` (created if missing) |
| Personal mode, Claude is the only client | `CLAUDE.local.md`. If only `AGENTS.md` exists (no `CLAUDE.md`), the file must start with `@AGENTS.md`, or Claude stops reading `AGENTS.md` (see agent-guild `installer.py:270`) |
| Personal mode, Cursor or Codex selected | `AGENTS.md` (neither has a personal project instruction file). If it's tracked, warn that the edit shows in git and list the options: commit, `git update-index --skip-worktree AGENTS.md`, or revert. The summary must say this clearly |

Note for Cursor/Codex when the target is `CLAUDE.md`: they don't read it. If Cursor or Codex is selected and the target
is `CLAUDE.md`, also write the sections to `AGENTS.md` (or warn); decide in Phase 0 by checking what agent-guild did.
`--claude-compat` behaviour is unchanged from agent-guild.

---

## 5. `--personal-settings`: keep everything out of git

The hard part: most delegated tools write shared project files (`.mcp.json`, `.cursor/mcp.json`,
`.codex/config.toml`, skill folders, `memory/`). Everything stays inside the project (see the hard rule at the top), so
hiding happens with git, not by writing elsewhere. Mechanism:

1. Where the project itself has a personal file, use it: `CLAUDE.local.md` for the rules,
   `.claude/settings.local.json` for Claude settings.
2. Snapshot before step 3 and after step 8. Every path that is **new** (did not exist before the run) goes into
   `.git/info/exclude` (one block, marked `# agentic-loadout`, so a later run can update it). Directories are excluded
   as a whole (`/.claude/agents/`) when we created them; otherwise each file.
3. Every file that **already existed** and that we (or a delegated tool) changed can't be hidden by an exclude, so it
   is listed in a final message: the file, what was added to it (e.g. "server `agemem` and `codenav` added to
   `.mcp.json`"), and the user's options: commit it, `git update-index --skip-worktree <file>` to hide the local edit,
   or revert our change. This message is part of the summary, never just a log line.
4. `CLAUDE.local.md` and `.claude/settings.local.json`: check `git check-ignore`; if not ignored, add to the exclude
   block too.
5. Not a git repo: nothing can be hidden; say so in the summary.

Acceptance: in a scratch repo with a committed `AGENTS.md` and nothing else, `--personal-settings --tools claude` leaves
`git status --porcelain` empty. With `--tools claude,cursor` it shows only `AGENTS.md` modified, and the summary
explains why.

---

## 6. Porting agents from agent-guild

Copy `agents/*.md`, `development-workflow.md`, `templates/*-rules.md`, `templates/coders/*.md`, and
`src/agent_guild/{files,specialists}.py` (Claude → Cursor/Codex conversion, language coders). Then:

- Replace every jevmem reference: `mcp__jevmem__memory_recall` → `mcp__agemem__project_memory_recall` in allowlists
  (`specialists.py` `_JEVMEM_READ`), `disallowedTools` lists for write tools (`remember`, `capture`, `maintain`,
  `index` stay orchestrator-only), and the memory protocol in `development-workflow.md`. The memory-bank paths
  (`memory/activeContext.md`, `progress.md`, `decisions.md`) match agemem's bank; check the file names against
  `agemem init`'s output.
- Remove the memory-bank and jev-memory skill installs and the jevmem hooks.
- **One grader source.** `code-grader` exists in the sdd skill (`skills/sdd-feature/agents/code-grader.md`) and in
  agent-guild (same body, different frontmatter). Read the body from the installed sdd skill at install time and add
  our frontmatter, so they can't drift. If `--without sdd`, no grader.
- Keep the design choices from agent-guild's README (orchestrator is the only memory writer, `disallowedTools` instead
  of allowlists, language coders with allowlists).

---

## 7. Pinning and security

- Pin everything: `agemem@0.1.1`, `install-mcp@1.10.2`, `skills@<x.y.z>`, the sdd skill ref (Phase 0: does
  `npx skills add owner/repo#<ref>` or `@<ref>` work? If not, fall back to `--sources-dir`-style local copy or record
  the resolved commit after install), `codenav-mcp>=0.2.1,<0.3`, `webnav-ts-mcp@0.2`. Keep versions in one module
  (`pins.py`) so a release updates one file.
- Telemetry: `npx skills` sends install telemetry; check whether it has an opt-out env var (Phase 0) and set it.
- Jev key: never asked for in chat or as a flag. With `--no-input` and no key configured, agemem setup must not fail
  half-way: run it with `--model jev` if agemem tolerates a missing key, otherwise skip that part and print the
  `uvx agemem config init` instructions (Phase 0 check).

---

## 8. Phase 0 spike (do first, in a scratch git repo)

Each item is a concrete check; write the answer back into §3 or §7.

1. `npx skills add illescasDaniel/sdd-feature-skill -a claude-code -a cursor -a codex -y --copy --json`: exact files
   and dirs created, `skills-lock.json` or not, where Codex skills land.
2. Does `npx skills add` accept a commit/tag pin? Telemetry opt-out?
3. `npx install-mcp@1.10.2 "uvx --from 'codenav-mcp>=0.2.1,<0.3' codenav-mcp" --client claude-code --local --name codenav -y`:
   is the version specifier passed through intact? Does it merge into an existing `.mcp.json` without reformatting
   or dropping keys?
4. `uvx --python 3.12 agemem@0.1.1 project init --mcp claude cursor codex --model jev --no-input` with no Jev key:
   what happens? Exact files written? Does a re-run change anything?
5. Confirm none of the delegated commands writes outside the project: run each with `HOME` pointed at an empty temp
   dir and check it stays empty (apart from tool caches like `~/.npm`, `~/.cache/uv`). `agemem project init` says it
   "ensures user config": find out exactly what it writes there; if it's more than its private key/config template,
   that's a blocker to fix in agemem. Anything else written there is a blocker for that command.
6. Decide: keep install-mcp, or use only the built-in merger (§3).

---

## 8a. Phase 0 results (2026-10-29, scratch repos, `HOME` = empty dir)

1. `npx skills@1.7.4 add illescasDaniel/sdd-feature-skill -a claude-code -a cursor -a codex -y --copy` writes
   `.claude/skills/sdd-feature/`, `.agents/skills/sdd-feature/` (Cursor and Codex share it) and `skills-lock.json`.
   Nothing outside the project except `~/.npm`. The skill ships `agents/code-grader.md`.
2. Pin works: `owner/repo#<sha>` is accepted and recorded as `ref` in `skills-lock.json`. Telemetry opt-out:
   `DISABLE_TELEMETRY=1` (also `DO_NOT_TRACK`).
3. **install-mcp is dropped.** It keeps the shell quotes literally (`"'codenav-mcp>=0.2.1,<0.3'"`, broken spec), drops
   `type: stdio`, and has the limits in §3. The built-in merger does every MCP write.
4. `agemem@0.1.1 project init --mcp claude cursor codex --model jev --no-input` works with no key. It writes `.agemem/`,
   `memory/`, `.mcp.json`, `.cursor/mcp.json`, `.codex/config.toml`, `.claude/settings.local.json` (hooks) and
   `.codex/hooks.json` (Cursor has no hooks). Re-running changes nothing. Its entries contain the **absolute project path**
   (`--project /abs/path`), so they are machine-specific.
5. Only user-level write: `~/.config/agemem/config.yaml` (template, `api_key: null`). That is the accepted exception.
6. Decision: no install-mcp; WP 2 only wraps agemem and skills.
7. **Upstream issue (agemem):** its MCP and hook entries embed the absolute project path, so they can't be committed
   for a team. agentic-loadout warns in shared mode and leaves the entries alone (agemem writes them). A portable form
   (relative path or `${workspaceFolder}`) would be an agemem change.

---

## 9. Work packages

Disjoint files so several agents can work in parallel after Phase 0. `WP` numbers are not an order, see dependencies.

| WP | Scope | Files | Depends on | Done when |
|---|---|---|---|---|
| **0** | Phase 0 spike | updates to `PLAN.md` | — | Every §8 item answered |
| **1** | Package skeleton, CLI, client/language detection, preflight, prompts, run order, summary | `pyproject.toml`, `src/agentic_loadout/cli.py`, `detect.py`, `preflight.py`, `pins.py` | 0 | `--dry-run` prints the full plan for a sample repo; `--no-input` fails early with every missing choice listed |
| **2** | External tool runners (agemem, skills, install-mcp), each with a dry-run rendering | `runners.py` | 0 | Each runner is a pure "build command" function + a thin executor; unit-tested on the commands built |
| **3** | Built-in MCP merger (JSON + Codex TOML, env vars) | `mcp_config.py` (ported) | 0 | Merges into existing configs without losing keys or formatting; existing entries win |
| **3a** | `coders` subcommand and default step: catalogue, language detection, confirmation, Homebrew flow for Swift; calls WP 3 (MCP), WP 4 (agent) and WP 5 (routing rule) | `coders.py`, `brew.py` | 2, 3, 4, 5 | §2a behaviour covered by tests with platform/`which` stubbed; a coder is never left half-installed; `coders --list` shows detected + installed |
| **4** | Agent port + jevmem → agemem rewrite + single grader source | `assets/agents/`, `assets/templates/`, `agents.py`, `specialists.py` | — | Generated agents for 3 clients match agent-guild's output except for the memory changes; no `jevmem` string anywhere |
| **5** | Instruction writer: target selection, markers, skip-and-warn, `CLAUDE.local.md` import rule | `instructions.py` | — | All §4 table rows covered by tests |
| **6** | Personal mode: snapshot, diff, `.git/info/exclude` block, tracked-file warnings | `git_state.py` | — | §5 acceptance criteria pass |
| **7** | Tests + CI | `tests/`, `.github/workflows/` | 1–6 | End-to-end test in a temp git repo with external commands stubbed (PATH shims), plus one opt-in live test. Manual macOS checklist for the Swift/Homebrew path |
| **8** | README with the "paste this prompt into your agent" install block (like agemem's and agent-guild's), release workflow (`pypi-publishing` skill) | `README.md`, `CHANGELOG.md` | 1–6 | — |

---

## 10. Open decisions (defaults in bold; change before implementing)

1. **Name:** `agentic-loadout` (the folder name). Separate package, not a new agent-guild major version.
2. **Implementation language:** **Python + `uvx`**, matching agent-guild and agemem (Node is required anyway for
   `npx`, so a Node CLI is the alternative).
3. Personal mode with Cursor/Codex: **write to `AGENTS.md` and warn** (as you described). Alternative: refuse unless
   `--tools claude`.
4. Friction log and its section from agent-guild: **drop** (it depended on memory-bank's `memory/friction/`).
   Alternative: keep it as an optional `--with friction`.
5. Auto-memory: **set `autoMemoryEnabled: false` when absent**, since agemem is the memory.
6. agent-guild after this ships: **keep it, point its README to agentic-loadout**.
