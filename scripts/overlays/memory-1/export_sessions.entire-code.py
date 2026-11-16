# Entire checkpoints (--entire): this pass adds the sessions that only Entire has, such as ones the agent no longer
# keeps on disk, ones recorded on another machine, and clients the readers above do not know. It only reads git data
# (`git for-each-ref`, `git ls-tree`, `git cat-file`), needs no Entire CLI, never fetches, and never rewrites a session
# file that already exists. It uses the same redaction and the same output format as the readers above.
# Entire keeps a checkpoint either as one ref (refs/entire/checkpoints/<xx>/<id>, the default since Entire 0.10.0) or on
# the branch entire/checkpoints/v1 (older setups). Entire does not document that layout; an unknown one is skipped with
# a warning rather than guessed at.
ENTIRE_FORMAT = 1  # `v` of Entire's compact transcript.jsonl
ENTIRE_REFS = ("refs/entire/checkpoints/", "refs/heads/entire/checkpoints/v1", "refs/remotes/*/entire/checkpoints/v1")
# <checkpoint dir>/<session index>/<file>: refs keep the files at the tree root, the branch under <xx>/<rest>/.
ENTIRE_ENTRY = re.compile(r"^(?P<ckpt>(?:[^/]+/[^/]+/)?)(?P<n>\d+)/(?P<file>transcript\.jsonl|metadata\.json)$")


def entire_git(project, *args):
    try:
        return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True, check=False)
    except OSError as exc:
        return subprocess.CompletedProcess(args, 127, "", str(exc))


class EntireBlobs:
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


def entire_candidates(project):
    """(refs, slots): every Entire ref, and a dict {ref, ckpt, n, transcript: (sha, size), metadata: sha} per stored session."""
    refs = entire_git(project, "for-each-ref", "--format=%(refname)", *ENTIRE_REFS).stdout.split()
    slots = []
    for ref in refs:
        found = {}
        for line in entire_git(project, "ls-tree", "-r", "-l", "--full-tree", ref).stdout.splitlines():
            meta, _, path = line.partition("\t")
            match = ENTIRE_ENTRY.match(path)
            if not match:
                continue
            _mode, _kind, sha, size = meta.split(None, 3)
            slot = found.setdefault((match["ckpt"], match["n"]), {"ref": ref, "ckpt": match["ckpt"], "n": match["n"]})
            slot["transcript" if match["file"] == "transcript.jsonl" else "metadata"] = (sha, int(size.strip() or 0))
        slots += [s for s in found.values() if "transcript" in s and "metadata" in s]
    return refs, slots


def entire_label(slot):
    """The checkpoint id, as `entire checkpoint explain` takes it."""
    if slot["ckpt"]:
        return slot["ckpt"].rstrip("/").replace("/", "")
    return slot["ref"].rsplit("/", 1)[-1]


def read_entire(data, warn):
    """Yield (role, timestamp, agent, text) from Entire's compact transcript (one JSON object per line)."""
    for raw in data.decode("utf-8", errors="replace").splitlines():
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        if event.get("v") != ENTIRE_FORMAT:
            warn(f"unsupported transcript format v={event.get('v')!r}")
            return
        if event.get("type") not in ("user", "assistant"):
            continue
        text = "\n".join(b["text"] for b in event.get("content") or []
                         if isinstance(b, dict) and isinstance(b.get("text"), str) and b.get("type") in (None, "text")).strip()
        if text:
            yield event["type"], event.get("ts", ""), event.get("agent", ""), text


def render_entire(slot, session_id, data, max_chars, warn):
    turns, agent = [], ""
    for role, stamp, agent_name, text in read_entire(data, warn):
        agent = agent or agent_name
        if text.startswith(SKIP_PREFIXES):
            continue
        turns.append((role, stamp, redact(clip(text, max_chars))))
    if not turns or not any(r == "user" for r, _, _ in turns):
        return None, None, None
    first, last = turns[0][1], turns[-1][1]
    # Same file names as the readers above: Claude Code ids by their first 8 characters, Codex ids by their last 8.
    sid = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", session_id)
    sid = sid[-8:] if agent == "codex" else sid[:8]
    name = f"{first[:10] or 'undated'}-{sid}.md"
    body = [f"# Session {session_id} ({agent or 'unknown'}, from Entire checkpoint {entire_label(slot)})\n\n"
            f"{first[:16].replace('T', ' ')} to {last[:16].replace('T', ' ')} UTC, {len(turns)} messages. "
            "Tool calls and outputs are not exported.\n"]
    body += [f"### {role} {stamp[:16].replace('T', ' ')}\n{text}\n" for role, stamp, text in turns]
    return name, sid, "\n".join(body)


def entire_gitignore(out):
    """A fresh archive is git-ignored like the template; an archive that was shared on purpose is left alone."""
    if (out / ".gitignore").exists() or any(p.name != "INDEX.md" for p in out.glob("*.md")):
        return
    out.mkdir(parents=True, exist_ok=True)
    (out / ".gitignore").write_text("*\n!.gitignore\n!INDEX.md\n", encoding="utf-8")


def export_entire(project, out, since=None, max_chars=6000, dry_run=False, log=print, warn=None, planned=()):
    """Write the sessions only Entire has. Returns the counts, or None when the repository has no Entire refs."""
    warn = warn or (lambda m: print(f"warning: {m}", file=sys.stderr))
    refs, slots = entire_candidates(project)
    if not refs:
        return None
    counts = {"new": 0, "present": 0, "skipped": 0}
    if not slots:
        warn(f"found {len(refs)} Entire ref(s) but none has the expected layout (<n>/transcript.jsonl next to "
             "<n>/metadata.json); Entire may have changed how it stores checkpoints, so nothing was exported")
        return counts
    reader = EntireBlobs(project)
    try:
        # A session can have several checkpoints; each transcript.jsonl holds the whole session up to that commit,
        # so the biggest one is the most complete.
        best = {}
        for slot in slots:
            try:
                meta = json.loads(reader.read(slot["metadata"][0]) or b"{}")
            except ValueError:
                continue
            session_id = meta.get("session_id")
            if not session_id:
                warn(f"checkpoint {entire_label(slot)} has no session id; skipped")
                continue
            if session_id not in best or slot["transcript"][1] > best[session_id]["transcript"][1]:
                best[session_id] = slot
        for session_id, slot in sorted(best.items()):
            data = reader.read(slot["transcript"][0])
            label = entire_label(slot)
            name, sid, text = render_entire(slot, session_id, data or b"", max_chars, lambda m: warn(f"{label}: {m}"))
            if name is None or (since and name[:10] < since):
                counts["skipped"] += 1
                continue
            # The readers above may have written this session already, possibly under another date: keep that file.
            # `planned`: names the native pass just rendered; in a dry run they are not on disk yet.
            if ((out / name).exists() or (out.is_dir() and next(iter(out.glob(f"*-{sid}.md")), None) is not None)
                    or any(p == name or p.endswith(f"-{sid}.md") for p in planned)):
                counts["present"] += 1
                continue
            counts["new"] += 1
            if not dry_run:
                entire_gitignore(out)
                out.mkdir(parents=True, exist_ok=True)
                (out / name).write_text(text, encoding="utf-8")
            print(f"{'new':8} {out / name}  ({text.splitlines()[0].split('(')[-1].split(',')[0]}, {len(text) // 1024} KB)")
    finally:
        reader.close()
    return counts


def entire_main(project, out, args, planned=()):
    if entire_git(project, "rev-parse", "--git-dir").returncode != 0:
        print(f"--entire: {project} is not a git repository, so there are no Entire checkpoints to read", file=sys.stderr)
        return 1
    counts = export_entire(project, out, args.since, args.max_chars, args.dry_run, planned=planned)
    if counts is None:
        print(f"no Entire checkpoints found in {project} (none committed yet, or none fetched)", file=sys.stderr)
        return 1
    print("entire: " + ", ".join(f"{v} {k}" for k, v in counts.items()), file=sys.stderr)
    return 0
