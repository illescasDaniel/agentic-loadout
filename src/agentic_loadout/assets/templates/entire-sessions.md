
The memory-1 session archive also takes checkpoints: the `--entire` flag of the export command in the memory section adds
only the sessions that are not exported yet (ones the agent no longer keeps, ones from another machine, other clients).
It reads git data only, never rewrites a session file, and only sees sessions that have a checkpoint, that is, a commit.
Add the new files to `memory/sessions/INDEX.md`. If a note's `source` is a checkpoint ID, read it with
`entire checkpoint explain <id> --full`. When a checkpoint explains a decision that no note records, verify it against the
current code and write a memory-1 note whose `source` is that checkpoint ID.
