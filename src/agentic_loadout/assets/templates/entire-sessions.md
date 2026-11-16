
The memory-1 session archive can also be filled from checkpoints. After `export_sessions.py`, run
`python3 .agents/scripts/entire_sessions.py --project . --out memory/sessions`: it adds only sessions that are not
exported yet (ones the agent no longer keeps, ones from another machine, other clients), never rewrites a session file,
and only sees sessions that have a checkpoint, that is, a commit. Add the new files to `memory/sessions/INDEX.md`. If a
note's `source` is a checkpoint ID, read it with `entire checkpoint explain <id> --full`. When a checkpoint explains a
decision that no note records, verify it against the current code and write a memory-1 note whose `source` is that
checkpoint ID.

