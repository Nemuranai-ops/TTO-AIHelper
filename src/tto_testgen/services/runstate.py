"""S10 RunStateService - lease lifecycle, gate delegation, status composition.

Owns the state; delegates all gate policy to L5 GateEvaluator. Touches no other
service, and no other service calls anything here except `is_gate_open`.

There is deliberately no `next_unit`, `suggest`, or `ready_units` method. C-12
reserves scope selection to the operator, and the absence is the enforcement.

Requirements: FR-BAT-01 to FR-BAT-07, U7-NFR-REL-01 to -05, U7-NFR-PRF-01 to -04,
U7-NFR-SEC-01 to -03.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Iterator

from tto_testgen.domain.gates import (
    STAGE_ORDER,
    GateEvaluation,
    PriorRecord,
    Role,
    evaluate,
    is_role_permitted,
    prior_stage,
    stage_index,
)
from tto_testgen.domain.model import StageName, UnitState, UnitStateRecord, utc_now
from tto_testgen.platform.result import ErrorCode, Ok, Result, err, ok

DEFAULT_STALE_MINUTES = 30

#: Fields a status report must never contain. Asserted by property test: a report
#: carrying any of these turns a statement of fact into a recommendation.
FORBIDDEN_STATUS_FIELDS = frozenset({"next", "recommended", "ready", "suggested", "up_next"})


class LeaseClassification(str, Enum):
    ACTIVE = "active"
    STALE = "stale"
    ORPHANED_LOCK = "orphaned-lock"


@dataclass(frozen=True, slots=True)
class LeaseStatus:
    classification: LeaseClassification
    age_minutes: int
    holder: str | None = None
    produced_so_far: dict[str, Any] = field(default_factory=dict)
    guidance: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification.value,
            "age_minutes": self.age_minutes,
            "holder": self.holder,
            "produced_so_far": self.produced_so_far,
            "guidance": self.guidance,
        }


@dataclass(frozen=True, slots=True)
class UnitLease:
    lease_id: str
    unit_ref: str
    stage: StageName

    def to_dict(self) -> dict[str, Any]:
        return {"lease_id": self.lease_id, "unit_ref": self.unit_ref, "stage": self.stage.value}


@dataclass(slots=True)
class StatusReport:
    units: list[dict[str, Any]] = field(default_factory=list)
    corpus: dict[str, Any] = field(default_factory=dict)
    business_rules: dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""
    note: str = "Reporting only. The operator names the next unit."

    def to_dict(self) -> dict[str, Any]:
        return {
            "units": self.units,
            "corpus": self.corpus,
            "business_rules": self.business_rules,
            "generated_at": self.generated_at,
            "note": self.note,
        }


class ReportContext:
    """Request-scoped memo for coverage content hashes.

    Scoped to one report and discarded with it. A cache that cannot outlive the read
    it serves cannot go stale - which matters more than the saved work: a hash held
    across reports could serve a stale current-hash, and BR-U7-3 compares that
    against the recorded one to decide whether an approval still stands. A stale
    value would keep a revoked approval looking valid.
    """

    __slots__ = ("_coverage_repo", "_memo", "hits", "misses")

    def __init__(self, coverage_repo: Any) -> None:
        self._coverage_repo = coverage_repo
        self._memo: dict[int, str | None] = {}
        self.hits = 0
        self.misses = 0

    def coverage_hash(self, feature_id: int | None) -> str | None:
        if feature_id is None:
            return None
        if feature_id in self._memo:
            self.hits += 1
            return self._memo[feature_id]
        self.misses += 1
        value = self._coverage_repo.content_hash_for(feature_id)
        self._memo[feature_id] = value
        return value


@contextmanager
def report_context(coverage_repo: Any) -> Iterator[ReportContext]:
    yield ReportContext(coverage_repo)


def _minutes_between(earlier: str | None, now: datetime) -> int:
    if not earlier:
        return 0
    try:
        stamp = datetime.fromisoformat(earlier)
    except ValueError:
        return 0
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(0, int((now - stamp).total_seconds() // 60))


def _summarise(metrics: dict[str, Any]) -> str:
    produced = metrics.get("cases_produced", 0)
    consumed = metrics.get("artefacts_consumed", 0)
    if not produced and not consumed:
        return "nothing yet"
    parts = []
    if produced:
        parts.append(f"{produced} case(s)")
    if consumed:
        parts.append(f"{consumed} artefact(s) consumed")
    return ", ".join(parts)


class RunStateService:
    """S10. Depends on the repository port, never on a concrete adapter."""

    def __init__(
        self,
        uow_factory: Callable[[], Any],
        *,
        stale_after_minutes: int = DEFAULT_STALE_MINUTES,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._stale_after = stale_after_minutes
        self._now = clock or (lambda: datetime.now(timezone.utc))

    # --- lease lifecycle --------------------------------------------------

    def begin_unit(
        self, unit_ref: str, stage: StageName, *, regenerate: bool = False,
        holder: str | None = None,
    ) -> Result[UnitLease]:
        """BR-U7-1, BR-U7-7. Claim a unit, or explain why it cannot be claimed."""
        with self._uow_factory() as uow:
            existing = uow.run_state.get_state(unit_ref, stage)

            if existing is not None:
                state = UnitState(existing["state"])

                if state is UnitState.IN_PROGRESS:
                    status = self.classify_lease(existing)
                    return err(
                        ErrorCode.FAILED_LOCKED,
                        f"{unit_ref}/{stage.value} is already in progress "
                        f"({status.classification.value}, {status.age_minutes}m)",
                        remediation=status.guidance,
                        unit_ref=unit_ref,
                        stage=stage.value,
                        lease_status=status.to_dict(),
                    )

                if state is UnitState.COMPLETED and not regenerate:
                    # Retrying a failure is the expected next action; re-running a
                    # success can discard reviewed work, so it must be stated.
                    return err(
                        ErrorCode.REJECTED_ALREADY_COMPLETE,
                        f"{unit_ref}/{stage.value} is already complete",
                        unit_ref=unit_ref,
                        stage=stage.value,
                    )

            now = self._now().isoformat(timespec="seconds")
            lease_id = str(uuid.uuid4())
            uow.run_state.set_state(
                UnitStateRecord(
                    unit_ref=unit_ref,
                    stage=stage,
                    state=UnitState.IN_PROGRESS,
                    lease_id=lease_id,
                    approved_by=existing["approved_by"] if existing else None,
                    approved_at=existing["approved_at"] if existing else None,
                    approved_content_hash=(
                        existing["approved_content_hash"] if existing else None
                    ),
                    metrics={"leased_at": now, "last_heartbeat": now,
                             "lease_holder": holder or ""},
                )
            )
        return ok(UnitLease(lease_id=lease_id, unit_ref=unit_ref, stage=stage))

    def complete_unit(
        self, lease_id: str, unit_ref: str, stage: StageName, metrics: dict[str, Any]
    ) -> Result[None]:
        with self._uow_factory() as uow:
            existing = uow.run_state.get_state(unit_ref, stage)
            if existing is None:
                return err(
                    ErrorCode.FAILED_INTERNAL,
                    f"{unit_ref}/{stage.value} was never begun",
                    remediation="Call unit_begin before unit_complete.",
                )
            if existing["lease_id"] != lease_id:
                return err(
                    ErrorCode.FAILED_LOCKED,
                    "Lease does not match the active claim on this unit",
                    remediation="Re-claim the unit with unit_begin to obtain a current lease.",
                )
            # State and metrics commit together, so metrics can never disagree with
            # the state they describe.
            uow.run_state.set_state(
                UnitStateRecord(
                    unit_ref=unit_ref, stage=stage, state=UnitState.COMPLETED,
                    lease_id=None,
                    approved_by=existing["approved_by"],
                    approved_at=existing["approved_at"],
                    approved_content_hash=existing["approved_content_hash"],
                    metrics=metrics,
                )
            )
        return ok(None)

    def fail_unit(
        self, lease_id: str, unit_ref: str, stage: StageName, reason: str
    ) -> Result[None]:
        if not reason.strip():
            return err(ErrorCode.FAILED_INTERNAL, "A failure requires a reason")
        with self._uow_factory() as uow:
            existing = uow.run_state.get_state(unit_ref, stage)
            if existing is None or existing["lease_id"] != lease_id:
                return err(ErrorCode.FAILED_LOCKED, "Lease does not match")
            uow.run_state.set_state(
                UnitStateRecord(
                    unit_ref=unit_ref, stage=stage, state=UnitState.FAILED,
                    lease_id=None, failure_reason=reason,
                    approved_by=existing["approved_by"],
                    approved_at=existing["approved_at"],
                    approved_content_hash=existing["approved_content_hash"],
                    metrics=self._metrics_of(existing),
                )
            )
        return ok(None)

    def heartbeat(self, lease_id: str, unit_ref: str, stage: StageName) -> Result[None]:
        with self._uow_factory() as uow:
            existing = uow.run_state.get_state(unit_ref, stage)
            if existing is None or existing["lease_id"] != lease_id:
                return err(ErrorCode.FAILED_LOCKED, "Lease does not match")
            metrics = self._metrics_of(existing)
            metrics["last_heartbeat"] = self._now().isoformat(timespec="seconds")
            uow.run_state.set_state(
                UnitStateRecord(
                    unit_ref=unit_ref, stage=stage, state=UnitState.IN_PROGRESS,
                    lease_id=lease_id,
                    approved_by=existing["approved_by"],
                    approved_at=existing["approved_at"],
                    approved_content_hash=existing["approved_content_hash"],
                    metrics=metrics,
                )
            )
        return ok(None)

    # --- classification ---------------------------------------------------

    @staticmethod
    def _metrics_of(record: Any) -> dict[str, Any]:
        import json

        raw = record["metrics"] if "metrics" in record.keys() else None
        if isinstance(raw, dict):
            return dict(raw)
        try:
            return json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    def classify_lease(self, record: Any) -> LeaseStatus:
        """BR-U7-2. Reports; never clears.

        No branch here removes, expires or reclaims a lease. Clearing a lock another
        process still holds is how databases get corrupted, and this code cannot tell
        a dead session from a slow one. The operator can look.
        """
        metrics = self._metrics_of(record)
        reference = metrics.get("last_heartbeat") or metrics.get("leased_at")
        age = _minutes_between(reference, self._now())
        holder = metrics.get("lease_holder") or None

        if age <= self._stale_after:
            return LeaseStatus(
                classification=LeaseClassification.ACTIVE,
                age_minutes=age,
                holder=holder,
                produced_so_far=metrics,
                guidance=(
                    f"Another session claimed this {age}m ago and appears active. "
                    f"Wait, or work on a different unit."
                ),
            )

        return LeaseStatus(
            classification=LeaseClassification.STALE,
            age_minutes=age,
            holder=holder,
            produced_so_far=metrics,
            guidance=(
                f"Claimed {age}m ago with no sign of life since. If that session has "
                f"ended, restart with regenerate=true. It had produced: "
                f"{_summarise(metrics)}."
            ),
        )

    # --- gates ------------------------------------------------------------

    def is_gate_open(
        self, unit_ref: str, stage: StageName, ctx: ReportContext | None = None
    ) -> GateEvaluation:
        """The whole of the cross-unit surface. Read-only, joins no transaction."""
        previous = prior_stage(stage)
        if previous is None:
            return evaluate(unit_ref, stage, None)

        with self._uow_factory() as uow:
            record = uow.run_state.get_state(unit_ref, previous)
            feature = uow.features.get_by_slug(unit_ref)
            feature_id = feature["id"] if feature else None
            current_hash = (
                ctx.coverage_hash(feature_id)
                if ctx is not None
                else (uow.coverage.content_hash_for(feature_id) if feature_id else None)
            )

        prior = (
            PriorRecord(
                state=UnitState(record["state"]),
                approved_by=record["approved_by"],
                approved_at=record["approved_at"],
                approved_content_hash=record["approved_content_hash"],
            )
            if record is not None
            else None
        )
        return evaluate(unit_ref, stage, prior, current_hash)

    def approve_stage(
        self, unit_ref: str, stage: StageName, approver: str, role: Role,
        content_hash: str | None = None,
    ) -> Result[dict[str, Any]]:
        """BR-U7-3.5. Only the Test Lead approves the coverage baseline."""
        if not is_role_permitted(stage, role):
            return err(
                ErrorCode.REJECTED_ROLE_NOT_PERMITTED,
                f"The {stage.value} stage may only be approved by the test lead",
                remediation=f"Have the Test Lead approve the {stage.value} stage.",
                attempted_by=approver,
                role=role.value,
            )

        with self._uow_factory() as uow:
            existing = uow.run_state.get_state(unit_ref, stage)
            state = UnitState(existing["state"]) if existing else UnitState.NOT_STARTED
            feature = uow.features.get_by_slug(unit_ref)
            resolved_hash = content_hash
            if resolved_hash is None and feature is not None:
                resolved_hash = uow.coverage.content_hash_for(feature["id"])
            approved_at = self._now().isoformat(timespec="seconds")
            uow.run_state.set_state(
                UnitStateRecord(
                    unit_ref=unit_ref, stage=stage, state=state,
                    lease_id=existing["lease_id"] if existing else None,
                    approved_by=approver, approved_at=approved_at,
                    approved_content_hash=resolved_hash,
                    metrics=self._metrics_of(existing) if existing else {},
                )
            )
        return ok(
            {
                "unit_ref": unit_ref, "stage": stage.value, "approved_by": approver,
                "role": role.value, "approved_at": approved_at,
                "content_hash": resolved_hash,
            }
        )

    # --- reporting --------------------------------------------------------

    def get_status(self, scope: str | None = None) -> StatusReport:
        """BR-U7-4. Facts only.

        Sorted by (unit_ref, stage_order): stable, deterministic, and carrying no
        signal about what to do next. No `next` field, no ordering by readiness, no
        filtering to open gates - each would turn a report into a proposal.
        """
        with self._uow_factory() as uow:
            records = list(uow.run_state.all_states(scope))
            active_cases = uow.cases.count_active()
            features = len(uow.features.list_all())
            ctx = ReportContext(uow.coverage)

            rows: list[dict[str, Any]] = []
            for record in records:
                stage = StageName(record["stage"])
                state = UnitState(record["state"])
                rows.append(
                    {
                        "unit_ref": record["unit_ref"],
                        "stage": stage.value,
                        "state": state.value,
                        "approved_by": record["approved_by"],
                        "approved_at": record["approved_at"],
                        "gate_open": self._gate_open_within(uow, record["unit_ref"], stage, ctx),
                        "lease_status": (
                            self.classify_lease(record).to_dict()
                            if state is UnitState.IN_PROGRESS
                            else None
                        ),
                        "metrics": self._metrics_of(record),
                    }
                )

        rows.sort(key=lambda r: (r["unit_ref"], stage_index(StageName(r["stage"]))))
        return StatusReport(
            units=rows,
            corpus={"active_cases": active_cases, "features": features},
            generated_at=self._now().isoformat(timespec="seconds"),
        )

    def _gate_open_within(
        self, uow: Any, unit_ref: str, stage: StageName, ctx: ReportContext
    ) -> bool:
        previous = prior_stage(stage)
        if previous is None:
            return True
        record = uow.run_state.get_state(unit_ref, previous)
        feature = uow.features.get_by_slug(unit_ref)
        current_hash = ctx.coverage_hash(feature["id"] if feature else None)
        prior = (
            PriorRecord(
                state=UnitState(record["state"]),
                approved_by=record["approved_by"],
                approved_at=record["approved_at"],
                approved_content_hash=record["approved_content_hash"],
            )
            if record is not None
            else None
        )
        return evaluate(unit_ref, stage, prior, current_hash).is_open

    def resume_view(self) -> dict[str, Any]:
        """BR-U7-5. Every interruption looks the same, because the recovery is."""
        report = self.get_status()
        interrupted = [r for r in report.units if r["state"] == UnitState.IN_PROGRESS.value]
        return {
            "interrupted": interrupted,
            "completed": sum(
                1 for r in report.units if r["state"] == UnitState.COMPLETED.value
            ),
            "corpus": report.corpus,
            "note": (
                "Nothing was lost. Unit work is transactional: an interrupted unit "
                "committed nothing, so restarting it re-runs it from the beginning."
            ),
        }
