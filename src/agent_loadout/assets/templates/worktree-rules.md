## Isolated worktrees

The `worktree` skill (`/worktree create|save|apply|delete`) runs a task in its own git worktree.

- Before starting a task that edits files, run `git status --short` and `git worktree list`. If the checkout has
  uncommitted changes you did not make this session, or another worktree is active, ask the user once whether they
  prefer to run the task in an isolated worktree. Don't ask again for the same task, and don't create one unasked.
- When using `/worktree create`, set up the environment the way this project documents it: read `AGENTS.md`,
  `CLAUDE.md` and `README.md` for the setup steps (dependencies, virtualenv, generated files, `.env` copies) and do them
  in the new worktree without being asked.
- When the task in a worktree is done, tell the user and offer `/worktree save` and then `/worktree apply` (it merges
  into the branch the worktree was created from). After a successful apply, offer `/worktree delete`. Never merge,
  push or delete without the user's yes.
