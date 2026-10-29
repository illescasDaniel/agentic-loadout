"""Language coders. A coder is one unit: the `coder-<lang>` subagent, the language's code-navigation MCP server and a
routing rule in the instruction file. They are always installed together, because without the subagent and its
instructions the agent doesn't use the MCP's tools.

This table is the only place to add a language.
"""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import pins
from .agents import ASSETS, write_agent
from .brew import BrewPlan, System, plan_swift, run_plan, swift_binary_path
from .detect import detect_languages
from .files import Ctx
from .instructions import Section
from .mcp_config import add_servers, servers_in
from .options import Options
from .ui import Prompter
from .vendors import VENDORS, _split, agent_filename


@dataclass(frozen=True)
class Coder:
    key: str  # language: what the user types and detection returns
    agent: str  # file name under .claude/agents/
    label: str
    extensions: str
    description: str
    server_key: str  # key in the MCP config; tool names are mcp__<server_key>__<tool>
    server: dict
    tools: tuple[str, ...]
    prerequisite: str
    fragment: str  # file under assets/templates/coders/

    @property
    def section(self) -> Section:
        paragraph = (
            f"Any task that adds, changes, renames, moves or deletes {self.extensions} code goes to `{self.agent}`, not "
            f"the generic `coder`: it uses the project's `{self.server_key}` MCP for type-checked navigation and "
            f"refactoring. Keep `coder` for everything else, and split a task that spans languages."
        )
        return Section(self.agent, f"## {self.label} code goes to `{self.agent}`\n\n"
                       + textwrap.fill(paragraph, width=120, break_on_hyphens=False))


PYTHON_TOOLS = (
    "symbol_info", "outline", "callers", "implementations", "search_symbol", "workspace", "hover", "definition",
    "references", "diagnostics", "edit", "edit_symbol", "rename_symbol", "change_signature", "move", "quick_fix",
    "verify_changes", "apply_edit", "undo_edit",
)
SWIFT_TOOLS = (
    "symbol_info", "references", "callers", "implementations", "type_at", "outline", "search_symbol", "hover",
    "definition", "diagnostics", "workspace", "verify", "affected_tests", "rename_symbol", "change_signature",
    "edit_symbol", "insert_member", "delete_symbol", "move_symbol", "add_conformance", "fix_diagnostics", "refactor",
    "apply_edit", "check_edit", "undo_edit",
)
TYPESCRIPT_TOOLS = (
    "symbol_info", "outline", "callers", "implementations", "search_symbol", "workspace", "hover", "definition",
    "references", "diagnostics", "css_var", "selector", "edit", "edit_symbol", "rename_symbol", "move", "quick_fix",
    "verify_changes", "apply_edit", "undo_edit",
)

CODERS = {
    c.key: c
    for c in (
        Coder(
            key="python",
            agent="coder-python",
            label="Python",
            extensions="`.py`/`.pyi`",
            description=(
                "Implementation engineer for Python code, backed by the codenav MCP (type-checked navigation and "
                "refactoring). Use INSTEAD of `coder` for any task that adds, changes, renames, moves or deletes Python "
                "code (.py/.pyi): an architect plan step, SDD Phase 3 tests or Phase 4 implementation step, grader "
                "fixes, a bug with a known cause. Same contract as `coder`."
            ),
            server_key="codenav",
            server={"type": "stdio", "command": "uvx", "args": ["--from", pins.CODENAV_SPEC, "codenav-mcp"]},
            tools=PYTHON_TOOLS,
            prerequisite="needs uv and Python 3.11+ (codenav-mcp runs through uvx).",
            fragment="python.md",
        ),
        Coder(
            key="swift",
            agent="coder-swift",
            label="Swift",
            extensions="Swift/Objective-C/C/C++ (`.swift`, `.m`, `.mm`, `.h`, `.c`, `.cpp`)",
            description=(
                "Implementation engineer for Swift code (also Objective-C, C and C++), backed by the codenav-swift MCP "
                "(compiler-aware navigation and refactoring). Use INSTEAD of `coder` for any task that adds, changes, "
                "renames, moves or deletes Swift or Objective-C code: an architect plan step, SDD Phase 3 tests or "
                "Phase 4 implementation step, grader fixes, a bug with a known cause. Same contract as `coder`."
            ),
            server_key="codenav-swift",
            server={"type": "stdio", "command": "codenav-swift-mcp", "env": {"CODENAV_SWIFT_WRITE": "1"}},
            tools=SWIFT_TOOLS,
            prerequisite="needs macOS 13+, a Swift toolchain and the codenav-swift-mcp binary (Homebrew).",
            fragment="swift.md",
        ),
        Coder(
            key="typescript",
            agent="coder-typescript",
            label="TypeScript",
            extensions="JavaScript/TypeScript/HTML/CSS (`.ts`, `.tsx`, `.js`, `.jsx`, `.html`, `.css`)",
            description=(
                "Implementation engineer for JavaScript, TypeScript, HTML and CSS code, backed by the webnav MCP "
                "(type-checked navigation and refactoring). Use INSTEAD of `coder` for any task that adds, changes, "
                "renames, moves or deletes such code: an architect plan step, SDD Phase 3 tests or Phase 4 "
                "implementation step, grader fixes, a bug with a known cause. Same contract as `coder`."
            ),
            server_key="webnav",
            server={"type": "stdio", "command": "npx", "args": [pins.WEBNAV_SPEC]},
            tools=TYPESCRIPT_TOOLS,
            prerequisite="needs Node.js 20+ (webnav-ts-mcp runs through npx).",
            fragment="typescript.md",
        ),
    )
}


def parse_languages(values: list[str]) -> list[str]:
    """`all`, or language names (a comma-separated list is fine). Unknown names are an error."""
    names = [n.strip().lower() for v in values for n in v.split(",") if n.strip()]
    if "all" in names:
        return list(CODERS)
    unknown = [n for n in names if n not in CODERS]
    if unknown:
        raise SystemExit(f"error: unknown language {', '.join(unknown)}; choose from {', '.join(CODERS)} or all")
    return [k for k in CODERS if k in names]


def agent_bytes(coder: Coder, memory: bool) -> bytes:
    """The coder's agent file (Claude format): generic `coder.md` + the language's navigation section + MCP tools."""
    fields, body = _split((ASSETS / "agents" / "coder.md").read_text(encoding="utf-8"))
    builtin = ("Read", "Edit", "Write", "Glob", "Grep", "Bash")
    recall = ("mcp__agemem__project_memory_recall",) if memory else ()
    tools = ", ".join((*builtin, *recall, *(f"mcp__{coder.server_key}__{t}" for t in coder.tools)))
    fields = {k: v for k, v in fields.items() if k not in ("name", "description", "disallowedTools")}
    fields["tools"] = tools
    head = f"name: {coder.agent}\ndescription: {json.dumps(coder.description, ensure_ascii=False)}\n"
    head += yaml.safe_dump(fields, sort_keys=False, allow_unicode=True, width=120)
    section = (ASSETS / "templates" / "coders" / coder.fragment).read_text(encoding="utf-8").strip()
    body, count = re.subn(r"\n## Rules", f"\n{section}\n\n## Rules", body, count=1)
    if count != 1:
        raise SystemExit("error: assets/agents/coder.md has no '## Rules' heading to put the navigation section before")
    return ("---\n" + head + "---\n" + body).encode("utf-8")


def server_for(coder: Coder, tool: str, project: Path, system: System) -> dict:
    server = json.loads(json.dumps(coder.server))
    if coder.key == "python" and (project / "src").is_dir():
        server["env"] = {"CODENAV_MCP_SOURCE_ROOT": "src"}
    if coder.key == "swift" and tool == "cursor":
        server["command"] = swift_binary_path(system)
    return server


def status(ctx: Ctx, coder: Coder, tools: list[str]) -> str:
    """installed (agent + server for every selected tool), partial, or absent."""
    agents = [ctx.exists(ctx.project / VENDORS[t].agents_dir / agent_filename(t, coder.agent)) for t in tools]
    servers = [coder.server_key in servers_in(ctx, t) for t in tools]
    found = agents + servers
    return "installed" if all(found) else "partial" if any(found) else "absent"


@dataclass
class CoderPlan:
    keys: list[str]
    brew: BrewPlan | None = None
    skipped_hint: str | None = None  # command to print when nothing was installed because we couldn't ask


def prepare(ctx: Ctx, opts: Options, prompter: Prompter, system: System, requested: list[str] | None) -> CoderPlan:
    """Decide which coders to install. All questions are asked here, before anything is written."""
    if not opts.wants("coders"):
        return CoderPlan([])
    if requested is not None:
        keys = list(requested)
    else:
        keys = []
        detected = detect_languages(opts.project)
        if not detected:
            ctx.log("coders", "-", "no Python, TypeScript or Swift project files found; name a language with `agent-loadout coders <language>`")
        for key in detected:
            coder = CODERS[key]
            current = status(ctx, coder, opts.selected())
            if current == "installed":
                ctx.log("installed", coder.agent, f"({coder.server_key} MCP already set up)")
            elif prompter.confirm(f"Detected {coder.label}. Install `{coder.agent}` with the {coder.server_key} MCP?"):
                keys.append(key)
        declined = [k for k in detected if k not in keys and status(ctx, CODERS[k], opts.selected()) != "installed"]
        hint = None
        if declined:
            hint = "uvx --python 3.12 agent-loadout coders " + " ".join(declined)
            ctx.note(f"Language coders not installed ({', '.join(declined)}). Install them any time with: {hint}")
        if not keys:
            return CoderPlan([], None, hint)
    plan = CoderPlan(keys)
    if "swift" in keys:
        plan.brew = plan_swift(opts.project, prompter, system, opts.allow_brew)
        for message in plan.brew.messages:
            ctx.note(message)
    return plan


def install(ctx: Ctx, opts: Options, plan: CoderPlan, system: System, memory: bool) -> list[Section]:
    """Write the agents and MCP servers; returns the routing-rule sections for the instruction file."""
    sections = []
    tools = opts.selected()
    for key in plan.keys:
        coder = CODERS[key]
        write_agent(ctx, tools, coder.agent, agent_bytes(coder, memory))
        for tool in tools:
            add_servers(ctx, tool, {coder.server_key: server_for(coder, tool, opts.project, system)})
        sections.append(coder.section)
        ctx.note(f"{coder.agent}: {coder.prerequisite}")
    if plan.brew is not None and (plan.brew.install_binary or plan.brew.install_xcode_build_server):
        if ctx.dry_run:
            ctx.log("would run", "brew install", " ".join(f for f, on in ((pins.SWIFT_BREW_FORMULA, plan.brew.install_binary),
                    (pins.XCODE_BUILD_SERVER_FORMULA, plan.brew.install_xcode_build_server)) if on))
        else:
            for error in run_plan(plan.brew, system, ctx.lines.append):
                ctx.warn(error)
    return sections


def list_coders(ctx: Ctx, opts: Options) -> str:
    detected = detect_languages(opts.project)
    rows = [f"  {'language':<11} {'coder':<18} {'MCP':<14} {'detected':<9} state"]
    for key, coder in CODERS.items():
        rows.append(f"  {key:<11} {coder.agent:<18} {coder.server_key:<14} {'yes' if key in detected else 'no':<9} "
                    f"{status(ctx, coder, opts.selected())}")
    return "\n".join(rows)
