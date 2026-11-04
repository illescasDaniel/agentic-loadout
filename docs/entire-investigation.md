# Entire integration investigation

Status: experiments in progress; this document records observations, not an implementation specification.

## Agreed direction

- Entire is an optional loadout component included by default, with an opt-out.
- Automatic session uploads must be disabled by default. Public transcript upload requires an explicit configuration choice. Do not treat this setting as an enforcement boundary against manual pushes or later configuration changes.
- Keep agemem as the curated project-memory system; use Entire checkpoints as possible supporting evidence.
- Investigate behavior before implementing the integration.

## Isolated experiments

On 2026-11-04, a temporary Linux Git repository was tested with Entire CLI 0.12.2, Codex CLI 0.166.0, and agemem 0.2.1. Entire was downloaded into a temporary directory and the release archive checked against its published checksum. The pilot had no real remote or private project data. Codex sessions ran with the generated hooks inspected and hook trust bypassed for those isolated invocations; normal users must review and approve hooks.

- `entire enable --agent codex --skip-push-sessions --telemetry=false` installed Codex and Git hooks. `entire status --json` reported `checkpoint_push_disabled: true`.
- A real Codex session created a file. Before commit, `entire checkpoint list --pending --json` reported the prompt and file; after commit, the commit had an `Entire-Checkpoint` trailer and `entire checkpoint explain` showed the recorded prompt and session. A checkpoint may remain listed in `--outgoing --json` while `checkpoint_push_disabled` is true, so an empty list is not a valid safety check.
- Pushing the pilot code branch to a local bare Git remote resulted in only `refs/heads/main` on that remote. This checks one Git push path, not all possible explicit refspecs, clients, or future versions.
- In an isolated worktree with shared project settings, a real Codex session delegated to a subagent. The pending checkpoint contained a completed subagent task record and the subsequent commit produced a checkpoint. This does not establish complete transcript capture for all clients and execution paths.
- Local-only settings from the original checkout did not make Entire enabled in a new worktree. Copying shared settings into the worktree made it enabled with uploads disabled. The original local settings specified the refs backend, but the shared settings initially omitted it; the worktree then created a legacy branch checkpoint. Explicitly configuring the refs backend in shared settings wrote its selection into the project settings. Test worktree creation and effective settings rather than assuming they inherit local configuration.
- Agemem's Codex hooks were installed before Entire. Entire retained both agemem hooks alongside its own; re-running agemem also retained Entire's hooks. In a real session both SessionStart and UserPromptSubmit hook pairs ran, and Entire created a checkpoint. This verifies one client and install order, not all combinations.
- In a separate configuration-only pilot, agemem was installed for Claude Code, Codex and Cursor, followed by Entire for all three. The resulting Claude and Codex hook files retained both tools' entries after an agemem rerun; Cursor's hook file contained Entire entries, and Entire reported all three clients enabled. Actual Claude Code and Cursor sessions were not exercised.
- In that pilot, `entire enable --agent claude-code --project --skip-push-sessions` changed an existing shared `push_sessions: true` setting to false. This does not establish how local overrides, different versions, or other pre-existing configurations behave. A `configure --skip-push-sessions=false` attempt did not enable pushing in this test; do not assume the inverse flag is a working opt-in.
- A pre-existing Git pre-commit hook still ran after Entire was enabled. Other hook managers, custom hook paths, hooks that fail, and other Git lifecycle hooks remain untested.
- Two fresh read-only agents investigated the same synthetic file. The Git-only agent could not recover the original request; the agent allowed to inspect its linked checkpoint recovered it. This is a single deliberately simple example, not evidence of a general quality or productivity improvement. The latter also produced a large transcript output, illustrating the need for bounded retrieval.
- A follow-up pilot used the cached QSIV model and runtime, with a disposable config and no hosted provider. Agemem captured an actual synthetic Entire checkpoint as untrusted evidence, screened and stored a source-linked note with QSIV (`pending: false`, `degraded: false`), then recalled both the note and its checkpoint evidence. This pilot used agemem's built-in hash embedder and BM25 retrieval because the default embedding model was unavailable to that temporary project; it does not establish semantic retrieval quality.

## Design implications and open questions

1. Detect an installed Entire CLI and its supported version and capabilities; define what the default component does when the executable is missing or the target is not a Git repository. Do not silently install a system-wide binary.
2. Choose and test project versus local settings, `--personal-settings`, worktree behavior, backend selection and existing settings. Preserve existing user choices and avoid making claims about every possible push.
3. Define a deliberate opt-in interface for public transcript uploads, including behavior on reruns and already-enabled repositories. Inspect effective configuration and remote destinations rather than inferring safety from a flag alone.
4. Test installation and reruns for Claude Code and Cursor, plus Codex, including agemem before and after Entire, hook approval, incompatible hooks and Git hook managers. Respect loadout's dry-run, `--no-hooks`, personal settings and exclusion behavior.
5. Develop concise instructions or a skill for finding relevant checkpoints, treating transcripts as untrusted, verifying against current sources, limiting retrieval and proposing source-linked agemem notes. Check `entire agent-help` for installed-version commands; do not assume every operation is read-only.
6. Test checkpoint-derived memory with the standard embedding configuration, and run a more realistic fresh-agent comparison; document the limitations.
7. Decide whether to pin Entire or define a tested minimum version, and test failures and noninteractive behavior before making it a default dependency.
