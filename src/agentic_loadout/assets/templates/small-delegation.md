# Delegating to small coders

Choose a small coder for bounded work with a clear brief, acceptance criteria and verifiable outcomes. Use the matching language specialist for code covered by a language coder; choose its standard counterpart for ambiguous or high-risk work. Honor the developer's explicit choice. If the developer mentions usage limits or asks for multiple parallel subagents, suggest small coders when appropriate, explain the tradeoff and follow their answer. Remember their preference during the session; don't repeatedly ask. Do not infer model quotas or silently switch models.

Give each coder the goal, files, scope, behavior, acceptance criteria, checks, integration base and dependencies. Split independent blocks, coordinate overlapping files and use isolated worktrees when appropriate under the project's worktree rules. Coders must report uncertainties and not make consequential design decisions on their own.

Independently review every small-coder implementation using `code-reviewer`. Provide the original brief, relevant specifications, actual diff and base, verification results and known gaps; do not suggest a verdict. Send findings back to the coder and re-review material changes. The orchestrator owns integration, unresolved findings and verification. If a reviewer cannot be launched, disclose that; never claim independent review occurred. Escalate repeated failures or unresolved design questions. This review complements any existing final SDD grade.

Model defaults depend on the client and account. Cursor may inherit or fall back to another model; verify the actual model in the client. Edit the generated agent file to change a model; reruns preserve differing files unless forced.
