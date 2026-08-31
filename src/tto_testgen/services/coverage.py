"""S4 CoverageService - the baseline, its forecast, and the gate that guards it.

The coverage arithmetic is D2's. This service feeds it, versions its output, hashes
what the approval binds to, and delegates the role restriction to U7.

Requirements: FR-COV-01 to FR-COV-07.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from tto_testgen.domain.coverage import (
    RequirementSpec,
    TechniqueInputs,
    compute_yield,
    derive_coverage,
    find_uncovered,
    select_reduction,
)
from tto_testgen.domain.coverage_hash import coverage_hash, next_version
from tto_testgen.domain.gates import Role
from tto_testgen.domain.model import RiskBand, StageName, utc_now
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import ErrorCode, Ok, Result, err, ok


@dataclass(slots=True)
class CoverageBuildResult:
    feature_slug: str
    model_version: int
    content_hash: str
    items: int = 0
    required_items: int = 0
    planned_total: int = 0
    per_test_type: dict[str, int] = field(default_factory=dict)
    gaps_recorded: int = 0
    approval_invalidated: bool = False
    previous_approver: str | None = None
    previous_approved_at: str | None = None
    disproportionate: list[str] = field(default_factory=list)
    zero_yield: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "feature": self.feature_slug,
            "model_version": self.model_version,
            "content_hash": self.content_hash,
            "items": self.items,
            "required_items": self.required_items,
            "planned_total": self.planned_total,
            "per_test_type": self.per_test_type,
            "gaps_recorded": self.gaps_recorded,
            "approval_invalidated": self.approval_invalidated,
            "derivation": (
                "sum of coverage_item.planned_count, ISTQB-standard depth "
                "(BR-2). Not-required items are stored with planned_count 0."
            ),
        }
        if self.approval_invalidated:
            # Information, not an error: the rebuild worked. Returning a REJECTED_*
            # code would tell the agent to fix input that is not wrong, and burying
            # this in a log would leave the operator to discover it when the cases
            # gate refuses - at which point it reads as a bug.
            payload["note"] = (
                f"The coverage model changed, so the approval by "
                f"{self.previous_approver} on {self.previous_approved_at} no longer "
                f"applies. The cases gate will refuse until it is re-approved."
            )
        if self.disproportionate:
            payload["disproportionate"] = self.disproportionate
        if self.zero_yield:
            payload["zero_yield"] = self.zero_yield
        return payload


@dataclass(slots=True)
class ReductionResult:
    feature_slug: str
    technique: str
    full_yield: int
    reduced_yield: int
    was_override: bool
    risk_band: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature_slug,
            "technique": self.technique,
            "full_yield": self.full_yield,
            "reduced_yield": self.reduced_yield,
            # Both yields, so the gap report can say how much coverage was given up
            # rather than merely that some was.
            "coverage_given_up": self.full_yield - self.reduced_yield,
            "was_override": self.was_override,
            "risk_band": self.risk_band,
            "note": "Reduction changed the model, so any prior approval no longer applies.",
        }


def _technique_inputs(candidate: dict[str, Any]) -> TechniqueInputs:
    return TechniqueInputs(
        valid_classes=candidate.get("valid_classes", 0),
        invalid_classes=candidate.get("invalid_classes", 0),
        boundaries=candidate.get("boundaries", 0),
        decision_rules=candidate.get("decision_rules", 0),
        valid_transitions=candidate.get("valid_transitions", 0),
        forbidden_transitions=candidate.get("forbidden_transitions", 0),
        independent_parameters=candidate.get("independent_parameters", 0),
        boundaries_undetermined=candidate.get("boundaries_undetermined", False),
    )


class CoverageService:
    def __init__(
        self,
        uow_factory: Callable[[], Any],
        run_state: Any,
        logger: Logger,
    ) -> None:
        self._uow_factory = uow_factory
        self._run_state = run_state
        self._logger = logger

    def build_model(
        self, feature_slug: str, technique_inputs: dict[str, dict] | None = None,
        run_id: int | None = None,
    ) -> Result[CoverageBuildResult]:
        inputs = technique_inputs or {}

        with self._uow_factory() as uow:
            feature = uow.features.get_by_slug(feature_slug)
            if feature is None:
                return err(ErrorCode.FAILED_INTERNAL, f"Unknown feature: {feature_slug}")
            feature_id = feature["id"]

            requirements = uow.requirements.query(feature_id=feature_id, limit=200).items
            if not requirements:
                return err(
                    ErrorCode.FAILED_INTERNAL,
                    f"{feature_slug} has no testable requirements",
                    remediation="Run the requirements stage for this feature first.",
                )

            specs = [
                RequirementSpec(
                    requirement_id=r["id"], feature_slug=feature_slug,
                    category=r["category"],
                    risk_band=RiskBand(r["risk_band"]) if r["risk_band"] else None,
                    inputs=_technique_inputs(inputs.get(r["id"], {})),
                )
                for r in requirements
            ]

            # sequence_start is always 0, never len(existing).
            #
            # A coverage item is identified by its (requirement, test type) pair, so
            # the same requirements in the same order must produce the same ids -
            # and `upsert_many` overwrites by id, so collisions are the intent.
            #
            # Starting the sequence past the existing count gave rebuilt items new
            # ids, which changed the content hash, which invalidated the approval on
            # every rebuild. That is exactly the failure BR-U3-4.1 exists to prevent:
            # an operator re-running coverage to check something would have cost the
            # Test Lead a fresh approval of an unchanged model.
            #
            # Requirement order is stable because the query orders by id.
            model = derive_coverage(specs, sequence_start=0)

            digest = coverage_hash(model.items)
            previous = uow.coverage.latest_version(feature_id)
            version, changed = next_version(previous, digest)

            approval = uow.run_state.get_state(feature_slug, StageName.COVERAGE)
            invalidated = bool(changed and approval and approval["approved_by"])

            uow.coverage.upsert_many(model.items)
            uow.coverage.set_version([i.id for i in model.items], version, digest)

            gaps = 0
            for requirement_id in model.undetermined_boundaries:
                if uow.gaps.add_unless_open({
                    "category": "boundaries-undetermined", "subject": requirement_id,
                    "feature_slug": feature_slug, "detected_at": utc_now(),
                    "detail": "boundaries not stated in any source; no boundary cases planned",
                }, run_id) is not None:
                    gaps += 1

            for uncovered in find_uncovered(model, [r["id"] for r in requirements]):
                if uow.gaps.add_unless_open({
                    "category": "uncovered-requirement", "subject": uncovered,
                    "feature_slug": feature_slug, "detected_at": utc_now(),
                }, run_id) is not None:
                    gaps += 1

            forecast = compute_yield(
                model,
                {r["id"]: feature_slug for r in requirements},
                {r["id"]: RiskBand(r["risk_band"]) if r["risk_band"] else None
                 for r in requirements},
            )

            result = CoverageBuildResult(
                feature_slug=feature_slug, model_version=version, content_hash=digest,
                items=len(model.items),
                required_items=sum(1 for i in model.items if i.is_required),
                planned_total=model.planned_total,
                per_test_type=forecast.per_test_type,
                gaps_recorded=gaps,
                approval_invalidated=invalidated,
                previous_approver=approval["approved_by"] if approval else None,
                previous_approved_at=approval["approved_at"] if approval else None,
                disproportionate=forecast.disproportionate,
                zero_yield=forecast.zero_yield,
            )

        self._logger.info(
            "coverage model built", feature=feature_slug, version=version,
            planned=result.planned_total, invalidated=invalidated,
        )
        return ok(result)

    def approve_baseline(
        self, feature_slug: str, approver: str, role: Role
    ) -> Result[dict[str, Any]]:
        """Delegates the role restriction to U7.

        One place decides who may approve what. Four services with independent role
        checks would eventually disagree, and the disagreement would surface as one
        permitting what another refuses, with no obvious wrong answer to point at.
        """
        with self._uow_factory() as uow:
            feature = uow.features.get_by_slug(feature_slug)
            if feature is None:
                return err(ErrorCode.FAILED_INTERNAL, f"Unknown feature: {feature_slug}")
            version = uow.coverage.latest_version(feature["id"])
            if version is None:
                return err(
                    ErrorCode.FAILED_INTERNAL,
                    f"{feature_slug} has no coverage model to approve",
                    remediation="Run coverage_build for this feature first.",
                )
            _, digest = version

        return self._run_state.approve_stage(
            feature_slug, StageName.COVERAGE, approver, role, content_hash=digest
        )

    def apply_reduction(
        self, feature_slug: str, reason: str, decided_by: str,
        *, override: bool = False, run_id: int | None = None,
    ) -> Result[ReductionResult]:
        if not reason.strip():
            return err(
                ErrorCode.FAILED_INTERNAL, "A reduction requires a reason",
                remediation="State why coverage is being reduced for this feature.",
            )

        with self._uow_factory() as uow:
            feature = uow.features.get_by_slug(feature_slug)
            if feature is None:
                return err(ErrorCode.FAILED_INTERNAL, f"Unknown feature: {feature_slug}")
            feature_id = feature["id"]

            requirements = uow.requirements.query(feature_id=feature_id, limit=200).items
            bands = [r["risk_band"] for r in requirements if r["risk_band"]]
            aggregate = (
                RiskBand.CRITICAL if "critical" in bands
                else RiskBand.HIGH if "high" in bands
                else RiskBand.MEDIUM if "medium" in bands
                else RiskBand.LOW if bands else None
            )

            if aggregate in (RiskBand.HIGH, RiskBand.CRITICAL) and not override:
                # Permitted, but it must be deliberate - the Test Lead may have
                # context the rating lacks, and the disagreement must be visible.
                return err(
                    ErrorCode.REJECTED_ROLE_NOT_PERMITTED,
                    f"{feature_slug} is rated {aggregate.value}",
                    remediation=(
                        "Pass override=true to reduce it anyway. The contradiction "
                        "between the rating and the decision will be recorded."
                    ),
                    risk_band=aggregate.value,
                )

            items = uow.coverage.for_feature(feature_id)
            full_yield = sum(i["planned_count"] for i in items)
            version_row = uow.coverage.latest_version(feature_id)
            version = version_row[0] if version_row else 1

            spec = RequirementSpec(
                requirement_id=requirements[0]["id"] if requirements else "",
                feature_slug=feature_slug,
                category=requirements[0]["category"] if requirements else "business-rule",
                risk_band=aggregate, inputs=TechniqueInputs(),
            )
            technique = select_reduction(spec)
            factor = {"pairwise": 0.5, "each-choice": 0.5, "risk-based-pruning": 0.4}.get(
                technique.value, 1.0
            )
            reduced_yield = max(len(items), int(full_yield * factor))
            reduced_yield = min(reduced_yield, full_yield)

            uow.reductions.add({
                "feature_id": feature_id, "model_version": version,
                "technique": technique.value, "reason": reason,
                "full_yield": full_yield, "reduced_yield": reduced_yield,
                "decided_by": decided_by, "decided_at": utc_now(),
                "risk_band": aggregate.value if aggregate else None,
                "was_override": override,
            })

            uow.gaps.add_unless_open({
                "category": "reduced-depth", "subject": feature_slug,
                "feature_slug": feature_slug, "detected_at": utc_now(),
                "detail": f"{full_yield} -> {reduced_yield} planned cases via {technique.value}",
            }, run_id)

        self._logger.info(
            "coverage reduced", feature=feature_slug, technique=technique.value,
            full=full_yield, reduced=reduced_yield, override=override,
        )
        return ok(ReductionResult(
            feature_slug=feature_slug, technique=technique.value,
            full_yield=full_yield, reduced_yield=reduced_yield,
            was_override=override,
            risk_band=aggregate.value if aggregate else None,
        ))
