"""Which languages a project uses, from marker files in the root and one level down. Nothing fancier on purpose:
if detection misses, the user names the language."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

SKIP_DIRS = {"node_modules", ".venv", "venv", "build", "dist", "Pods", ".git", "__pycache__", "site-packages", "DerivedData"}

MARKERS = {  # language -> glob patterns on file or directory names
    "python": ("pyproject.toml", "setup.py", "setup.cfg", "requirements*.txt", "Pipfile", "uv.lock"),
    "typescript": ("package.json", "tsconfig.json", "jsconfig.json", "deno.json"),
    "swift": ("Package.swift", "*.xcodeproj", "*.xcworkspace", "Podfile", "Cartfile"),
}
XCODE_PATTERNS = ("*.xcodeproj", "*.xcworkspace")


def _names(project: Path) -> list[str]:
    """Names in the project root and in each non-hidden, non-vendored subdirectory."""
    names: list[str] = []
    try:
        entries = sorted(project.iterdir())
    except OSError:
        return names
    for entry in entries:
        names.append(entry.name)
        if entry.is_dir() and not entry.is_symlink() and entry.name not in SKIP_DIRS and not entry.name.startswith(".") \
                and not entry.suffix in (".xcodeproj", ".xcworkspace", ".xcassets"):
            try:
                names.extend(child.name for child in entry.iterdir())
            except OSError:
                pass
    return names


def _matches(names: list[str], patterns: tuple[str, ...]) -> bool:
    return any(fnmatch(name, pattern) for name in names for pattern in patterns)


def detect_languages(project: Path) -> list[str]:
    names = _names(project)
    return [lang for lang, patterns in MARKERS.items() if _matches(names, patterns)]


def has_xcode_project(project: Path) -> bool:
    return _matches(_names(project), XCODE_PATTERNS)
