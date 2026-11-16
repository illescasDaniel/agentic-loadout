"""The memory-1 and docs-1 skills. agentic-loadout ships its own adapted copies (assets/skills, see UPSTREAM.md there) and
copies them into the project's skills folder of every selected client; nothing is downloaded.

A project set up by an earlier state of this package has the same skills installed by `npx skills`, with an entry in
`skills-lock.json`. Those copies are replaced (so there is one copy, never two) and their lock entries are removed.
"""

from __future__ import annotations

from .agents import ASSETS
from .agents import SKILL_DIRS as ALL_SKILL_FOLDERS
from .files import Ctx, read_json, write_bytes, write_json
from .options import Options

SKILL_DIRS = {"claude": ".claude/skills", "cursor": ".agents/skills", "codex": ".agents/skills"}
LOCK = "skills-lock.json"


def vendored_files(name: str) -> dict[str, bytes]:
    root = ASSETS / "skills" / name
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


def folders(opts: Options) -> list[str]:
    """The distinct project skill folders of the selected clients (Cursor and Codex share one)."""
    return list(dict.fromkeys(SKILL_DIRS[t] for t in opts.selected()))


def _locked(ctx: Ctx) -> dict:
    path = ctx.project / LOCK
    if not ctx.exists(path):
        return {}
    skills = read_json(path, ctx)[0].get("skills")
    return skills if isinstance(skills, dict) else {}


def install_skill(ctx: Ctx, opts: Options, name: str) -> bool:
    """Copy the skill into each selected client's folder. Returns True when an `npx skills` copy was replaced everywhere
    it existed, so its lock entry can go (see `drop_lock_entries`)."""
    managed = name in _locked(ctx)
    files = vendored_files(name)
    for folder in folders(opts):
        dest = ctx.project / folder / name
        replaced = managed and dest.is_dir()
        if replaced:
            ctx.remove_tree(dest)
        counts: dict[str, int] = {}
        for rel, data in files.items():
            status = write_bytes(ctx, dest / rel, data, log=False)
            counts[status] = counts.get(status, 0) + 1
        summary = ", ".join(f"{n} {s}" for s, n in counts.items())
        shown = dest.relative_to(ctx.project).as_posix() + "/"
        if not replaced and set(counts) == {"unchanged"}:
            ctx.log("unchanged", shown, f"({len(files)} files)")
        else:
            status = ("would replace" if ctx.dry_run else "replaced") if replaced else ("would install" if ctx.dry_run else "installed")
            ctx.log(status, shown, f"({summary})" + (", the copy `npx skills` had installed" if replaced else ""))
        if "skipped" in counts:
            ctx.warn(f"{folder}/{name}: some files differ from the shipped copy and were kept (use --force to overwrite them).")
    if not managed:
        return False
    leftovers = [f for f in ALL_SKILL_FOLDERS if f not in folders(opts) and (ctx.project / f / name / "SKILL.md").is_file()]
    if leftovers:
        ctx.warn(f"`npx skills` also installed {name} in {', '.join(f'{f}/{name}' for f in leftovers)}; that client is not "
                 "selected, so its old copy was left and the lock entry kept. Re-run with that client to replace it.")
        return False
    return True


def drop_lock_entries(ctx: Ctx, names: list[str]) -> None:
    """Remove the `npx skills` bookkeeping for skills this package now ships itself. Call it after any `npx skills`
    command of the same run, so the latest lock file is edited."""
    path = ctx.project / LOCK
    if not names or not ctx.exists(path):
        return
    data, indent = read_json(path, ctx)
    skills = data.get("skills")
    if not isinstance(skills, dict):
        return
    gone = [n for n in names if n in skills]
    if not gone:
        return
    for name in gone:
        del skills[name]
    if not skills and set(data) <= {"version", "skills"}:
        ctx.remove_tree(path)
        ctx.log("would remove" if ctx.dry_run else "removed", LOCK, f"(it only listed {', '.join(gone)})")
        return
    write_json(ctx, path, data, indent, [f"removed {', '.join(gone)}"])


def remove_old_entire_script(ctx: Ctx) -> None:
    """Loadout 0.6.x and the first state of this branch installed `.agents/scripts/entire_sessions.py`; the Entire reading
    is now part of the memory skill's export script (`--entire`)."""
    path = ctx.project / ".agents/scripts/entire_sessions.py"
    if not ctx.exists(path):
        return
    if b"Fill memory/sessions/ from the Entire checkpoints" not in ctx.read(path)[:400]:
        ctx.warn(".agents/scripts/entire_sessions.py is not the script agentic-loadout installed, so it was left alone.")
        return
    ctx.remove_tree(path)
    ctx.log("would remove" if ctx.dry_run else "removed", path, "(superseded by `export_sessions.py --entire`)")

