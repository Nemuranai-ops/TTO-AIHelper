"""L14 CommandRunner - the only module in this codebase that imports subprocess.

Four guarantees, all in one place rather than at every call site:

  - **No shell.** `shell=False`, always. There is no shell to interpret a
    metacharacter, so the guarantee does not depend on the argument list being right.
  - **No interpolation.** The port takes a sequence; every caller passes literals.
  - **Bounded runtime.** A timeout per command, with a timeout distinguished from a
    non-zero exit - the first is a machine problem, the second is a project problem.
  - **Bounded output.** Truncated at capture, then sanitised.

`.importlinter` asserts this is the sole importer. That is the first contract in the
project to name a stdlib module, and it is worth the asymmetry: starting a process is
the most consequential capability this codebase can acquire.
"""

from __future__ import annotations

import shutil
import subprocess  # noqa: S404 - contained here by design; see the module docstring
import time
from pathlib import Path
from typing import Sequence

from tto_testgen.platform.result import sanitise
from tto_testgen.ports.commands import CommandResult

#: 64 KiB. A failing `npm ci` against a broken lockfile emits tens of megabytes, and
#: `capture_output=True` holds all of it - so the bound is applied when the text is
#: read, not after it is already in memory.
DEFAULT_OUTPUT_LIMIT = 65536


class SubprocessCommandRunner:
    """Runs one command. Decides nothing about which commands to run."""

    def __init__(
        self,
        workspace_root: Path | None = None,
        *,
        output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT,
    ) -> None:
        self._workspace_root = workspace_root
        self._limit = output_limit_bytes

    def is_available(self, executable: str) -> bool:
        """Resolve on PATH rather than attempting the command.

        Catching `FileNotFoundError` from the invocation would work and would
        conflate "not installed" with a permissions error, a broken symlink and a
        dozen other OSErrors - which is how a `skipped` status ends up hiding a real
        fault the operator needed to know about.
        """
        return shutil.which(executable) is not None

    def _clip(self, text: str) -> tuple[str, bool]:
        if len(text) <= self._limit:
            return sanitise(text, self._workspace_root), False
        head = text[: self._limit]
        return (
            sanitise(head, self._workspace_root)
            + f"\n[truncated at {self._limit} bytes]",
            True,
        )

    def run(
        self, argv: Sequence[str], *, cwd: Path, timeout_s: int
    ) -> CommandResult:
        arguments = [str(a) for a in argv]
        if not arguments:
            raise ValueError("argv must name a command")

        started = time.perf_counter()
        try:
            completed = subprocess.run(  # noqa: S603 - shell=False, literal argv
                arguments,
                cwd=str(cwd),
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                # A non-zero exit is an expected outcome here: a compilation failure
                # is information the report carries, not an exception to propagate.
                check=False,
            )
        except subprocess.TimeoutExpired as expired:
            elapsed = int((time.perf_counter() - started) * 1000)
            out, truncated = self._clip(_as_text(expired.stdout))
            errs, truncated_err = self._clip(_as_text(expired.stderr))
            return CommandResult(
                argv=tuple(arguments), exit_code=None, stdout=out, stderr=errs,
                timed_out=True, truncated=truncated or truncated_err,
                duration_ms=elapsed,
            )

        elapsed = int((time.perf_counter() - started) * 1000)
        out, truncated = self._clip(completed.stdout or "")
        errs, truncated_err = self._clip(completed.stderr or "")
        return CommandResult(
            argv=tuple(arguments),
            exit_code=completed.returncode,
            stdout=out,
            stderr=errs,
            truncated=truncated or truncated_err,
            duration_ms=elapsed,
        )


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
