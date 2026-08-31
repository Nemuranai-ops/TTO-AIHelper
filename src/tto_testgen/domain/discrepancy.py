"""Discrepancy detection - recording that two sources disagree, never settling it.

BR-U2-6. The test for whether something is a discrepancy:

    Would a tester write a different test depending on which source they believed?

If yes, record it. If no, it is a difference and is not recorded. Recording every
difference buries the signal, and a report nobody reads because it is mostly noise is
worse than none - it looks like diligence.

Pure: detectors take two claims and return a record. Resolution is a human act, and
nothing here performs one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class DiscrepancyKind(str, Enum):
    ENDPOINT_NOT_IMPLEMENTED = "endpoint-not-implemented"
    SHAPE_MISMATCH = "shape-mismatch"
    STATUS_CODE_UNDOCUMENTED = "status-code-undocumented"
    AUTH_REQUIREMENT_MISMATCH = "auth-requirement-mismatch"
    SCREEN_NOT_IN_LIVE = "screen-not-in-live"
    SCREEN_DIFFERS_FROM_DESIGN = "screen-differs-from-design"
    RULE_CONTRADICTION = "rule-contradiction"


@dataclass(frozen=True, slots=True)
class Discrepancy:
    """Symmetric by construction. Neither claim is marked correct."""

    kind: DiscrepancyKind
    subject: str
    source_a: str
    claim_a: str
    source_b: str
    claim_b: str
    detected_at: str = ""

    def __post_init__(self) -> None:
        if not self.subject.strip():
            raise ValueError("A discrepancy requires a subject")
        if self.source_a == self.source_b:
            raise ValueError("A discrepancy requires two different sources")

    @classmethod
    def of(cls, kind, subject, source_a, claim_a, source_b, claim_b) -> "Discrepancy":
        return cls(
            kind=kind, subject=subject,
            source_a=source_a, claim_a=claim_a,
            source_b=source_b, claim_b=claim_b,
            detected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind.value, "subject": self.subject,
            "source_a": self.source_a, "claim_a": self.claim_a,
            "source_b": self.source_b, "claim_b": self.claim_b,
            "detected_at": self.detected_at,
        }


def screen_not_in_live(screen_name: str) -> Discrepancy:
    return Discrepancy.of(
        DiscrepancyKind.SCREEN_NOT_IN_LIVE, screen_name,
        "figma", "screen present in the design set",
        "live", "no matching screen found in the application",
    )


def screen_differs_from_design(screen_name: str, design: str, live: str) -> Discrepancy:
    return Discrepancy.of(
        DiscrepancyKind.SCREEN_DIFFERS_FROM_DESIGN, screen_name,
        "figma", design, "live", live,
    )


def rule_contradiction(condition: str, jira_effect: str, code_effect: str) -> Discrepancy:
    return Discrepancy.of(
        DiscrepancyKind.RULE_CONTRADICTION, condition,
        "jira", jira_effect, "code", code_effect,
    )


def from_merge(merge_discrepancy) -> Discrepancy:
    """Lift an API merge discrepancy into the common record."""
    return Discrepancy.of(
        DiscrepancyKind(merge_discrepancy.kind), merge_discrepancy.subject,
        merge_discrepancy.source_a, merge_discrepancy.claim_a,
        merge_discrepancy.source_b, merge_discrepancy.claim_b,
    )


#: Differences that are NOT discrepancies. Kept as documentation of the boundary,
#: because the tempting mistake is to detect these and drown the real signal.
NOT_DISCREPANCIES = (
    "wording differences between two descriptions of the same rule",
    "formatting, whitespace or field ordering",
    "a Confluence page phrasing a rule differently from Jira while meaning the same",
    "comment text differing from documentation",
)
