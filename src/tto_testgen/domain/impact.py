"""D8 ImpactAnalyzer - turning a detected change into a precise statement.

BR-9. Classify each affected case unchanged, requires-update or obsolete. Report
changes that map to nothing rather than assuming they are harmless, and state the
scale before any regeneration is proposed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tto_testgen.domain.model import ChangeClassification

#: BR-9. Above this share of the active corpus, the scale is reported and
#: confirmation required before regeneration.
LARGE_IMPACT_THRESHOLD = 0.20


@dataclass(frozen=True, slots=True)
class ChangedRef:
    ref: str
    source: str  # "bitbucket" | "jira"
    kind: str = "modified"  # modified | deleted | added


@dataclass(frozen=True, slots=True)
class TraceEdge:
    changed_ref: str
    case_id: str
    requirement_id: str
    statement_changed: bool = False
    rule_changed: bool = False
    requirement_deleted: bool = False
    target_removed: bool = False


@dataclass(frozen=True, slots=True)
class ClassifiedImpact:
    case_id: str
    classification: ChangeClassification
    reason: str
    changed_ref: str


@dataclass(slots=True)
class ImpactSet:
    impacts: list[ClassifiedImpact] = field(default_factory=list)
    unmapped: list[ChangedRef] = field(default_factory=list)
    corpus_size: int = 0

    @property
    def affected_case_ids(self) -> set[str]:
        return {i.case_id for i in self.impacts}

    @property
    def scale(self) -> float:
        if self.corpus_size <= 0:
            return 0.0
        touched = {
            i.case_id
            for i in self.impacts
            if i.classification is not ChangeClassification.UNCHANGED
        }
        return len(touched) / self.corpus_size

    @property
    def is_large(self) -> bool:
        return self.scale > LARGE_IMPACT_THRESHOLD

    def by_classification(self) -> dict[str, int]:
        counts = {c.value: 0 for c in ChangeClassification}
        for impact in self.impacts:
            counts[impact.classification.value] += 1
        return counts


def classify_edge(edge: TraceEdge) -> ClassifiedImpact:
    """BR-9. First matching condition decides."""
    if edge.requirement_deleted:
        return ClassifiedImpact(
            edge.case_id,
            ChangeClassification.OBSOLETE,
            "the requirement it verifies was deleted",
            edge.changed_ref,
        )
    if edge.target_removed:
        return ClassifiedImpact(
            edge.case_id,
            ChangeClassification.OBSOLETE,
            "the endpoint or screen it targets was removed",
            edge.changed_ref,
        )
    if edge.statement_changed:
        return ClassifiedImpact(
            edge.case_id,
            ChangeClassification.REQUIRES_UPDATE,
            "the requirement statement changed",
            edge.changed_ref,
        )
    if edge.rule_changed:
        return ClassifiedImpact(
            edge.case_id,
            ChangeClassification.REQUIRES_UPDATE,
            "a business rule it depends on changed",
            edge.changed_ref,
        )
    return ClassifiedImpact(
        edge.case_id,
        ChangeClassification.UNCHANGED,
        "source changed but the verified behaviour did not",
        edge.changed_ref,
    )


def map_impact(
    changes: list[ChangedRef], edges: list[TraceEdge], corpus_size: int
) -> ImpactSet:
    """Map changes through the traceability graph.

    A change touching nothing traceable is reported as unmapped, never assumed to
    have no impact. "We found no link" and "there is no impact" are different
    statements, and conflating them is how an untested change ships.
    """
    by_ref: dict[str, list[TraceEdge]] = {}
    for edge in edges:
        by_ref.setdefault(edge.changed_ref, []).append(edge)

    result = ImpactSet(corpus_size=corpus_size)
    for change in changes:
        matching = by_ref.get(change.ref, [])
        if not matching:
            result.unmapped.append(change)
            continue
        for edge in matching:
            result.impacts.append(classify_edge(edge))
    return result
