- This project's `memory/` still holds files from the previous memory system (agemem): `activeContext.md`,
  `progress.md`, `decisions.md`, `archive.md` and the `.agemem/` folder. They are not memory-1 files: do not read them
  at session start (`NOW.md` is the status file). When the user
  agrees, migrate them (current state to `NOW.md` and `LATER.md`, each dated decision to a note under `memory/notes/`,
  keeping its date and why), then delete the old files and `.agemem/` and re-run agentic-loadout to drop this item.
