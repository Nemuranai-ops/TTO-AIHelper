"""D3 TraceabilityResolver - the rule that keeps the corpus honest.

BR-3 and BR-8. Every test case must carry at least one link resolving to a Jira key.
Where no direct story link exists, a key is derived from commit history and recorded
as `derived-from-commit` - never presented as equivalent to a direct link, because
provenance is weaker evidence than specification.

Where no key can be derived by any route, the behaviour becomes a gap. It does not
become a test case with an invented link.

PBT targets: PBT-03 - matrix bidirectional consistency, every non-obsolete case
reaches at least one Jira key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from tto_testgen.domain.model import (
    LINK_TYPE_PRECEDENCE,
    LinkType,
    TraceLink,
)

_JIRA_IN_TEXT = re.compile(r"\b([A-Z]{2,10}-[1-9]\d*)\b")

DEFAULT_LOOKBACK_DAYS = 180


@dataclass(frozen=True, slots=True)
class CommitRecord:
    sha: str
    message: str
    committed_at: datetime
    lines_changed: int = 0

    @property
    def jira_keys(self) -> list[str]:
        return _JIRA_IN_TEXT.findall(self.message)


@dataclass(frozen=True, slots=True)
class Gap:
    """A behaviour that could not be traced. Recorded, never silently dropped."""

    source_ref: str
    description: str
    attempted: list[str] = field(default_factory=list)
    category: str = "untraceable-behaviour"


@dataclass(frozen=True, slots=True)
class KeyResolution:
    jira_key: str
    link_type: LinkType
    evidence: str
    selection_basis: str | None = None
    alternatives: list[dict[str, object]] = field(default_factory=list)

    def to_link(self, source_kind: str, source_id: str, target_ref: str) -> TraceLink:
        return TraceLink(
            source_kind=source_kind,
            source_id=source_id,
            target_ref=target_ref,
            link_type=self.link_type,
            evidence=self.evidence,
            selection_basis=self.selection_basis,
            alternatives=self.alternatives,
            resolved_jira_key=self.jira_key,
        )


def require_jira_key(links: list[TraceLink], known_keys: frozenset[str]) -> str | None:
    """BR-8.2 step 1. The strongest link resolving to a *known* key.

    Membership in `known_keys` is the point: it is what stops an invented key from
    satisfying the rule. A key that resolves but was never ingested is not evidence
    of anything (US-TRC-01 AC4).
    """
    resolving = [
        link
        for link in links
        if link.resolved_jira_key and link.resolved_jira_key in known_keys
    ]
    if not resolving:
        return None
    resolving.sort(key=lambda l: LINK_TYPE_PRECEDENCE.index(l.link_type))
    return resolving[0].resolved_jira_key


def derive_key_from_commits(
    file_path: str,
    commits: list[CommitRecord],
    known_keys: frozenset[str],
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
) -> KeyResolution | Gap:
    """BR-3. Resolve a Jira key from the commits that touched a file.

    Selection order: most recent commit carrying a known key, tie-broken by lines
    changed, then by timestamp, then lexically for determinism.

    The lookback window is the part that matters most. Without it a five-year-old
    refactor can become the recorded provenance of today's behaviour - a link that
    is technically present and substantively meaningless, which is worse than an
    honest gap because it satisfies the rule while defeating its purpose.
    """
    reference = now or datetime.now(timezone.utc)
    cutoff = reference - timedelta(days=lookback_days)

    candidates: list[tuple[str, CommitRecord]] = []
    for commit in commits:
        if commit.committed_at < cutoff:
            continue
        for key in commit.jira_keys:
            if key in known_keys:
                candidates.append((key, commit))

    if not candidates:
        return Gap(
            source_ref=file_path,
            description="No Jira key derivable from commit history",
            attempted=[
                "direct-story",
                f"commit-derivation (window {lookback_days}d, "
                f"{len(commits)} commits examined)",
            ],
        )

    candidates.sort(
        key=lambda pair: (
            -pair[1].committed_at.timestamp(),
            -pair[1].lines_changed,
            pair[0],
        )
    )
    chosen_key, chosen_commit = candidates[0]
    others = [
        {"jira_key": key, "sha": commit.sha, "committed_at": commit.committed_at.isoformat()}
        for key, commit in candidates[1:]
    ]

    basis = (
        f"most recent commit within {lookback_days}d window; "
        f"{len(candidates)} candidate(s)"
    )
    if len(candidates) > 1 and candidates[0][1].committed_at == candidates[1][1].committed_at:
        basis += "; tie broken by lines changed"

    return KeyResolution(
        jira_key=chosen_key,
        link_type=LinkType.DERIVED_FROM_COMMIT,
        evidence=f"{chosen_commit.sha[:12]} {chosen_commit.message.splitlines()[0][:80]}",
        selection_basis=basis,
        alternatives=others,
    )


# ---------------------------------------------------------------------------
# Traceability matrix
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MatrixEdge:
    from_kind: str
    from_id: str
    to_kind: str
    to_id: str


@dataclass(slots=True)
class TraceMatrix:
    forward: dict[str, list[str]] = field(default_factory=dict)
    reverse: dict[str, list[str]] = field(default_factory=dict)

    def add(self, source: str, target: str) -> None:
        self.forward.setdefault(source, [])
        self.reverse.setdefault(target, [])
        if target not in self.forward[source]:
            self.forward[source].append(target)
        if source not in self.reverse[target]:
            self.reverse[target].append(source)

    def ensure_node(self, node: str) -> None:
        """Record a node with no edges.

        Requirements with zero cases must appear with an empty set, never be
        omitted: an absent row hides exactly what the matrix exists to reveal
        (US-TRC-04 AC4).
        """
        self.forward.setdefault(node, [])

    def targets_of(self, source: str) -> list[str]:
        return self.forward.get(source, [])

    def sources_of(self, target: str) -> list[str]:
        return self.reverse.get(target, [])

    def is_bidirectionally_consistent(self) -> bool:
        """PBT-03. Every forward edge has a corresponding reverse edge."""
        for source, targets in self.forward.items():
            for target in targets:
                if source not in self.reverse.get(target, []):
                    return False
        for target, sources in self.reverse.items():
            for source in sources:
                if target not in self.forward.get(source, []):
                    return False
        return True

    def uncovered(self, expected_sources: list[str]) -> list[str]:
        return [s for s in expected_sources if not self.forward.get(s)]


def build_matrix(edges: list[MatrixEdge], all_sources: list[str] | None = None) -> TraceMatrix:
    matrix = TraceMatrix()
    for source in all_sources or []:
        matrix.ensure_node(source)
    for edge in edges:
        matrix.add(edge.from_id, edge.to_id)
    return matrix


def link_counts_by_type(links: list[TraceLink]) -> dict[str, int]:
    """BR-3.6. Derived links are counted separately from direct links.

    Provenance is weaker evidence than specification, so a coverage report that
    merged the two would overstate how well the corpus is grounded.
    """
    counts = {link_type.value: 0 for link_type in LinkType}
    for link in links:
        counts[link.link_type.value] += 1
    return counts
