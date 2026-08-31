"""Atomicity detection for testable requirements.

BR-U3-2.1. A statement is non-atomic when it joins two independently verifiable verb
phrases. Atomicity is the one property nothing downstream can recover: a bundled
requirement produces bundled cases, a case verifying two behaviours cannot be traced
to either alone, and a coverage report counting it once overstates coverage of both.
Every later stage inherits the error and none can detect it.

The heuristic is deliberately conservative. A false rejection costs one resubmission;
a false acceptance costs a permanently untraceable case. The asymmetry justifies
erring toward acceptance and letting review catch what this misses.

Pure: takes a statement, returns a verdict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Verbs that commonly head an independently verifiable clause in a requirement.
#: Not exhaustive by design - the heuristic only claims to catch the obvious cases.
_VERBS = (
    r"is|are|was|were|shall|should|must|will|can|may|does|do|"
    r"returns?|rejects?|accepts?|displays?|shows?|sends?|stores?|creates?|"
    r"updates?|deletes?|validates?|calculates?|records?|logs?|prevents?|allows?|"
    r"redirects?|raises?|throws?|fails?|succeeds?"
)

_CONJUNCTION_SPLIT = re.compile(
    rf"\b(?P<left>(?:{_VERBS}))\b.{{2,120}}?\s+(?P<conj>and|or)\s+.{{0,40}}?\b(?P<right>(?:{_VERBS}))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AtomicityVerdict:
    is_atomic: bool
    suspected_split: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "is_atomic": self.is_atomic,
            "suspected_split": self.suspected_split,
            "detail": self.detail,
        }


def check(statement: str, *, force_atomic: bool = False) -> AtomicityVerdict:
    """Judge a requirement statement.

    `force_atomic` is the documented escape (U3-NFR-MNT-01). A heuristic with no
    escape becomes a wall the agent works around by mangling wording; one with an
    unrecorded escape becomes a habit nobody notices. This one is available and its
    use is logged, so if overrides cluster the heuristic needs work - and that is
    visible rather than inferred.
    """
    if force_atomic:
        return AtomicityVerdict(
            is_atomic=True, detail="atomicity check overridden by the caller"
        )

    text = " ".join(statement.split())
    if not text:
        return AtomicityVerdict(is_atomic=False, detail="statement is empty")

    match = _CONJUNCTION_SPLIT.search(text)
    if match is None:
        return AtomicityVerdict(is_atomic=True)

    conjunction = match.group("conj")
    split_at = match.start("conj")
    return AtomicityVerdict(
        is_atomic=False,
        suspected_split=f"{text[:split_at].strip()} | {text[split_at + len(conjunction):].strip()}",
        detail=(
            f"two verb phrases joined by '{conjunction}'. Split into separate "
            f"requirements, restate as one behaviour, or pass force_atomic=true if "
            f"this reads as a single behaviour."
        ),
    )
