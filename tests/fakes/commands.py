"""A fake CommandRunner.

The U6 suite must pass on a machine with no Node, because working without Node is a
feature of that unit rather than a limitation of the test environment. Every
toolchain path is therefore exercised through this fake, and the real runner is
tested separately against the Python interpreter already running the suite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from tto_testgen.ports.commands import CommandResult


@dataclass(slots=True)
class FakeCommandRunner:
    """Canned results by executable name, plus a record of what was asked."""

    available: set[str] = field(default_factory=lambda: {"npm", "npx", "node"})
    #: Keyed by the first argv element that matters - "npm ci", "npx tsc", etc.
    outcomes: dict[str, CommandResult] = field(default_factory=dict)
    calls: list[tuple[tuple[str, ...], Path, int]] = field(default_factory=list)

    def is_available(self, executable: str) -> bool:
        return executable in self.available

    def run(self, argv: Sequence[str], *, cwd: Path, timeout_s: int) -> CommandResult:
        arguments = tuple(str(a) for a in argv)
        self.calls.append((arguments, cwd, timeout_s))
        for key, result in self.outcomes.items():
            if " ".join(arguments).startswith(key):
                return result
        return CommandResult(argv=arguments, exit_code=0)


def failing(argv: tuple[str, ...], stderr: str = "error TS2307: cannot find module") -> CommandResult:
    return CommandResult(argv=argv, exit_code=2, stderr=stderr)


def timing_out(argv: tuple[str, ...]) -> CommandResult:
    return CommandResult(argv=argv, exit_code=None, timed_out=True, duration_ms=300000)
