## Phase Gate Protocol (Spec-Driven Development)

Use the `sdd-html-feature` skill for features and user-facing changes. Keep the design, spec, architecture, build, verification and approval record together in `sdd/<feature>.html` (or the project's established convention).

- Stop for **separate design, spec and architecture approvals in chat**; resume at the first unapproved gate. An artifact, plan or page interaction is not approval.
- After architecture approval, write scenario-based tests and implement. QA and an independent grade follow automatically unless the user opts out at the architecture gate; follow the skill's budgets and reporting rules.
- Tiny fixes without new behavior do not require SDD unless project rules say otherwise. If an approved requirement changes, return to the affected gate.
