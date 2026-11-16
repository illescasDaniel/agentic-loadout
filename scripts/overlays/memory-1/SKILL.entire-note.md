Add `--entire` to also read [Entire](https://github.com/entireio/cli) checkpoints, but only when the user asks for it
(the project's rules say when it is enabled). Checkpoints are git data (`refs/entire/checkpoints/`), not files, so
this pass adds the sessions the agent's own transcript files no longer hold: ones rotated away, recorded on another
machine, or from other clients. It reads git only, never rewrites a session file that already exists, and redacts the
same way. Entire needs a commit before a session has a checkpoint.
