## Project docs (docs-1)

Project docs are in `docs/`; start at `docs/INDEX.md` (generated, one line per doc). Cite docs by ID (`DOC-012`). Code
at HEAD wins over a doc. Before changing code, find the docs that cover it
(`python3 {{SKILL_DIR}}/docs-1/scripts/docs_index.py covers <file>`) and update them in the same change, then run
`docs_index.py write` and `check`. Full protocol: the `docs-1` skill.

- If `docs/INDEX.md` does not exist yet, ask the user before setting docs-1 up; do not create it on your own. The skill
  adds frontmatter to the existing docs and generates the index.
- Docs say how the system works now; memory (if the project has it) keeps why it is that way, what changed, preferences
  and status. Do not copy one into the other.
