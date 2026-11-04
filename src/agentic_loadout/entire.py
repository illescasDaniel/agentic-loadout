"""Optional integration with an already installed Entire CLI."""
from __future__ import annotations

import json

from . import git_state
from .files import Ctx, read_json, write_json
from .options import Options
from .runners import Executor, run

AGENTS = {"claude": "claude-code", "codex": "codex", "cursor": "cursor"}


def install(ctx: Ctx, opts: Options, executor: Executor, present: bool) -> bool:
    if not opts.wants("entire"):
        return False
    if opts.no_hooks:
        ctx.note("Entire was skipped because --no-hooks was selected.")
        return False
    if not present:
        if opts.entire_upload_sessions:
            raise SystemExit("error: --entire-upload-sessions requires the Entire CLI on PATH")
        ctx.note("Entire CLI was not found; install it and re-run to enable checkpoint capture (or use --without entire).")
        return False
    if not git_state.is_git_repo(opts.project):
        if opts.entire_upload_sessions:
            raise SystemExit("error: --entire-upload-sessions requires a Git repository")
        ctx.note("Entire requires a Git repository; it was skipped without initializing one.")
        return False

    for path in (opts.project / ".entire/settings.json", opts.project / ".entire/settings.local.json"):
        if path.exists():
            existing, _ = read_json(path)
            if not isinstance(existing.get("strategy_options", {}), dict):
                raise SystemExit(f"error: {path}: strategy_options must be an object")

    agents = [AGENTS[t] for t in opts.selected()]
    scope = "--local" if opts.personal_settings else "--project"
    run(["entire", "enable", "--agent", agents[0], scope, "--skip-push-sessions", "--telemetry=false", "--no-init-repo"],
        opts, executor, ctx.lines.append)
    for agent in agents[1:]:
        run(["entire", "agent", "add", agent], opts, executor, ctx.lines.append)

    # A pre-existing local override has precedence over project settings.
    local = opts.project / ".entire/settings.local.json"
    if not opts.personal_settings and local.exists():
        run(["entire", "configure", "--local", "--skip-push-sessions"], opts, executor, ctx.lines.append)
    if opts.entire_upload_sessions:
        target = local if opts.personal_settings else opts.project / ".entire/settings.json"
        for path in dict.fromkeys([target, *([local] if local.exists() else [])]):
            data, indent = read_json(path, ctx)
            options = data.setdefault("strategy_options", {})
            if not isinstance(options, dict):
                raise SystemExit(f"error: {path}: strategy_options must be an object")
            options["push_sessions"] = True
            write_json(ctx, path, data, indent, ["explicitly enable checkpoint uploads"])
        ctx.warn("Entire checkpoint uploads are enabled; session transcripts may be visible to readers of the destination.")
    else:
        ctx.note("Entire checkpoint uploads are disabled by default; inspect `entire status` before pushing.")
    ctx.lines.append("             writes .entire/, Git hooks and selected client hooks")
    return True


def verify(ctx: Ctx, opts: Options, executor: Executor) -> None:
    if opts.dry_run:
        return
    result = executor(["entire", "status", "--json"], opts.project, {})
    try:
        status = json.loads(result.stdout) if result.returncode == 0 else {}
    except (ValueError, TypeError):
        status = {}
    if not status.get("enabled"):
        raise SystemExit("error: Entire did not report an enabled configuration; inspect `entire status`.")
    if not opts.entire_upload_sessions and status.get("checkpoint_push_disabled") is not True:
        raise SystemExit("error: Entire did not confirm checkpoint uploads are disabled; inspect `entire status` before pushing.")
    if opts.entire_upload_sessions and status.get("checkpoint_push_disabled") is True:
        raise SystemExit("error: Entire reports checkpoint uploads disabled despite the explicit request; inspect its settings.")
