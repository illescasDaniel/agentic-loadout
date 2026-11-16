#!/usr/bin/env python3
"""Fill memory/sessions/ from the Entire checkpoints stored in this repository's git data.

Companion to memory-1's export_sessions.py, which reads the agent's own transcript files. Run that first; this script
then adds the sessions it did not find: ones the agent no longer keeps on disk, ones recorded on another machine and
fetched with the checkpoints, and clients export_sessions.py does not read. It never rewrites a session file that
already exists (use --update to rewrite). Output matches export_sessions.py: one condensed, redacted Markdown file per
session, prose only (user and assistant text, no tool calls or output), named <first date>-<session id part>.md.

It only reads git data (`git for-each-ref`, `git ls-tree`, `git cat-file`), never fetches, and works without the
Entire CLI. Entire keeps checkpoints either as one ref per checkpoint (refs/entire/checkpoints/<xx>/<id>, the default
since Entire 0.10) or on the branch entire/checkpoints/v1 (older setups); both are read. Only checkpoints that
exist locally are used; sessions with no commit yet have none (see `entire checkpoint list --pending`).

usage: entire_sessions.py [--project DIR] [--out DIR] [--since YYYY-MM-DD] [--max-chars N] [--update] [--dry-run]
Prints one line per file written; add those to sessions/INDEX.md.
Standard library only; Python 3.9+.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SUPPORTED_FORMAT = 1  # `v` of Entire's compact transcript.jsonl; anything else is skipped with a warning

REF_PATTERNS = ("refs/entire/checkpoints/", "refs/heads/entire/checkpoints/v1", "refs/remotes/*/entire/checkpoints/v1")

# Same filter and redaction as export_sessions.py (kept in step by hand): injected context rather than conversation,
# and credential-shaped strings. Entire redacts too, but best effort.
SKIP_PREFIXES = (
    "<command-", "<local-command", "<system-reminder", "<task-notification", "<environment_context",
    "<user_instructions", "<permissions instructions", "<user_shell_command", "# AGENTS.md instructions",
    "Caveat:", "This session is being continued", "[Request interrupted",
)
R = "[REDACTED]"
SECRET_PATTERNS = [
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", R),
    (r"\b(?:sk|pk|rk)-(?:ant-|proj-|live-|test-)?[A-Za-z0-9_\-]{16,}", R),
    (r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}", R),
    (r"\bglpat-[A-Za-z0-9_\-]{20,}|\bhf_[A-Za-z0-9]{20,}|\bnpm_[A-Za-z0-9]{30,}|\bpypi-[A-Za-z0-9_\-]{30,}", R),
    (r"\bxox[abposr]-[A-Za-z0-9\-]{10,}|\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_\-]{30,}", R),
    (r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}", R),
    (r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{20,}", r"\1 " + R),
    (r"(?i)\b([a-z0-9_]*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key)[a-z0-9_]*\s*[:=]\s*[\"']?)"
     r"(?!\[REDACTED)[^\s\"'`,;]{8,}", r"\1" + R),
    (r"(?i)\b([a-z][a-z0-9+.\-]*://[^\s:/@]+:)[^\s@/]{4,}@", r"\1" + R + "@"),
]
SECRET_PATTERNS = [(re.compile(p, re.S), r) for p, r in SECRET_PATTERNS]

# <checkpoint dir>/<session index>/<file>: refs keep the files at the tree root, the branch under <xx>/<rest>/.
ENTRY = re.compile(r"^(?P<ckpt>(?:[^/]+/[^/]+/)?)(?P<n>\d+)/(?P<file>transcript\.jsonl|metadata\.json)$")


def redact(text):
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def clip(text, limit):
    if limit and len(text) > limit:
        return text[:limit] + f"\n[... {len(text) - limit} more characters not exported]"
    return text


def git(project, *args):
    return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True, check=False)


class BlobReader:
    """One long-running `git cat-file --batch`, so thousands of checkpoints cost one process."""

    def __init__(self, project):
        self.proc = subprocess.Popen(["git", "-C", str(project), "cat-file", "--batch"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def read(self, sha):
        self.proc.stdin.write(sha.encode() + b"\n")
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().split()
        if len(header) < 3 or header[1] != b"blob":
            return None
        data = self.proc.stdout.read(int(header[2]))
        self.proc.stdout.read(1)  # the newline git adds after each object
        return data

    def close(self):
        self.proc.stdin.close()
        self.proc.wait()


def find_candidates(project):
    """Yield dicts {ref, ckpt, n, transcript: (sha, size), metadata: sha} for every stored session transcript."""
    refs = git(project, "for-each-ref", "--format=%(refname)", *REF_PATTERNS).stdout.split()
    for ref in refs:
        tree = git(project, "ls-tree", "-r", "-l", "--full-tree", ref).stdout
        found = {}
        for line in tree.splitlines():
            meta, _, path = line.partition("\t")
            match = ENTRY.match(path)
            if not match:
                continue
            _mode, _kind, sha, size = meta.split(None, 3)
            slot = found.setdefault((match["ckpt"], match["n"]), {"ref": ref, "ckpt": match["ckpt"], "n": match["n"]})
            slot["transcript" if match["file"] == "transcript.jsonl" else "metadata"] = (sha, int(size.strip() or 0))
        for slot in found.values():
            if "transcript" in slot and "metadata" in slot:
                yield slot


def checkpoint_label(slot):
    """The checkpoint id, as `entire checkpoint explain` takes it."""
    if slot["ckpt"]:
        return slot["ckpt"].rstrip("/").replace("/", "")
    return slot["ref"].rsplit("/", 1)[-1]


def parse_compact(data, warn):
    """Yield (role, timestamp, agent, text) from Entire's compact transcript (one JSON object per line)."""
    for raw in data.decode("utf-8", errors="replace").splitlines():
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        if event.get("v") != SUPPORTED_FORMAT:
            warn(f"unsupported transcript format v={event.get('v')!r}")
            return
        if event.get("type") not in ("user", "assistant"):
            continue
        text = "\n".join(b["text"] for b in event.get("content") or []
                         if isinstance(b, dict) and isinstance(b.get("text"), str) and b.get("type") in (None, "text")).strip()
        if text:
            yield event["type"], event.get("ts", ""), event.get("agent", ""), text


def session_name(agent, session_id, first):
    # export_sessions.py names Claude Code files by the first 8 characters of the id and Codex files by the last 8.
    sid = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", session_id)
    sid = sid[-8:] if agent == "codex" else sid[:8]
    return f"{first[:10] or 'undated'}-{sid}.md", sid


def render(slot, session_id, data, max_chars, warn):
    turns, agent = [], ""
    for role, stamp, agent_name, text in parse_compact(data, warn):
        agent = agent or agent_name
        if text.startswith(SKIP_PREFIXES):
            continue
        turns.append((role, stamp, redact(clip(text, max_chars))))
    if not turns or not any(r == "user" for r, _, _ in turns):
        return None, None, None
    first, last = turns[0][1], turns[-1][1]
    name, sid = session_name(agent, session_id, first)
    body = [f"# Session {session_id} ({agent or 'unknown'}, from Entire checkpoint {checkpoint_label(slot)})\n\n"
            f"{first[:16].replace('T', ' ')} to {last[:16].replace('T', ' ')} UTC, {len(turns)} messages. "
            "Tool calls and outputs are not exported.\n"]
    body += [f"### {role} {stamp[:16].replace('T', ' ')}\n{text}\n" for role, stamp, text in turns]
    return name, sid, "\n".join(body)


def ensure_gitignore(out):
    """A fresh archive is git-ignored like memory-1's template; an archive the user chose to share is left alone."""
    if (out / ".gitignore").exists() or any(p.name != "INDEX.md" for p in out.glob("*.md")):
        return
    out.mkdir(parents=True, exist_ok=True)
    (out / ".gitignore").write_text("*\n!.gitignore\n!INDEX.md\n", encoding="utf-8")


def export(project, out, since=None, max_chars=6000, update=False, dry_run=False, log=print, warn=None):
    warn = warn or (lambda m: print(f"warning: {m}", file=sys.stderr))
    candidates = list(find_candidates(project))
    if not candidates:
        return None
    reader = BlobReader(project)
    try:
        # A session can have several checkpoints; each transcript.jsonl holds the whole session up to that commit,
        # so the biggest one is the most complete.
        best = {}
        for slot in candidates:
            try:
                meta = json.loads(reader.read(slot["metadata"][0]) or b"{}")
            except ValueError:
                continue
            session_id = meta.get("session_id")
            if not session_id:
                warn(f"checkpoint {checkpoint_label(slot)} has no session id; skipped")
                continue
            if session_id not in best or slot["transcript"][1] > best[session_id]["transcript"][1]:
                best[session_id] = slot
        counts = {"new": 0, "updated": 0, "present": 0, "skipped": 0}
        for session_id, slot in sorted(best.items()):
            data = reader.read(slot["transcript"][0])
            name, sid, text = render(slot, session_id, data or b"", max_chars, lambda m: warn(f"{checkpoint_label(slot)}: {m}"))
            if name is None or (since and name[:10] < since):
                counts["skipped"] += 1
                continue
            target = out / name
            existing = target if target.exists() else next(iter(out.glob(f"*-{sid}.md")), None) if out.is_dir() else None
            if existing is not None and not update:
                counts["present"] += 1
                continue
            state = "new" if existing is None else "updated"
            if existing is not None and existing.read_text(encoding="utf-8") == text:
                counts["present"] += 1
                continue
            counts[state] += 1
            if not dry_run:
                ensure_gitignore(out)
                out.mkdir(parents=True, exist_ok=True)
                (existing or target).write_text(text, encoding="utf-8")
            log(f"{state:8} {existing or target}  ({text.splitlines()[0].split('(')[-1].split(',')[0]}, {len(text) // 1024} KB)")
    finally:
        reader.close()
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project", default=".", help="repository whose checkpoints to read (default: .)")
    ap.add_argument("--out", default="memory/sessions", help="output folder (default: memory/sessions)")
    ap.add_argument("--since", help="only sessions whose first message is on or after this date (YYYY-MM-DD)")
    ap.add_argument("--max-chars", type=int, default=6000, help="cap per message, 0 for none (default: 6000)")
    ap.add_argument("--update", action="store_true", help="rewrite session files that already exist (default: keep them)")
    ap.add_argument("--dry-run", action="store_true", help="list what would be written")
    args = ap.parse_args(argv)
    project = Path(args.project).resolve()
    if git(project, "rev-parse", "--git-dir").returncode != 0:
        print(f"{project} is not a git repository", file=sys.stderr)
        return 1
    counts = export(project, Path(args.out), args.since, args.max_chars, args.update, args.dry_run)
    if counts is None:
        print(f"no Entire checkpoints found in {project} (none committed yet, or none fetched)", file=sys.stderr)
        return 1
    print(", ".join(f"{v} {k}" for k, v in counts.items()), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
