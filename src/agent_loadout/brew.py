"""The one machine-wide action agent-loadout can take: installing the codenav-swift-mcp binary with Homebrew.

It never runs without an explicit yes (`--allow-brew` counts), even when `--yes` is passed. The decision is made
before any file is written (preflight); the install itself runs later, in the coders step.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import pins
from .detect import has_xcode_project
from .ui import Prompter

SWIFT_BINARY = "codenav-swift-mcp"
SWIFT_REPO = "https://github.com/illescasDaniel/codenav-swift-mcp"


@dataclass
class System:
    """What the brew decision needs from the machine; tests replace it."""

    system: Callable[[], str] = platform.system
    which: Callable[[str], str | None] = shutil.which
    run: Callable[[Sequence[str]], subprocess.CompletedProcess] = field(
        default=lambda cmd: subprocess.run(list(cmd), capture_output=True, text=True, check=False))


@dataclass
class BrewPlan:
    state: str = "present"  # present | install | declined | no-brew | not-macos
    install_binary: bool = False
    install_xcode_build_server: bool = False
    messages: list[str] = field(default_factory=list)

    @property
    def needs_binary(self) -> bool:
        return self.state in ("declined", "no-brew", "not-macos")


def plan_swift(project: Path, prompter: Prompter, system: System, allow_brew: bool = False) -> BrewPlan:
    """Decide what to do about the Swift binary (and xcode-build-server). Asks the user; runs nothing."""
    plan = BrewPlan()
    if system.system() != "Darwin":
        plan.state = "not-macos"
        plan.messages.append(f"{SWIFT_BINARY} only runs on macOS 13+ with a Swift toolchain; the config is written but "
                             f"the server won't start here. See {SWIFT_REPO}")
        return plan
    if system.which(SWIFT_BINARY):
        pass
    elif system.which("brew") is None:
        plan.state = "no-brew"
        plan.messages.append(f"Homebrew was not found. Install it (https://brew.sh) and run "
                             f"`brew install {pins.SWIFT_BREW_FORMULA}`, or build from source: {SWIFT_REPO}")
    elif prompter.confirm(f"Install {SWIFT_BINARY} with Homebrew (`brew install {pins.SWIFT_BREW_FORMULA}`)? "
                          "This installs it machine-wide.", default=False, always_ask=True, assume=True if allow_brew else None):
        plan.state, plan.install_binary = "install", True
    else:
        plan.state = "declined"
        plan.messages.append(f"Run `brew install {pins.SWIFT_BREW_FORMULA}` when you want the Swift coder to work.")
    if has_xcode_project(project) and not (project / "buildServer.json").exists():
        if system.which("xcode-build-server") is None and system.which("brew") is not None and prompter.confirm(
                f"Install xcode-build-server with Homebrew (`brew install {pins.XCODE_BUILD_SERVER_FORMULA}`)? "
                "Xcode projects need it.", default=False, always_ask=True, assume=True if allow_brew else None):
            plan.install_xcode_build_server = True
        plan.messages.append("Xcode project without buildServer.json: run "
                             "`xcode-build-server config -project <App>.xcodeproj -scheme <Scheme>` "
                             "(pick your scheme; this isn't run for you).")
    return plan


def run_plan(plan: BrewPlan, system: System, log: Callable[[str], None] = print) -> list[str]:
    """Run the confirmed brew installs. Returns error messages (empty when everything worked)."""
    errors = []
    for wanted, formula in ((plan.install_binary, pins.SWIFT_BREW_FORMULA),
                            (plan.install_xcode_build_server, pins.XCODE_BUILD_SERVER_FORMULA)):
        if not wanted:
            continue
        log(f"  running    brew install {formula}")
        result = system.run(["brew", "install", formula])
        if result.returncode != 0:
            errors.append(f"`brew install {formula}` failed: {(result.stderr or '').strip()[-300:]}")
    return errors


def swift_binary_path(system: System) -> str:
    """Absolute path for Cursor, which doesn't inherit the shell PATH."""
    found = system.which(SWIFT_BINARY)
    if found:
        return found
    result = system.run(["brew", "--prefix"]) if system.which("brew") else None
    prefix = result.stdout.strip() if result is not None and result.returncode == 0 and result.stdout.strip() else "/opt/homebrew"
    return f"{prefix}/bin/{SWIFT_BINARY}"
