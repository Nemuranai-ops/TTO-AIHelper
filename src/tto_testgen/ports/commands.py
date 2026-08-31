"""P4 CommandPort - running an external command, contained.

The signature is the enforcement. `argv` is a **sequence of strings, never a string**,
so a caller cannot pass a shell command even by mistake - and the one adapter behind
this port runs everything with `shell=False`, so there is no shell to interpret a
metacharacter even if one arrived.

U6 is the only unit that starts a process, and this is the only port through which it
may. `.importlinter` asserts that `subprocess` is imported by exactly one module, so a
future unit reaching for the capability fails the build rather than quietly acquiring
it (U6-NFR-SEC-01, -02, U6-NFR-MNT-01).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable


@dataclass(frozen=True, slots=True)
class CommandResult:
    """What happened. `exit_code` is None only when the command timed out."""

    argv: tuple[str, ...]
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    truncated: bool = False
    duration_ms: int = 0

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def summary(self) -> str:
        if self.timed_out:
            return f"{' '.join(self.argv)} timed out"
        return f"{' '.join(self.argv)} exited {self.exit_code}"


@runtime_checkable
class CommandRunner(Protocol):
    def run(
        self, argv: Sequence[str], *, cwd: Path, timeout_s: int
    ) -> CommandResult: ...

    def is_available(self, executable: str) -> bool: ...
