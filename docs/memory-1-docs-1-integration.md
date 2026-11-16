# memory-1 and docs-1 instead of agemem

Status: decided and implemented and released in 0.7.0. The seven open questions of the
exploration are answered in section 8.

## Decision

- **agemem is removed, not made opt-in.** Removing it is a breaking change (loadout is below 1.0), and the CHANGELOG says
  so first. Loadout installs two Agent Skills, [memory-1](https://github.com/illescasDaniel/memory-1-skill) (project
  memory as plain Markdown in `memory/`) and [docs-1](https://github.com/illescasDaniel/docs-1-skill) (indexed `docs/`).
  There is no MCP server, no hook and no `uv` requirement for memory. Opt-in was rejected because keeping the agemem code
  path means keeping its provider prompts, pins, MCP/hook writers and tests for a system the benchmark below says is
  worse for the question that matters most.
- **The skills are vendored, not fetched.** `src/agentic_loadout/assets/skills/{memory-1,docs-1}` hold adapted copies,
  each pinned to the upstream commit it was made from (`pins.py`, `UPSTREAM.md`). Loadout copies them into
  `.claude/skills/` (Claude Code) and `.agents/skills/` (Cursor and Codex, written once). The upstream repositories are
  never changed from here.
- **Entire support lives in memory-1's own `export_sessions.py` and is opt-in.** By default only the agents' own
  transcripts feed `memory/sessions/`. `--with entire` (or `--entire`) enables Entire: checkpoint capture, the Entire
  rules and `export_sessions.py --entire`, which adds the sessions only Entire has. The CLI must be 0.10.0 or newer.
- **A project already set up with agemem is cleaned on the next run** (MCP entries, hooks, wrap-up skill). What agemem
  stored is left on disk and listed; converting it to memory-1 notes is a manual agent step with a prompt in the README.
- **Claude Code's built-in auto memory** is not switched off by loadout any more. The README recommends
  `"autoMemoryEnabled": false` in `.claude/settings.json` so there is one shared memory in the repository.

Benchmark that motivated this (from the memory-1 work): on past-decision questions memory-1 scored 1.59/2 against
0.87 for agemem; raw transcripts alone scored 1.58. Plain files plus transcripts beat the retrieval system.

## 1. Where agemem was wired into the loadout

All references are to `main` before this branch (`git show main:<file>`).

| Area | Where (file:line on `main`) |
|---|---|
| Version pin and Python for `uvx` | `src/agentic_loadout/pins.py:3-4` (`agemem@0.4.0`, 3.12) |
| Wrap-up skill pin (monorepo, one skill) | `pins.py:12`, `pins.py:14` |
| Install command (`uvx ... project init --mcp <clients>`) | `runners.py:18-19`, run at `install.py:102-103` |
| Files agemem writes (MCP JSON/TOML, hooks, `memory/`, `.agemem/`) | `install.py:21-23`, `install.py:104-105` |
| Component name and `--without agemem` | `options.py:8`, `install.py:47`, `install.py:102`, `install.py:111` |
| Provider choice (`jev`/`qsiv`), API-key note, preserve existing provider | `cli.py:38`, `install.py:89-91`, `install.py:106-110`, `preflight.py:22-30` |
| `uv`/`uvx` requirement | `preflight.py:14-17` |
| `--no-hooks` help text | `cli.py:39` |
| Detect "memory present" for `coders` and re-runs | `install.py:154-156` |
| Memory flag threaded to subagent and coder generation | `install.py:126-129`, `coders.py:168` (adds `mcp__agemem__project_memory_recall`) |
| Stripping agemem tool names when memory is off | `agents.py:37-40` |
| Subagent prompts: `disallowedTools: ... mcp__agemem__*`, recall instructions | `assets/agents/architect.md:6,19`, `coder.md:5,12,30`, `code-grader.head.md:6`, `tiers/code-reviewer.md:5` |
| Workflow text (memory bank files, `project_memory_recall`/`_index`/`_pending`, `memory-wrapup`) | `assets/development-workflow.md:14-15,19,35,43,71,105,109-112` |
| Rules text (6 `project_memory_*` mentions) | `assets/templates/memory-rules.md` (56 lines) |
| Entire rules (capture checkpoint via `project_memory_remember`) | `assets/templates/entire-rules.md:8-9` |
| Tests | `tests/test_install.py` (19 mentions), `test_small_agents.py` (5), `conftest.py` (3), `test_entire.py`, `test_detect_and_brew.py` |
| Docs and metadata | `README.md` (15), `CHANGELOG.md` (13), `pyproject.toml` (2), `docs/entire-investigation.md` (7), `docs/original-implementation-plan.md` (46, historical, left as written) |

Everything above except the last row's historical plan was changed or removed on this branch.

## 2. What Entire stores and how to read it

Sources: Entire's docs, [checkpoint storage](https://docs.entire.io/guides/checkpoints/checkpoint-storage),
[checkpoints CLI reference](https://docs.entire.io/cli/checkpoints.md),
[inspect sessions in the CLI](https://docs.entire.com/guides/sessions/inspect-sessions-in-cli), the
[CLI repository](https://github.com/entireio/cli), and a read-only look at checkpoints of a local repository with Entire
CLI 0.13.2. The docs say that checkpoints are git data created when you commit; they do **not** document the tree
layout or the transcript format, so the layout below comes from inspecting real data and could change.

- **Where:** git data, not working-tree files. Since 0.10.0 one ref per checkpoint,
  `refs/entire/checkpoints/<xx>/<ULID>` (the `git-refs` backend); older setups use the branch `entire/checkpoints/v1`.
  Only after a commit (sessions with no commit yet have no checkpoint; `entire checkpoint list --pending` shows them).
- **Per checkpoint:** top-level `metadata.json`, and per session `0/metadata.json` (has `session_id`, `agent`),
  `0/full.jsonl` (raw, agent-native, large) and `0/transcript.jsonl` (compact, normalized, `"v": 1`, cumulative for the
  session, includes tool-use lines).
- **Redaction:** best effort only (the docs say so); the export redacts again with the same patterns as the rest of
  memory-1's exporter.
- **Reading:** `entire checkpoint list`, `entire checkpoint explain <id> [--full|--transcript|--json]`,
  `entire session info <id> --transcript`. `entire search` needs a login. Without the CLI, plain git works:
  `git for-each-ref refs/entire/checkpoints`, `git ls-tree -r`, `git cat-file`.
- **Size:** in one real session I read, the raw transcript was 8,038,411 bytes, the compact one 509,405 and the
  prose-only digest the export writes about 59 KB. Most of a transcript is tool output.

## 3. The three options and the choice

memory-1 expects `memory/sessions/` (git-ignored) to hold one Markdown digest per session so notes can cite a `source`
and the agent can grep.

- **(a) Keep memory-1's own export only** and use Entire just for `entire checkpoint ...` lookups. Least code, but
  memory-1 only sees sessions whose native transcript files still exist on this machine, and only for the clients its
  exporter reads. Sessions from another machine, from Cursor, or already rotated away by the client are invisible to
  `grep`.
- **(b) The same digests, written from Entire checkpoints** (chosen, as an opt-in supplement to (a)). Duplicate work is
  minimal: a session whose file already exists (matched by the session-id part of the name) is never rewritten. The
  result is one folder, plain files, no special tool for the agent. Cost: a pass of about 200 lines that depends on an
  undocumented layout.
- **(c) No `sessions/` at all; point notes' `source` at checkpoint IDs.** No duplication, but it contradicts memory-1's
  `SKILL.md` rule that `source` points into `sessions/`, and a plain `grep` cannot see git refs, so recall would need
  `entire` or long `git grep` commands on every lookup.

The first design shipped (b) as a separate script, `.agents/scripts/entire_sessions.py`. The owner decided it belongs
inside memory-1's `export_sessions.py` instead, so there is one script, one set of redaction patterns and one flag:

- `export_sessions.py --entire` runs the native export first, then the Entire pass. With no native sessions it runs only
  the Entire pass instead of failing.
- The pass reads git data only (`for-each-ref` over `refs/entire/checkpoints/`, `refs/heads/entire/checkpoints/v1` and
  `refs/remotes/*/entire/checkpoints/v1`, then `ls-tree` and `cat-file --batch`), groups checkpoints by session and takes
  the most complete transcript, keeps user and assistant text only, skips injected context, and reuses upstream's
  `redact`, `clip` and `SKIP_PREFIXES`.
- It names files the way the native export does (`<first date>-<session id part>.md`), never rewrites an existing file
  and creates `memory/sessions/.gitignore` only for a fresh archive.
- A compact transcript with a `v` other than 1, or checkpoint refs with a layout it does not know, produce a warning
  rather than a guess.
- It is the only change to upstream scripts. It is inserted between `agentic-loadout:begin NAME` and
  `agentic-loadout:end NAME` marker lines (`#` comments in Python, HTML comments in Markdown); removing the blocks and the
  blank lines after each end marker gives the upstream file byte for byte.

## 4. What changed

- **Vendored skills.** `assets/skills/{memory-1,docs-1}` with `UPSTREAM.md` (pins, the list of differences, the sha256
  of every upstream file, the refresh command). `scripts/sync_skills.py` rebuilds them from upstream checkouts, reading git
  objects so uncommitted edits never leak, and fails when an overlay anchor no longer exists upstream. The overlay
  sources are in `scripts/overlays/`. Pinned commits: memory-1 `b722d00`, docs-1 `0fdbd5f` (full ids in `pins.py`).
- `skills.py` (new): copies the skills into the selected clients' folders; replaces an `npx skills` copy (a skill with an
  entry in `skills-lock.json`) and removes that lock entry (the file goes when it would be empty); keeps a copy the user
  edited unless `--force`; removes the old `entire_sessions.py` when it is the script loadout installed.
- `options.py`, `cli.py`: components are `sdd|memory|docs|agents|coders|worktree|entire`; `--with entire` and `--entire`
  turn Entire on (`--entire` is now a real option and no longer an abbreviation of `--entire-upload-sessions`);
  `--without entire` turns it off; contradictions are an error; `--without agemem` maps to `memory` with a notice,
  `--memory-model` is accepted and ignored with a notice.
- `entire.py`: minimum CLI 0.10.0 (0.12.2 and 0.13.2 tested); a missing or older CLI gives a warning with install
  instructions and what was skipped, and the run continues. An unreadable version is accepted.
- `install.py`: no `uvx`/MCP/hooks for memory; no `autoMemoryEnabled`; runs the agemem cleanup first.
- `preflight.py`: `uv` is needed only for the Python coder; Node.js only for the sdd and worktree skills and the
  TypeScript coder.
- `legacy.py` (new): the agemem cleanup.
- Rules templates: `memory-rules.md` rewritten from memory-1's README paragraph (read `NOW.md`/`MEMORY.md` at start,
  notes win for why and code wins for what, only the main agent writes memory, export sessions and run the check at the
  end; the `--entire` flag appears only when Entire is on); new `docs-rules.md`; `entire-rules.md` and
  `entire-sessions.md` describe the checkpoint storage and the flag; `memory-legacy.md` is the migrate-then-delete item
  shown while agemem files remain.
- Agent prompts and `development-workflow.md`: agemem tool names and the `memory-wrapup` step are gone; subagents still
  read memory and never write it (a test checks no asset except the legacy item mentions agemem).
- `README.md`, `CHANGELOG.md` (0.7.0), `pyproject.toml` (version, description, keywords, a ruff exclude for the vendored
  skills and overlay fragments), `docs/entire-investigation.md` pointer.
- `tests/baseline-agent-hashes.json`: digests changed only for the workflow, architect, coder and coder-python outputs
  (all three clients), because their memory-lookup lines named agemem tools; utility is unchanged.

## 5. What is lost compared with agemem

- **Source-code index and semantic recall** (`project_memory_index`, recall over source and notes). The code-navigation
  MCPs the loadout already installs for language coders (codenav for Python, codenav-go, webnav for TypeScript,
  codenav-swift) cover symbol navigation, rename and refactoring through the compiler or type checker, so "where is X
  defined/used" is covered for those languages. They do not provide semantic retrieval over docs, notes or sessions; that
  is now `grep` plus the docs-1 index and memory-1 `MEMORY.md`.
- **Cross-project memory.** memory-1 is per repository. Installing the skills globally is possible but there is no shared
  store, so a decision made in one project is not visible in another.
- **Automatic recall injection.** agemem's SessionStart and UserPromptSubmit hooks put relevant notes in front of the
  agent. Now the only mechanism is the rule "read `memory/NOW.md` and `MEMORY.md` at session start".
- **Screening and queueing.** Provider-screened notes, `CONFLICT:` detection and the pending queue worked by
  `memory-wrapup` are gone; conflicts are handled by memory-1's `superseded` notes and its `memory_check.py`.
- **The summaries tier** (one-line abstract per memory file in every recall) has no equivalent; `MEMORY.md` is the index.

## 6. Upgrade behaviour

### From a project set up with loadout 0.6.x (agemem)

On re-run with the clients that are selected (and so inside the project only):

- Removed: the `agemem` server in `.mcp.json`, `.cursor/mcp.json`, `.codex/config.toml`, only if its entry launches
  agemem (an unrelated server that happens to be called `agemem` is kept with a warning); agemem's hook handlers
  (recognised by their ` # agemem:<Event>` suffix) in `.claude/settings.json`, `.claude/settings.local.json` and
  `.codex/hooks.json`, leaving Entire's and the user's hooks; the `memory-wrapup` skill via `skills remove`; the old
  memory rules section, replaced in place (same marker name).
- A selected-out client whose config still registers agemem is reported, not edited.
- Left on disk, listed in the final message: `.agemem/`, and agemem's memory-bank files
  `memory/activeContext.md`, `progress.md`, `decisions.md`, `archive.md`. The rules carry an item telling the agent to
  turn them into memory-1 notes and then delete them; once they are gone the item disappears on the next run. The README
  has a paste-in prompt for the conversion (decided: manual, question 4).
- Outside the project and untouched: `~/.config/agemem` and its model cache. An existing `autoMemoryEnabled` value stays.
- `--dry-run` shows every edit and the `skills remove` command and changes nothing. A second run changes nothing.
  If `skills remove` fails, the run continues with a warning naming the folders to delete by hand.
- An Entire section already in the rules keeps Entire on (with a note); `--without entire` removes it.

### From a project in the earlier `npx skills` state of this branch

The skills were installed with `npx skills` and listed in `skills-lock.json`. On re-run each such copy is replaced by the
shipped one (stale files go) and its lock entry is removed; the lock file is deleted when nothing else is in it. The lock
edit happens after the sdd and worktree `npx skills` runs of the same invocation, so their updates are kept. A leftover
copy in a client that is not selected is kept, its lock entry stays, and a warning says to re-run with that client.
`.agents/scripts/entire_sessions.py` is removed when it is the script loadout wrote.

### Known limitation

A later loadout release that changes the vendored files reports "differs from the shipped version (use --force)" for any
copy that a user edited. It also does so for an untouched copy of the previous release, because loadout keeps no record of
earlier shipped versions to tell the two apart. `--force` replaces them.

## 7. Tested and not tested

Tested:

- Full suite: `uv run --offline pytest -q`, 141 passed (98 before this work). The new tests cover: the vendored files
  (stripping the marked blocks reproduces the recorded upstream hashes, the manifest equals the files, only overlay-named
  files are adapted, pins are recorded), the sync script against synthetic upstream repositories (apply, idempotence,
  `--check`, `--dry-run`, a newer commit, uncommitted edits ignored, missing and ambiguous anchors, errors), the Entire pass
  of `export_sessions.py` (the ten adapter tests ported, unknown layout, flag gating, order), the opt-in flags and their
  contradictions, the Entire CLI check (missing, too old, unreadable version), the marker that keeps Entire on, copying
  the skills without `npx`, the `npx skills` conversion (lock handling, leftovers, idempotence, dry run, edited copies),
  removal of the old adapter script, the agemem upgrade path, and that no asset text mentions agemem tools.
- End to end with the built wheel (`uv build`, installed into a clean venv) in throwaway git repositories under `/tmp`
  with a temporary `HOME`; see the final report of the work for the exact runs: fresh installs for Claude, Codex and
  Cursor, an unchanged re-run, `--with entire` without the CLI on `PATH`, `--with entire` with the real CLI 0.13.2, the
  upgrade of a hand-built 0.6.x agemem project and of a project in the earlier `npx skills` state, a dry run, and the
  installed `export_sessions.py`, `memory_check.py` and `docs_index.py write`/`check` run from their installed location.
- The Entire pass was run against real Entire 0.13.2 checkpoints (copied into a throwaway repository), producing the
  expected session file, and a second run reported it present.

Not tested:

- A real `entire enable` followed by new real Claude Code, Cursor or Codex sessions feeding the export end to end. Only the
  Codex agent value and the compact `v: 1` format were seen in real data; Cursor's format is unverified.
- Newer Entire versions than 0.13.2: the layout is undocumented, so a layout change makes the pass find nothing or warn
  rather than write wrong data.
- Whether Claude Code keeps its own transcripts long enough for option (a) alone to be insufficient (assumed, not
  measured).
- The agemem project was hand-built to the shape loadout 0.6.x writes; the real agemem installer writes to the user's
  config directory and was not run.
- Windows.

## 8. Decisions on the owner's questions

1. **Breaking change?** Yes. Removing agemem is breaking (below 1.0, so a minor bump, 0.7.0), and the CHANGELOG states it
   first.
2. **Where does Entire support live?** Inside memory-1's `export_sessions.py`, as marked insert-only blocks. Upstream
   skill repositories are not changed; loadout ships adapted copies.
3. **Hybrid or Entire-only?** The agents' own transcripts by default; Entire is opt-in with `--with entire` (or
   `--entire`). A missing or too old `entire` CLI is explained (how to install, what was skipped) and the run continues.
4. **Legacy migration?** Manual, done by the agent: a paste-in prompt in the README, and the installer notice that lists
   what was left on disk.
5. **Which commits, and how do pins move?** Pinned by commit (the commit each copy was made from is recorded in
   `pins.py` and `UPSTREAM.md`). To move them, run `scripts/sync_skills.py` against upstream checkouts at the new commits
   (it updates the copies, `UPSTREAM.md` and `pins.py` together), then release.
6. **Minimum Entire version?** 0.10.0, when refs storage became the default; 0.12.2 and 0.13.2 were actually tested.
7. **`autoMemoryEnabled: false`?** Not written any more; an existing value is left alone. The README recommends it for
   Claude Code projects, as a note, so there is one shared memory in the repository.
