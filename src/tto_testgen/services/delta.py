"""S9 DeltaService - detect what moved, classify it, retire the obsolete, and stop.

**S9 has no method that creates a requirement or a case.** FR-DLT-06 requires delta
runs to face the same human gates as the baseline, and a delta run that regenerated
would bypass every one of them. The constraint holds by absence - the fourth and last
use of that pattern, after P2's write-free source protocols, RunStateService's missing
`next_unit()` and S7's missing `push`.

Classification is D8's. S9 builds the four booleans of a `TraceEdge` from the corpus
and hands them over; it decides nothing about what they mean. This is the eighth unit,
and the seven before it each resisted the same temptation to copy a domain algorithm
for local convenience.

Requirements: FR-DLT-01 to FR-DLT-07.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from tto_testgen.domain.impact import (
    ChangeClassification,
    ChangedRef,
    ImpactSet,
    TraceEdge,
    map_impact,
)
from tto_testgen.domain.model import ChangeEvent, Run, StageName, utc_now
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import ErrorCode, Result, err, ok

PROJECT_SLUG = "<project>"


def advance_baseline(run_id: int, detection: Any, run_state: Any) -> bool:
    """Advance the baseline only when every source was reached. P-U8-01.

    A module-level function rather than a method, so it can be exercised without
    constructing a service - which matters because this is the function whose failure
    would be invisible.

    **Advancing after a partial detection makes the undetected changes invisible for
    ever**: the next run compares from the newer head, so everything in the window the
    failed source covered is silently skipped. That is not a degraded run - it is a
    permanently wrong corpus, and nothing downstream would ever reveal it.

    Returns whether it advanced, so the caller reports the fact rather than assuming
    it.
    """
    if detection.unavailable_sources:
        return False
    run_state.record_baseline(run_id, detection.head_commits, detection.jira_watermark)
    return True


@dataclass(slots=True)
class DeltaReport:
    run_id: int | None = None
    baseline_run_id: int | None = None
    baseline_ended_at: str | None = None
    no_baseline_reason: str = ""
    detection: dict[str, Any] = field(default_factory=dict)
    impact: dict[str, Any] = field(default_factory=dict)
    retired: list[dict[str, Any]] = field(default_factory=list)
    requires_update: list[dict[str, Any]] = field(default_factory=list)
    unmapped: list[dict[str, Any]] = field(default_factory=list)
    baseline_advanced: bool = False
    change_event_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "baseline_run_id": self.baseline_run_id,
            "baseline_ended_at": self.baseline_ended_at,
            "no_baseline_reason": self.no_baseline_reason,
            "detection": self.detection,
            "impact": self.impact,
            "retired": self.retired,
            "retired_count": len(self.retired),
            # Reported, never touched: regenerating would bypass the gates.
            "requires_update": self.requires_update,
            "requires_update_count": len(self.requires_update),
            # Lifted to the top level: it is the finding an operator most needs to
            # see, and the one most easily lost inside a nested structure.
            "unmapped": self.unmapped,
            "baseline_advanced": self.baseline_advanced,
            "derivation": (
                "changes since the last completed run, mapped through the "
                "traceability graph and classified by the impact rules. Obsolete "
                "cases are retired, never deleted. requires-update cases are "
                "reported and left untouched; regenerating them re-enters the "
                "pipeline at the requirements stage, through the normal gates."
            ),
        }


class DeltaService:
    """Detection, classification, retirement. Creates nothing."""

    def __init__(
        self,
        uow_factory: Callable[[], Any],
        run_state: Any,
        detector: Any,
        logger: Logger,
    ) -> None:
        self._uow_factory = uow_factory
        self._run_state = run_state
        self._detector = detector
        self._logger = logger

    # --- detection ------------------------------------------------------------

    def detect(self, run_id: int | None = None) -> Result[DeltaReport]:
        # No gate is evaluated here, and that is the correct reading of FR-DLT-06.
        #
        # "Delta runs face the same gates as the baseline" is about the work a delta
        # *triggers*: regenerating requirements and cases re-enters the pipeline at
        # U3 and U4, where the gates already are. Detection itself creates nothing -
        # it reads, and it retires cases whose requirement no longer exists, which is
        # recording a fact the change already made true.
        #
        # Gating detection would also invert the intent: an operator could not learn
        # that the corpus had gone stale until they had approved a stage, and the
        # thing they most need before approving is the knowledge that it moved.
        report = DeltaReport()
        with self._uow_factory() as uow:
            baseline_row = uow.run_state.last_completed_run()
            if baseline_row is None:
                # Treating "no baseline" as "everything changed" would classify the
                # whole corpus as affected - true, unhelpful, and it would obscure
                # the real answer, which is that no run has finished.
                report.no_baseline_reason = (
                    "no completed run to compare against; finish a baseline run first"
                )
                return ok(report)
            baseline = _baseline_of(baseline_row)
            report.baseline_run_id = baseline.run_id
            report.baseline_ended_at = baseline.ended_at

        detection = self._detector.detect(baseline)
        report.detection = detection.to_dict()

        with self._uow_factory() as uow:
            # A detection is itself a run. `run.kind = 'delta'` has existed since U1
            # and this is its first writer; `change_event.run_id` is NOT NULL, so
            # there is no way to record a change without one - which is the schema
            # saying that a change nobody can attribute to a run is not a fact worth
            # keeping.
            if run_id is None:
                uow.run_state.start_run(
                    Run(correlation_id=f"delta-{baseline.run_id}", kind="delta",
                        started_at=utc_now())
                )
                run_id = uow.run_state.current_run_id()
            report.run_id = run_id

            edges = self._edges_for(uow, detection.changes)
            corpus_size = uow.cases.count_active()
            impact = map_impact(detection.changes, edges, corpus_size)
            report.impact = _impact_summary(impact)
            report.unmapped = [
                {"ref": c.ref, "source": c.source, "kind": c.kind}
                for c in impact.unmapped
            ]
            report.requires_update = [
                {"case_id": i.case_id, "reason": i.reason, "changed_ref": i.changed_ref}
                for i in impact.impacts
                if i.classification is ChangeClassification.REQUIRES_UPDATE
            ]

            event_id = uow.changes.add(ChangeEvent(
                run_id=run_id,
                source="bitbucket" if detection.head_commits else "jira",
                ref_from=_first_head(baseline.head_commits),
                ref_to=_first_head(detection.head_commits),
                changed_refs=[c.ref for c in detection.changes],
                jira_keys=[c.ref for c in detection.changes if c.source == "jira"],
                is_unmapped=bool(impact.unmapped),
                impact_scale=impact.scale,
            ))
            report.change_event_id = event_id

            report.retired = self._retire(uow, impact, event_id)

            report.baseline_advanced = advance_baseline(
                run_id, detection, uow.run_state
            )
            if report.baseline_advanced:
                # Only a run whose detection was complete becomes the next baseline.
                uow.run_state.complete_run(run_id)

        self._logger.info(
            "delta detected", changes=len(detection.changes),
            retired=len(report.retired), advanced=report.baseline_advanced,
            complete=detection.complete,
        )
        return ok(report)

    def baseline_status(self) -> Result[dict[str, Any]]:
        with self._uow_factory() as uow:
            row = uow.run_state.last_completed_run()
        if row is None:
            return ok({
                "has_baseline": False,
                "reason": "no completed run to compare against",
            })
        baseline = _baseline_of(row)
        return ok({
            "has_baseline": True,
            "run_id": baseline.run_id,
            "ended_at": baseline.ended_at,
            "head_commits": dict(sorted(baseline.head_commits.items())),
            "jira_watermark": baseline.jira_watermark,
        })

    # --- edges ------------------------------------------------------------------

    def _edges_for(self, uow: Any, changes: list[ChangedRef]) -> list[TraceEdge]:
        """Build the four booleans D8 classifies on. U8 decides nothing here."""
        edges: list[TraceEdge] = []
        for change in changes:
            for link in uow.traces.for_target(change.ref):
                record = dict(link)
                if str(record.get("source_kind")) != "test_case":
                    continue
                case = uow.cases.get(str(record["source_id"]))
                if case is None:
                    continue
                item = uow.coverage.get(str(case["coverage_item_id"]))
                requirement_id = (
                    str(dict(item)["requirement_id"]) if item is not None else ""
                )
                requirement = (
                    uow.requirements.get(requirement_id) if requirement_id else None
                )
                edges.append(
                    TraceEdge(
                        changed_ref=change.ref,
                        case_id=str(case["id"]),
                        requirement_id=requirement_id,
                        # The four booleans are the whole interface between this unit
                        # and D8. U8 assembles them from the corpus; `classify_edge`
                        # decides what they mean.
                        requirement_deleted=item is None or requirement is None,
                        target_removed=change.kind == "removed",
                        statement_changed=(
                            change.kind == "modified" and change.source == "jira"
                        ),
                        rule_changed=False,
                    )
                )
        return edges

    # --- retirement ---------------------------------------------------------------

    def _retire(
        self, uow: Any, impact: ImpactSet, change_event_id: int
    ) -> list[dict[str, Any]]:
        """Mark obsolete. Nothing is deleted, and nothing cascades.

        Steps, test data, trace links and the automated test all remain. The case
        leaves coverage counts, generated views and duplicate candidate selection
        automatically, because U3's and U4's queries already filter on `is_obsolete`.
        """
        retired: list[dict[str, Any]] = []
        for entry in impact.impacts:
            if entry.classification is not ChangeClassification.OBSOLETE:
                continue
            uow.cases.mark_obsolete(entry.case_id, entry.reason, change_event_id)
            retired.append({
                "case_id": entry.case_id,
                "reason": entry.reason,
                "changed_ref": entry.changed_ref,
            })
        return retired


def _baseline_of(row: Any) -> Any:
    import json

    from tto_testgen.adapters.change_detector import DeltaBaseline

    record = dict(row)
    try:
        heads = json.loads(record.get("head_commits") or "{}")
    except ValueError:
        heads = {}
    return DeltaBaseline(
        run_id=int(record["id"]),
        ended_at=str(record["ended_at"]),
        head_commits={str(k): str(v) for k, v in heads.items()},
        jira_watermark=record.get("jira_watermark"),
    )


def _impact_summary(impact: ImpactSet) -> dict[str, Any]:
    return {
        "affected_cases": len(impact.affected_case_ids),
        "by_classification": impact.by_classification(),
        "scale": round(impact.scale, 4),
        "is_large": impact.is_large,
        "unmapped": len(impact.unmapped),
    }


def _first_head(heads: dict[str, str]) -> str:
    return next(iter(sorted(heads.values())), "")
