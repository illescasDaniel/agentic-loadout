#!/usr/bin/env python3
"""Export a project's agent sessions (Claude Code, Codex) to condensed, redacted Markdown.

Keeps only what the user and the assistant said to each other: no tool calls, tool output, reasoning or injected
instructions. One file per session, named <first date>-<session id prefix>.md. A file is rewritten only when its
session has grown, so the script is safe to run at the end of every session.

usage: export_sessions.py [--project DIR] [--out DIR] [--since YYYY-MM-DD] [--max-chars N] [--dry-run]
       export_sessions.py --claude-dir DIR ...   (moved project, or worktrees outside it; repeatable)
Prints one line per new or updated file; add those to sessions/INDEX.md.
Standard library only; Python 3.9+.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

HOME = Path.home()
CLAUDE_ROOT = Path(os.environ.get("CLAUDE_CONFIG_DIR", HOME / ".claude")) / "projects"
CODEX_ROOT = Path(os.environ.get("CODEX_HOME", HOME / ".codex")) / "sessions"

# Injected context rather than conversation.
SKIP_PREFIXES = (
    "<command-", "<local-command", "<system-reminder", "<task-notification", "<environment_context",
    "<user_instructions", "<permissions instructions", "<user_shell_command", "# AGENTS.md instructions",
    "Caveat:", "This session is being continued", "[Request interrupted",
)

# Credential-shaped strings. Conservative: a false positive costs a few characters of context.
R = "[REDACTED]"
SECRET_PATTERNS = [  # (pattern, replacement)
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", R),
    (r"\b(?:sk|pk|rk)-(?:ant-|proj-|live-|test-)?[A-Za-z0-9_\-]{16,}", R),
    (r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}", R),
    (r"\bglpat-[A-Za-z0-9_\-]{20,}|\bhf_[A-Za-z0-9]{20,}|\bnpm_[A-Za-z0-9]{30,}|\bpypi-[A-Za-z0-9_\-]{30,}", R),
    (r"\bxox[abposr]-[A-Za-z0-9\-]{10,}|\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_\-]{30,}", R),
    (r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}", R),                 # JWT
    (r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{20,}", r"\1 " + R),
    (r"(?i)\b([a-z0-9_]*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key)[a-z0-9_]*\s*[:=]\s*[\"']?)"
     r"(?!\[REDACTED)[^\s\"'`,;]{8,}", r"\1" + R),
    (r"(?i)\b([a-z][a-z0-9+.\-]*://[^\s:/@]+:)[^\s@/]{4,}@", r"\1" + R + "@"),             # user:pass@host
]
SECRET_PATTERNS = [(re.compile(p, re.S), r) for p, r in SECRET_PATTERNS]


def redact(text):
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def clip(text, limit):
    if limit and len(text) > limit:
        return text[:limit] + f"\n[... {len(text) - limit} more characters not exported]"
    return text


def claude_text(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


def read_claude(path):
    """Yield (role, timestamp, text) from a Claude Code transcript; drops subagent, meta and tool turns."""
    with path.open(encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            try:
                event = json.loads(raw)
            except ValueError:
                continue
            if event.get("type") not in ("user", "assistant") or event.get("isSidechain") or event.get("isMeta"):
                continue
            text = claude_text((event.get("message") or {}).get("content")).strip()
            if text:
                yield event["type"], event.get("timestamp", ""), text


def codex_meta(path):
    with path.open(encoding="utf-8", errors="replace") as fh:
        for _, raw in zip(range(5), fh):
            try:
                event = json.loads(raw)
            except ValueError:
                continue
            if event.get("type") == "session_meta":
                return event.get("payload") or {}
    return {}


def read_codex(path):
    """Yield (role, timestamp, text) from a Codex rollout file; drops developer, reasoning and tool items."""
    with path.open(encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            try:
                event = json.loads(raw)
            except ValueError:
                continue
            item = event.get("payload") or {}
            if event.get("type") != "response_item" or item.get("type") != "message":
                continue
            role = item.get("role")
            if role not in ("user", "assistant"):
                continue
            text = "\n".join(b.get("text", "") for b in item.get("content") or []
                             if isinstance(b, dict) and b.get("type") in ("input_text", "output_text")).strip()
            if text:
                yield role, event.get("timestamp", ""), text


def claude_cwd(path):
    with path.open(encoding="utf-8", errors="replace") as fh:
        for _, raw in zip(range(50), fh):
            try:
                cwd = json.loads(raw).get("cwd")
            except (ValueError, AttributeError):
                continue
            if cwd:
                return cwd
    return None


def inside(cwd, project):
    return bool(cwd) and (Path(cwd) == project or project in Path(cwd).parents)


def find_sessions(project, claude_dirs):
    found = []
    if claude_dirs:
        found += [("claude", p, read_claude) for d in claude_dirs for p in sorted(Path(d).glob("*.jsonl"))]
    elif CLAUDE_ROOT.is_dir():
        # Claude Code keeps a project's sessions under its absolute path with every non-alphanumeric character as "-";
        # worktrees inside the project get sibling folders with a longer name. Confirm each by its recorded cwd.
        enc = re.sub(r"[^A-Za-z0-9]", "-", str(project))
        for cdir in sorted(CLAUDE_ROOT.iterdir()):
            if cdir.name == enc or cdir.name.startswith(enc + "-"):
                found += [("claude", p, read_claude) for p in sorted(cdir.glob("*.jsonl"))
                          if cdir.name == enc or inside(claude_cwd(p), project)]
    if CODEX_ROOT.is_dir():
        for path in sorted(CODEX_ROOT.rglob("*.jsonl")):
            if inside(codex_meta(path).get("cwd"), project):
                found.append(("codex", path, read_codex))
    return found


def render(client, path, reader, max_chars):
    turns = []
    for role, stamp, text in reader(path):
        if text.startswith(SKIP_PREFIXES):
            continue
        turns.append((role, stamp, redact(clip(text, max_chars))))
    if not turns or not any(r == "user" for r, _, _ in turns):
        return None, None
    first, last = turns[0][1], turns[-1][1]
    # Claude Code ids are random UUIDs; Codex ids are time-ordered (UUIDv7), so take their random tail instead.
    sid = path.stem[-8:] if client == "codex" else path.stem[:8]
    name = f"{first[:10] or 'undated'}-{sid}.md"
    body = [f"# Session {path.stem} ({client})\n\n{first[:16].replace('T', ' ')} to {last[:16].replace('T', ' ')} UTC, "
            f"{len(turns)} messages. Tool calls and outputs are not exported.\n"]
    body += [f"### {role} {stamp[:16].replace('T', ' ')}\n{text}\n" for role, stamp, text in turns]
    return name, "\n".join(body)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project", default=".", help="project root whose sessions to export (default: .)")
    ap.add_argument("--out", default="memory/sessions", help="output folder (default: memory/sessions)")
    ap.add_argument("--claude-dir", action="append", help="Claude Code transcript folder to use instead of the "
                    "default lookup (repeatable; for moved projects or worktrees outside the project)")
    ap.add_argument("--since", help="only sessions whose first message is on or after this date (YYYY-MM-DD)")
    ap.add_argument("--max-chars", type=int, default=6000, help="cap per message, 0 for none (default: 6000)")
    ap.add_argument("--dry-run", action="store_true", help="list what would be written")
    args = ap.parse_args(argv)

    project = Path(args.project).resolve()
    out = Path(args.out)
    sessions = find_sessions(project, args.claude_dir)
    if not sessions:
        print(f"no Claude Code or Codex sessions found for {project}", file=sys.stderr)
        return 1
    rendered = {}
    for client, path, reader in sessions:
        name, text = render(client, path, reader, args.max_chars)
        # A resumed or forked session can appear in two folders under one id: keep the longer copy.
        if name and not (args.since and name[:10] < args.since) and len(text) > len(rendered.get(name, ("", ""))[1]):
            rendered[name] = (client, text)
    counts = {"new": 0, "updated": 0, "unchanged": 0}
    for name, (client, text) in sorted(rendered.items()):
        target = out / name
        old = target.read_text(encoding="utf-8") if target.exists() else None
        state = "new" if old is None else "unchanged" if old == text else "updated"
        counts[state] += 1
        if state == "unchanged":
            continue
        if not args.dry_run:
            out.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        print(f"{state:8} {target}  ({client}, {len(text) // 1024} KB)")
    print(", ".join(f"{v} {k}" for k, v in counts.items()), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
