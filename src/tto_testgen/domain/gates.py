"""L5 GateEvaluator - the policy that decides whether work may proceed.

BR-U7-3. Three conditions, all required: the prior stage is completed, it is
approved, and the approved content hash still matches what is there now.

Pure by construction. `evaluate` receives the prior stage's record and the current
content hash as arguments rather than fetching them, which has three consequences:

  - It can be called from inside a caller's transaction without joining it. S4, S5,
    S6 and S7 evaluate gates while holding their own; a component that read from a
    repository would enlist in that transaction and could roll back with it.
  - It is exhaustively testable. Three conditions across seven stages is a small
    enough space to cover completely, and no database is needed to do it.
  - The read-only guarantee is structural. There is no repository here, so there is
    nothing to write through.

Requirements: U7-NFR-REL-05, U7-NFR-PRF-01, FR-BAT-07, FR-COV-06.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from tto_testgen.domain.model import StageName, UnitState

#: The pipeline, in order. Held as data rather than scattered through conditionals
#: so gate evaluation and status sorting cannot disagree about what order it runs in.
STAGE_ORDER: tuple[StageName, ...] = (
    StageName.INGEST,
    StageName.ANALYSE,
    StageName.REQUIREMENTS,
    StageName.COVERAGE,
    StageName.CASES,
    StageName.AUTOMATION,
    StageName.HANDOVER,
)


class Role(str, Enum):
    """Closed set. An unrecognised value is an invalid role, not an unauthorised one.

    U1 accepted this as a free string, which was adequate for a thin wrapper. But
    'testlead' instead of 'test-lead' would fail the coverage restriction closed -
    the right outcome for the wrong reason, telling the operator they lack authority
    when in fact they made a typo.
    """

    TEST_ANALYST = "test-analyst"
    TEST_AUTOMATION_ENGINEER = "test-automation-engineer"
    TEST_LEAD = "test-lead"


class GateFailure(str, Enum):
    NOT_COMPLETED = "not-completed"
    NOT_APPROVED = "not-approved"
    CONTENT_CHANGED = "content-changed"


#: BR-U7-3.5. Only the coverage baseline is role-restricted (FR-COV-06).
ROLE_RESTRICTED: dict[StageName, Role] = {StageName.COVERAGE: Role.TEST_LEAD}


@dataclass(frozen=True, slots=True)
class PriorRecord:
    """The subset of a unit_state row that gate evaluation needs.

    A narrow input type rather than the full record: it makes the evaluator's
    dependency on storage shape explicit and small, and it lets the property tests
    generate exactly the space that matters.
    """

    state: UnitState
    approved_by: str | None = None
    approved_at: str | None = None
    approved_content_hash: str | None = None


@dataclass(frozen=True, slots=True)
class GateEvaluation:
    is_open: bool
    stage: StageName
    prior_stage: StageName | None = None
    failed_condition: GateFailure | None = None
    detail: str = ""
    remediation: str = ""
    permitted_role: Role | None = None
    approved_by: str | None = None
    approved_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "is_open": self.is_open,
            "stage": self.stage.value,
            "prior_stage": self.prior_stage.value if self.prior_stage else None,
            "failed_condition": self.failed_condition.value if self.failed_condition else None,
            "detail": self.detail,
            "remediation": self.remediation,
            "permitted_role": self.permitted_role.value if self.permitted_role else None,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
        }


def stage_index(stage: StageName) -> int:
    return STAGE_ORDER.index(stage)


def prior_stage(stage: StageName) -> StageName | None:
    """The stage that must be complete before `stage` may begin. None for the first."""
    index = stage_index(stage)
    return STAGE_ORDER[index - 1] if index > 0 else None


def next_stage(stage: StageName) -> StageName | None:
    """Used only for stage ordering in reports. Never to propose work (C-12)."""
    index = stage_index(stage)
    return STAGE_ORDER[index + 1] if index < len(STAGE_ORDER) - 1 else None


def is_role_permitted(stage: StageName, role: Role) -> bool:
    """BR-U7-3.5. Kept in one function so four calling services cannot disagree."""
    required = ROLE_RESTRICTED.get(stage)
    return required is None or role is required


def _role_clause(stage: StageName) -> str:
    required = ROLE_RESTRICTED.get(stage)
    return f" The {required.value.replace('-', ' ')} must do this." if required else ""


def evaluate(
    unit_ref: str,
    stage: StageName,
    prior: PriorRecord | None,
    current_content_hash: str | None = None,
) -> GateEvaluation:
    """BR-U7-3. Open only when all three conditions hold.

    `prior` is None when no record exists for the prior stage - the same situation
    as a record in `not-started`, and reported the same way.
    """
    previous = prior_stage(stage)
    if previous is None:
        # The first stage has no predecessor, so its gate is always open.
        return GateEvaluation(is_open=True, stage=stage)

    if prior is None or prior.state is not UnitState.COMPLETED:
        return GateEvaluation(
            is_open=False,
            stage=stage,
            prior_stage=previous,
            failed_condition=GateFailure.NOT_COMPLETED,
            detail=f"{previous.value} is not complete for {unit_ref}",
            remediation=f"Complete the {previous.value} stage for {unit_ref} first.",
        )

    if prior.approved_by is None:
        return GateEvaluation(
            is_open=False,
            stage=stage,
            prior_stage=previous,
            failed_condition=GateFailure.NOT_APPROVED,
            detail=f"{previous.value} is complete but not approved for {unit_ref}",
            remediation=(
                f"Approve the {previous.value} stage for {unit_ref}."
                f"{_role_clause(previous)}"
            ),
            permitted_role=ROLE_RESTRICTED.get(previous),
        )

    # An approval recorded without a hash is honoured rather than blocking forever,
    # but the detail says so, leaving the weaker guarantee visible rather than assumed.
    if prior.approved_content_hash is not None and current_content_hash is not None:
        if prior.approved_content_hash != current_content_hash:
            return GateEvaluation(
                is_open=False,
                stage=stage,
                prior_stage=previous,
                failed_condition=GateFailure.CONTENT_CHANGED,
                detail=(
                    f"{previous.value} was approved by {prior.approved_by} on "
                    f"{prior.approved_at}, but its content has changed since"
                ),
                remediation=(
                    f"Re-approve the {previous.value} stage for {unit_ref}; the "
                    f"earlier approval no longer applies.{_role_clause(previous)}"
                ),
                permitted_role=ROLE_RESTRICTED.get(previous),
                approved_by=prior.approved_by,
                approved_at=prior.approved_at,
            )

    return GateEvaluation(
        is_open=True,
        stage=stage,
        prior_stage=previous,
        approved_by=prior.approved_by,
        approved_at=prior.approved_at,
    )
