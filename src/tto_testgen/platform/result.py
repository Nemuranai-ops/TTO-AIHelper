"""X1 ResultAndErrors - the failure vocabulary shared across the MCP boundary.

Rejection is a normal event in this system: the design refuses invalid work by intent.
The agent must be able to tell "your test case has no Jira key, add one" from "the
database is unreachable", because the correct response differs completely. That is why
the code taxonomy has two families rather than one.

Requirements: NFR-SEC-07, NFR-SEC-08, NFR-USA-03.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Generic, TypeVar

T = TypeVar("T")


class ErrorCode(str, Enum):
    """Two families. REJECTED_* means the caller must change its input;
    FAILED_* means the system had a problem and blind retry is inappropriate."""

    # --- REJECTED_*: agent-fixable -------------------------------------------
    REJECTED_NO_STEPS = "REJECTED_NO_STEPS"
    REJECTED_INVALID_STEPS = "REJECTED_INVALID_STEPS"
    REJECTED_NO_JIRA_KEY = "REJECTED_NO_JIRA_KEY"
    REJECTED_UNKNOWN_JIRA_KEY = "REJECTED_UNKNOWN_JIRA_KEY"
    REJECTED_DUPLICATE = "REJECTED_DUPLICATE"
    REJECTED_MISSING_EQUIVALENCE_CLASS = "REJECTED_MISSING_EQUIVALENCE_CLASS"
    REJECTED_SELF_SUPPLIED_ID = "REJECTED_SELF_SUPPLIED_ID"
    REJECTED_PERSONAL_DATA = "REJECTED_PERSONAL_DATA"
    REJECTED_GATE_CLOSED = "REJECTED_GATE_CLOSED"
    REJECTED_ALREADY_COMPLETE = "REJECTED_ALREADY_COMPLETE"
    REJECTED_ROLE_NOT_PERMITTED = "REJECTED_ROLE_NOT_PERMITTED"

    # --- FAILED_*: system problems -------------------------------------------
    FAILED_DB_UNAVAILABLE = "FAILED_DB_UNAVAILABLE"
    FAILED_MCP_UNREACHABLE = "FAILED_MCP_UNREACHABLE"
    FAILED_MIGRATION = "FAILED_MIGRATION"
    FAILED_TIMEOUT = "FAILED_TIMEOUT"
    FAILED_LOCKED = "FAILED_LOCKED"
    FAILED_INTERNAL = "FAILED_INTERNAL"

    @property
    def is_rejection(self) -> bool:
        return self.value.startswith("REJECTED_")


#: Remediation text per code. Held here rather than at each call site so the guidance
#: the agent receives for a given failure is identical wherever it is raised.
REMEDIATION: dict[ErrorCode, str] = {
    ErrorCode.REJECTED_NO_STEPS: "Add ordered steps, each with a non-empty expected result.",
    ErrorCode.REJECTED_INVALID_STEPS: "Number steps consecutively from 1 with no gaps or duplicates.",
    ErrorCode.REJECTED_NO_JIRA_KEY: (
        "Add a trace link resolving to a Jira key, or route this behaviour to the gap report."
    ),
    ErrorCode.REJECTED_UNKNOWN_JIRA_KEY: (
        "The referenced Jira key is not in the ingested set. Ingest the issue, or use a key that exists."
    ),
    ErrorCode.REJECTED_DUPLICATE: (
        "A matching case already exists. Differentiate this case or drop it."
    ),
    ErrorCode.REJECTED_MISSING_EQUIVALENCE_CLASS: (
        "State the equivalence class or boundary each data value represents."
    ),
    ErrorCode.REJECTED_SELF_SUPPLIED_ID: "Omit the identifier; the toolchain allocates it.",
    ErrorCode.REJECTED_PERSONAL_DATA: (
        "Replace the value with a documented synthetic one. The rejection names the "
        "field, the pattern matched, and the permitted form."
    ),
    ErrorCode.REJECTED_GATE_CLOSED: "Obtain approval for the named stage before continuing.",
    ErrorCode.REJECTED_ALREADY_COMPLETE: (
        "This unit and stage are already complete. Pass regenerate=true if re-running is intended."
    ),
    ErrorCode.REJECTED_ROLE_NOT_PERMITTED: "This approval is restricted to a different role.",
    ErrorCode.FAILED_DB_UNAVAILABLE: "Check the database path and run the health check.",
    ErrorCode.FAILED_MCP_UNREACHABLE: "The external MCP server did not respond. Check credentials and connectivity.",
    ErrorCode.FAILED_MIGRATION: "The migration was rolled back. Restore from the pre-migration backup.",
    ErrorCode.FAILED_TIMEOUT: "The operation exceeded its budget. Reduce the batch scope and retry.",
    ErrorCode.FAILED_LOCKED: (
        "The database is locked, possibly by a terminated process. "
        "Verify no other TAAS process is running, then retry."
    ),
    ErrorCode.FAILED_INTERNAL: "An unexpected condition occurred. The operation was rolled back.",
}

_SECRET_PATTERNS = [
    re.compile(r"(?i)(token|secret|password|api[_-]?key)\s*[=:]\s*\S+"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]+"),
]
_TRACE_LINE = re.compile(r'\s*File "[^"]+", line \d+.*')


def sanitise(message: str, workspace_root: Path | None = None) -> str:
    """Strip anything that must not cross the MCP boundary.

    Removes paths outside the workspace, stack-trace lines and secret-shaped text
    (NFR-SEC-08). Paths *inside* the workspace are kept relative, because an agent
    told 'resources.md not found' can act on it.
    """
    out = _TRACE_LINE.sub("", message)
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub("[redacted]", out)

    if workspace_root is not None:
        root = str(workspace_root.resolve())
        out = out.replace(root + "/", "").replace(root, ".")

    # Any absolute path still present points outside the workspace.
    out = re.sub(r"(?<![\w.])/(?:[\w.\-]+/)*[\w.\-]+", "<path>", out)
    out = re.sub(r"[A-Za-z]:\\(?:[\w.\-]+\\)*[\w.\-]+", "<path>", out)
    return " ".join(out.split())


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    value: T
    ok: bool = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class Err:
    code: ErrorCode
    message: str
    remediation: str = ""
    context: dict[str, object] = field(default_factory=dict)
    ok: bool = field(default=False, init=False)

    @property
    def is_rejection(self) -> bool:
        return self.code.is_rejection


Result = Ok[T] | Err


def ok(value: T) -> Ok[T]:
    return Ok(value)


def err(
    code: ErrorCode,
    message: str,
    *,
    remediation: str | None = None,
    workspace_root: Path | None = None,
    **context: object,
) -> Err:
    return Err(
        code=code,
        message=sanitise(message, workspace_root),
        remediation=remediation if remediation is not None else REMEDIATION.get(code, ""),
        context=context,
    )


def is_rejection(result: Result[T]) -> bool:
    return isinstance(result, Err) and result.is_rejection
