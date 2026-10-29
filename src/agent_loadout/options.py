from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .vendors import TOOLS

COMPONENTS = ("sdd", "agemem", "agents", "coders", "worktree")


@dataclass
class Options:
    project: Path
    tools: list[str] = field(default_factory=lambda: ["claude"])
    with_coders: list[str] | None = None  # None: detect and confirm; [] with "coders" in `without`: skip
    without: frozenset[str] = frozenset()
    memory_model: str | None = None
    no_hooks: bool = False
    personal_settings: bool = False
    git_exclude: bool = False
    claude_compat: bool = False
    model: str | None = None
    dry_run: bool = False
    no_input: bool = False
    yes: bool = False
    allow_brew: bool = False
    force: bool = False

    def wants(self, component: str) -> bool:
        return component not in self.without

    @property
    def hide(self) -> bool:
        """Keep the files this run creates out of git (personal mode implies it)."""
        return self.personal_settings or self.git_exclude

    def selected(self) -> list[str]:
        return [t for t in TOOLS if t in self.tools]
