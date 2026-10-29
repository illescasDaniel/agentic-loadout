"""Questions to the user. Every question goes through `Prompter`, so --yes / --no-input are handled in one place."""

from __future__ import annotations

import sys
from collections.abc import Callable


class Prompter:
    def __init__(self, yes: bool = False, no_input: bool = False, input_fn: Callable[[str], str] = input,
                 out: Callable[[str], None] = print):
        self.yes, self.no_input, self._input, self.out = yes, no_input, input_fn, out

    @property
    def interactive(self) -> bool:
        return not self.no_input and (sys.stdin.isatty() or self._input is not input)

    def confirm(self, question: str, default: bool = True, always_ask: bool = False, assume: bool | None = None) -> bool:
        """Ask a yes/no question.

        --yes answers yes unless `always_ask` (machine-wide actions); `assume` answers it too, whatever the mode.
        Without a terminal (or with --no-input) the answer is no, so nothing happens that wasn't asked for.
        """
        if assume is not None:
            return assume
        if self.yes and not always_ask:
            return True
        if not self.interactive:
            return False
        suffix = " [Y/n] " if default else " [y/N] "
        try:
            answer = self._input(question + suffix).strip().lower()
        except EOFError:
            return False
        return default if not answer else answer in ("y", "yes")

    def ask(self, question: str, choices: tuple[str, ...], default: str) -> str:
        """Pick one of `choices`. --yes and --no-input take the default."""
        if self.yes or not self.interactive:
            return default
        try:
            answer = self._input(f"{question} [{'/'.join(choices)}] (default {default}) ").strip().lower()
        except EOFError:
            return default
        return answer if answer in choices else default
