# Plan: model tiers for delegated work

Status: proposal for review, 2026-11-03. No implementation is authorized by this plan alone.

## Goal and decisions

Make small-model delegation available for well-defined work while preserving language-specific navigation and independent review. Keep the current standard coders; add generic and language-specific `-small` counterparts. The orchestrator chooses an appropriate role for the task and honors the developer's choice.

When a developer mentions usage limits or asks for multiple parallel subagents, suggest small-model agents as an option when appropriate. Explain the tradeoff briefly and proceed according to their answer. An explicit request to use a tier is sufficient; do not ask again. Do not automatically switch models merely because limits are mentioned, read usage data, configure a status line, or infer that quotas are separate. Routine delegation without either trigger should not generate repeated suggestions. Keep established preferences for the session and avoid prompting on every block.

The earlier project implementation plan is preserved in `docs/original-implementation-plan.md`.

## Current behavior and constraints

- `assets/agents/coder.md` is a Sonnet agent. `coders.py` builds each language coder from that shared body plus its navigation fragment and tool list. The language routing sections currently direct all relevant code to the standard specialist.
- `assets/development-workflow.md` describes the generic and language coders, independent SDD grading, task routing and orchestrator responsibilities. The `code-grader` is sourced from the installed SDD skill and is an Opus final grade, not a general implementation reviewer.
- `vendors.py` converts Claude-format agents for Cursor and Codex. Cursor currently inherits the parent model; Codex conversion currently drops the Claude model. Merely naming an agent `small` therefore does not guarantee a smaller model.
- Coders may be installed without the generic agent suite through `agentic-loadout coders`. `--without agents`, `--without sdd` and `--without agemem` are independent choices. Navigation MCPs and generated instruction sections must still work in those combinations.
- Existing user-owned instructions, agent files and MCP entries must retain the installer's current conflict and `--force` behavior. The installer is project-scoped; keep the established personal-settings and exclusion semantics.

## Roles and model policy

| Role | Agent names | Claude default | Codex proposed default | Responsibility |
|---|---|---|---|---|
| Small implementation | `coder-small`, `coder-python-small`, `coder-typescript-small`, `coder-swift-small` | Haiku, high effort where supported | Luna, high effort where supported | Execute bounded briefs, use the language MCP and report uncertainty. |
| Standard implementation | Existing `coder` and `coder-<language>` | Sonnet | Terra, subject to capability validation | Handle normal implementation and more ambiguous or intricate work. |
| Independent reviewer | `code-reviewer` | Sonnet | Terra, subject to capability validation | Review the actual changes and evidence; return actionable findings. |
| Architecture/advice | Existing `architect` | Opus | Sol by default; Astra available for especially demanding work | Resolve architecture and difficult decisions; do not make model choice a claim of equivalence. |
| Utility | Existing `utility` | Haiku | Luna | Bounded checks and mechanical tasks, subject to existing permissions and workflow. |
| Final SDD grade | Existing `code-grader` | Opus | Sol or Astra, subject to client support | Preserve the existing SDD skill's independent final grade and protocol. |

These are proposed configurable defaults, not equivalence, quality, cost or availability guarantees. Confirm exact model IDs, effort settings and availability in each supported client during implementation. Existing standard agents and their defaults must not silently change on upgrade without an explicit migration choice; this includes the current utility, architect and grader behavior. Record any validated default change in the README and upgrade notes. An unavailable configured model must produce a clear warning or client error; do not silently claim a small model was used.

For Cursor, verify current model-selection support before committing to a mapping. If supported reliably, use an explicit configurable model. Otherwise preserve `inherit`, state clearly that the small role controls instructions rather than guaranteeing model size, and let the developer select the actual model. For Codex, add explicit client-specific model mapping rather than passing Claude aliases through the existing converter. Keep overrides per client and role; never assume Claude model aliases exist in Codex. Reasoning effort and model are independent settings and must use values supported by that client/model.

## Delegation and review

1. **Choose the role.** Use small coders for clear, bounded work with concrete acceptance criteria and verifiable outcomes. Larger tasks may be split into independent blocks; length alone is not a reason to use or reject the small tier. Use the standard coder or architect for unresolved behavioral decisions, broad interaction risks, unclear specifications or repeated failures. Honor a developer's explicit model or role choice.
2. **Brief the coder.** Give the goal, relevant paths, allowed scope, behavior and edge cases, acceptance criteria, verification commands, dependencies, integration base and how to report blockers. Preserve the shared language-specific tool instructions and forbid unrelated edits, unapproved dependencies, memory writes and git operations unless the brief authorizes them. Small coders stop and report consequential ambiguities rather than inventing design decisions.
3. **Review independently.** The orchestrator gives `code-reviewer` the original brief, relevant specification, exact diff or isolated worktree and base, test results, and known uncertainties. Ask for correctness, regressions, missing requirements and meaningful verification; do not suggest a verdict. The reviewer is read-only, provides prioritized findings with file/line evidence, and distinguishes verified behavior from assumptions. A review is not a substitute for required tests or the SDD final grade.
4. **Repair and re-review.** Send findings to the same coder when practical. Re-review the resulting diff, especially changes addressing material findings. The orchestrator owns unresolved findings, integration and the final report; after repeated failure or unresolved design questions, escalate to the standard coder or architect. Never silently accept failed review. If an independent reviewer cannot be launched, tell the developer and follow project instructions rather than claiming independent review took place.
5. **Parallelize safely.** Assign independent blocks with clear ownership and dependencies. Use isolated worktrees when supported and appropriate; coordinate overlapping changes and review/integrate each result against its actual base. Avoid destructive worktree operations and follow the existing worktree workflow and user instructions. No blanket requirement to create worktrees for every task. Run relevant checks after integration; report skipped checks and conflicts. A coder does not commit or merge unless its brief authorizes it.

Review applies to small-coder implementation, including fixes to findings. For trivial read-only utility results, the orchestrator can verify them directly; don't spawn a reviewer for every command. Existing SDD approval gates, the architect and grader contracts, and memory ownership remain intact.

## Installation and upgrade design

- Add small coders as an **opt-in** feature. Define an explicit CLI option for both the full install and `coders` command, e.g. `--small-coders`; settle exact spelling during implementation. Default and existing invocations keep their present output and behavior. The option enables the generic small coder when generic agents are installed, and the small specialist for each selected or already-installed language specialist; a standalone `coders` run installs the requested language specialists and their small variants without requiring the generic suite. Avoid silently adding unrequested languages or duplicating MCP servers.
- Include a reviewer when the opt-in small workflow is installed, including standalone language-coder installs, independent of SDD. Ensure `--without agents` and `--without sdd` have clearly documented behavior: language specialists and the minimal reviewer required by an explicit small-coder request may still be installed, while the generic suite and SDD grader remain omitted. Preflight should report the precise files and any conflicts before writing.
- Parameterize generation by role/tier: reuse the current coder body and the exact same language fragment and navigation tool list, with a concise small-coder instruction supplement. Avoid copying long prompts or diverging language tool lists. Distinct names and descriptions must make the two roles discoverable.
- Update the generated language routing section so language choice and model tier are separate: Python changes always go to a Python specialist, with either the standard or small specialist selected according to the workflow and developer choice. Multi-language work may be split by language. Ensure instructions never refer to agents that were not installed.
- Extend role metadata and client conversion deliberately. Preserve model and reasoning fields when copying or converting between clients where appropriate; don't accidentally translate a custom source agent into a different model. Preserve client-specific read-only restrictions where supported and use explicit instructions otherwise; document that instructions alone are not an enforcement boundary. Test the actual generated format and supported client behavior.
- Re-runs, dry runs, `--force`, collision handling, status/list output and personal mode must account for each newly generated agent and the reviewer. Existing customized agents, navigation servers, unrelated settings and unmarked instructions remain protected. Print clear upgrade and unavailable-model messages, and document how to select or override role-to-model mappings without editing generated files where feasible.

## Work packages

1. **Capability and UX spike.** Verify current Claude Code, Codex and Cursor custom-agent schema, supported model selection and effort, read-only capabilities, model availability/failure behavior and installed client versions. Decide exact per-client defaults and an override mechanism; record limitations and source/date. Verify existing behavior for `coders` alone and component exclusions. Resolve whether generated defaults can be portable across accounts before implementing.
2. **Roles and shared templates.** Implement the small coder supplement and read-only reviewer. Extend agent metadata/generation and per-client model configuration. Preserve standard agents by default, and include generic and per-language roles according to explicit installation choices.
3. **Routing and workflow.** Update language routing, model-choice guidance, triggered suggestion behavior, review loop, parallel blocks and integration rules. Ensure standalone coders and no-SDD setups never reference missing roles.
4. **Installer and lifecycle.** Add the opt-in flag to both entry points, preflight, dry-run, listing and upgrade paths. Handle re-runs, conflicts, personal settings and shared navigation servers consistently.
5. **Verification and documentation.** Add focused automated tests and manual client checks below; document examples, mapping/overrides, model availability caveats, and the distinction between independent review and SDD grading. Update the README and relevant change notes.

Work packages 2 and 3 can be developed independently after package 1 if their role contracts are agreed; package 4 integrates them, followed by package 5. Do not implement this proposal until reviewed.

## Acceptance and verification

- A default install and an upgrade without the opt-in preserve existing roles and routing. Opting in creates only the selected language variants, generic variant where applicable, and reviewer; MCP entries are shared, not duplicated.
- Exercise fresh install, upgrade, rerun, dry-run and conflict/`--force` behavior, plus standalone `coders`, `--without agents`, `--without sdd`, `--without agemem`, personal settings and multiple selected clients. Include customized agent/config preservation and partial installs.
- For every client, parse generated agent files and verify role names, navigation instructions, tools, model/effort mapping and reviewer restrictions. Check that unavailable or unsupported model selection is disclosed and that `inherit` is not presented as a guaranteed small model. Validate conversions and existing custom agent round trips.
- Test routing text for standard versus small language coders and for missing optional roles. Verify a developer's explicit choice and session preference take precedence over suggestions; mention of limits or a parallel request triggers an offer rather than a silent switch. No usage telemetry or automatic quota lookup is installed.
- Run the project's test suite and quality checks appropriate to the change. In supported clients, manually smoke-test a bounded change delegated to a small coder, an independent review and a reviewer-requested correction; check actual model identity, navigation MCP access and integration. Report any client/model combinations not tested, including Swift/macOS where unavailable.
- Evaluate on representative tasks with comparable briefs and record review findings, retries, elapsed time and available usage data before asserting savings or broad model equivalence.

## Review decisions

- Confirm the proposed per-client default models and override UX after the capability spike, particularly Terra versus Sol for standard Codex coding and review.
- Confirm the CLI option name and whether enabling small coders should be presented in the interactive installer as well as by explicit flag.
- Confirm the desired escalation threshold after repeated review failures; start with the current workflow's two-attempt rule where applicable.
