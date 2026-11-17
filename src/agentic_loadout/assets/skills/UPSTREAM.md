# Upstream skills

agentic-loadout ships adapted copies of two Agent Skills. Each copy is made from the skill's own repository at the commit below; those repositories are never changed from here. Do not edit these folders by hand: `scripts/sync_skills.py` rebuilds them.

| Skill | Upstream repository | Commit |
|---|---|---|
| `memory-1` | https://github.com/illescasDaniel/memory-1-skill | `a141c5aed3fb6f4f1b955083a915fdffd0d71833` |
| `docs-1` | https://github.com/illescasDaniel/docs-1-skill | `13b2e5390db0bd46471e32e913e88d9c8b0bab86` |

## What differs from upstream

Every difference is an insertion between an `agentic-loadout:begin NAME` and an `agentic-loadout:end NAME` marker line (`#` comments in Python, HTML comments in Markdown). Removing the marked blocks, and the blank lines right after each end marker, gives the upstream file byte for byte. Nothing else is changed.

- `memory-1/SKILL.md`, block `entire-note`: one paragraph about the opt-in `--entire` flag, in the Session archive section
- `memory-1/scripts/export_sessions.py`, block `entire-code`: the opt-in Entire pass (functions that read checkpoints from git data, same output format and redaction)
- `memory-1/scripts/export_sessions.py`, block `entire-flag`: the `--entire` flag
- `memory-1/scripts/export_sessions.py`, block `entire-only`: with `--entire` and no native sessions, run only the Entire pass instead of failing
- `memory-1/scripts/export_sessions.py`, block `entire-run`: with `--entire`, run the Entire pass after the native export

## Manifest

`sha256` is the hash of the upstream file (without the marked blocks).

| File | sha256 | Differs |
|---|---|---|
| `memory-1/SKILL.md` | `7fe13f51c547eb3538b08c51116fe867f01bff0653663ac85f48757dd65db22c` | yes |
| `memory-1/scripts/export_sessions.py` | `477ce237882de4642f17c9fecf020cfa024598559000ba77aff436c391b335f8` | yes |
| `memory-1/scripts/memory_check.py` | `4e617dbb339f4a67b9d0cb9c9db70b2e61ff51cb0c6580db9ac59f41f0f67522` | no |
| `memory-1/templates/.gitignore` | `36cb3e2d2fdb2bad956337d5649c75b20cabb3c505cb728fefcbe3cb8b5dee6c` | no |
| `memory-1/templates/LATER.md` | `b215b01ed2f7434b1287a2ebfc8dd7d69b89a97d0d464b7aa1ba7d0d65c1a676` | no |
| `memory-1/templates/MEMORY.md` | `71375e4b3012cb78b1854265f9612752e8ca91e8bb59917b5642d4bddf0d9ad4` | no |
| `memory-1/templates/NOW.md` | `33a49515e4993add3398dd761a2757678bed98e76de0bfa830ca7179ca72145f` | no |
| `memory-1/templates/notes/_example.md` | `dfef86ac833702c9889b4fc3ec5200ac99538abb9421a9639d2e23ea873cb54e` | no |
| `memory-1/templates/sessions/INDEX.md` | `41bcbc17607e29348915c7eec91520310416437de7ed1016564e8b9586be0c4d` | no |
| `docs-1/SKILL.md` | `501ca6711b0f5da780731db5f76c8d7da1872b5c658548c364d268b482adb428` | no |
| `docs-1/scripts/docs_index.py` | `73a6fd6d9bfb7cfe91a1962dd139e714142f5127b33da150301d6fba2b359930` | no |
| `docs-1/templates/doc.md` | `e184b65699e4c8044d077bd6b6ff6d4b65eadf22556b7db76bd4b520bd965829` | no |

## Refresh

```bash
python3 scripts/sync_skills.py --memory-1 ../memory-1-skill --memory-1-commit <commit> \
                               --docs-1 ../docs-1-skill --docs-1-commit <commit>
```

Add `--check` to verify without writing. The script fails when an overlay anchor line no longer exists upstream; fix `scripts/overlays/overlays.toml` and run it again.
