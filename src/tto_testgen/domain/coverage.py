"""D2 CoverageModeller - what must be tested, to what depth, and why.

BR-2. ISTQB-standard depth: one case per equivalence class, three values per
boundary, one per decision-table rule, 0-switch state coverage plus forbidden
transitions.

Volume is an outcome of this model, never a target. Nothing here pads toward a
figure: if the inputs yield 4,800 cases, that is the honest answer and the gap
report explains it.

PBT targets: PBT-03 - total yield equals the sum of per-feature yields; reduction
never increases planned count; every requirement has at least one coverage item.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from tto_testgen.domain.model import (
    CoverageItem,
    CoverageTechnique,
    EntityKind,
    RiskBand,
    TestType,
    encode_id,
)

#: BR-2.5. Above this many planned cases for one requirement, apply reduction.
REDUCTION_THRESHOLD = 50


class ReductionTechnique(str, Enum):
    PAIRWISE = "pairwise"
    EACH_CHOICE = "each-choice"
    RISK_BASED_PRUNING = "risk-based-pruning"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class TechniqueInputs:
    """What the analysis found for one requirement, as depth-relevant facts."""

    valid_classes: int = 0
    invalid_classes: int = 0
    boundaries: int = 0
    decision_rules: int = 0
    valid_transitions: int = 0
    forbidden_transitions: int = 0
    independent_parameters: int = 0
    boundaries_undetermined: bool = False


@dataclass(frozen=True, slots=True)
class RequirementSpec:
    """The subset of a requirement this module needs. Keeps D2 independent of
    storage shape and testable without fixtures."""

    requirement_id: str
    feature_slug: str
    category: str
    risk_band: RiskBand | None
    inputs: TechniqueInputs


@dataclass(slots=True)
class CoverageModel:
    version: str
    items: list[CoverageItem] = field(default_factory=list)
    reductions: list[dict[str, object]] = field(default_factory=list)
    undetermined_boundaries: list[str] = field(default_factory=list)

    @property
    def planned_total(self) -> int:
        return sum(item.planned_count for item in self.items)

    def per_requirement(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for item in self.items:
            totals[item.requirement_id] = totals.get(item.requirement_id, 0) + item.planned_count
        return totals


#: Which test types are candidates for each requirement category. Types not listed
#: still produce a coverage item with is_required=False, so the decision is visible.
CATEGORY_TYPES: dict[str, tuple[TestType, ...]] = {
    "business-rule": (
        TestType.FUNCTIONAL_POSITIVE,
        TestType.FUNCTIONAL_NEGATIVE,
        TestType.BOUNDARY,
        TestType.VALIDATION,
        TestType.ERROR_HANDLING,
    ),
    "api-contract": (
        TestType.API_CONTRACT,
        TestType.FUNCTIONAL_POSITIVE,
        TestType.FUNCTIONAL_NEGATIVE,
        TestType.VALIDATION,
        TestType.PERMISSIONS,
        TestType.ERROR_HANDLING,
    ),
    "ui-behaviour": (
        TestType.UI_BEHAVIOUR,
        TestType.FUNCTIONAL_POSITIVE,
        TestType.FUNCTIONAL_NEGATIVE,
        TestType.VALIDATION,
    ),
    "validation": (TestType.VALIDATION, TestType.BOUNDARY, TestType.FUNCTIONAL_NEGATIVE),
    "integration": (TestType.INTEGRATION, TestType.ERROR_HANDLING),
    "security": (TestType.PERMISSIONS, TestType.FUNCTIONAL_NEGATIVE),
    "performance": (),
    "accessibility": (TestType.UI_BEHAVIOUR,),
}

ALL_TYPES: tuple[TestType, ...] = tuple(TestType)


def select_technique(test_type: TestType, inputs: TechniqueInputs) -> CoverageTechnique:
    """Pick the design technique whose inputs the requirement actually supplies."""
    if test_type is TestType.BOUNDARY and inputs.boundaries:
        return CoverageTechnique.BOUNDARY_VALUE_ANALYSIS
    if inputs.valid_transitions or inputs.forbidden_transitions:
        return CoverageTechnique.STATE_TRANSITION
    if inputs.decision_rules:
        return CoverageTechnique.DECISION_TABLE
    if inputs.valid_classes or inputs.invalid_classes:
        return CoverageTechnique.EQUIVALENCE_PARTITIONING
    return CoverageTechnique.DIRECT


def planned_count(technique: CoverageTechnique, inputs: TechniqueInputs) -> int:
    """BR-2.1 to BR-2.4. The yield each technique produces."""
    if technique is CoverageTechnique.EQUIVALENCE_PARTITIONING:
        return inputs.valid_classes + inputs.invalid_classes
    if technique is CoverageTechnique.BOUNDARY_VALUE_ANALYSIS:
        # Three values per boundary: just below, at, just above.
        return 0 if inputs.boundaries_undetermined else 3 * inputs.boundaries
    if technique is CoverageTechnique.DECISION_TABLE:
        return inputs.decision_rules
    if technique is CoverageTechnique.STATE_TRANSITION:
        # 0-switch on valid transitions, plus every explicitly forbidden one.
        # Forbidden transitions are included because an unenforced prohibition is
        # a common and high-consequence defect.
        return inputs.valid_transitions + inputs.forbidden_transitions
    return 1


def _rationale(test_type: TestType, technique: CoverageTechnique, count: int) -> str:
    return (
        f"{test_type.value} via {technique.value}: {count} planned case(s) "
        f"per ISTQB-standard depth"
    )


def _not_required_reason(test_type: TestType, spec: RequirementSpec) -> str:
    return (
        f"{test_type.value} adds nothing for a {spec.category} requirement with the "
        f"available inputs"
    )


def select_reduction(spec: RequirementSpec) -> ReductionTechnique:
    """BR-2.5. Which reduction applies when expansion is unreasonable."""
    if spec.risk_band is RiskBand.LOW:
        return ReductionTechnique.RISK_BASED_PRUNING
    if spec.inputs.independent_parameters >= 3:
        return ReductionTechnique.PAIRWISE
    if spec.inputs.independent_parameters >= 2:
        return ReductionTechnique.EACH_CHOICE
    return ReductionTechnique.NONE


def _reduce(count: int, technique: ReductionTechnique) -> int:
    """Reduction never increases the planned count (PBT-03 invariant)."""
    if technique is ReductionTechnique.PAIRWISE:
        reduced = max(1, int(count**0.5) * 2)
    elif technique is ReductionTechnique.EACH_CHOICE:
        reduced = max(1, count // 2)
    elif technique is ReductionTechnique.RISK_BASED_PRUNING:
        reduced = max(1, int(count * 0.4))
    else:
        reduced = count
    return min(reduced, count)


def derive_coverage(
    specs: list[RequirementSpec],
    *,
    model_version: str = "1",
    sequence_start: int = 0,
) -> CoverageModel:
    """Produce the coverage model for a set of requirements."""
    model = CoverageModel(version=model_version)
    counter = sequence_start

    for spec in specs:
        candidate_types = CATEGORY_TYPES.get(spec.category, (TestType.FUNCTIONAL_POSITIVE,))
        required_items: list[CoverageItem] = []

        for test_type in ALL_TYPES:
            counter += 1
            item_id = encode_id(EntityKind.COVERAGE_ITEM, spec.feature_slug, counter)

            if test_type not in candidate_types:
                # BR-2.6: the row exists. An absent row and a deliberate exclusion
                # look identical unless the exclusion is recorded.
                model.items.append(
                    CoverageItem(
                        id=item_id,
                        requirement_id=spec.requirement_id,
                        test_type=test_type,
                        technique=CoverageTechnique.DIRECT,
                        planned_count=0,
                        rationale=_not_required_reason(test_type, spec),
                        is_required=False,
                        model_version=model_version,
                    )
                )
                continue

            technique = select_technique(test_type, spec.inputs)
            count = planned_count(technique, spec.inputs)
            if count == 0 and technique is CoverageTechnique.BOUNDARY_VALUE_ANALYSIS:
                # Boundaries stated as undetermined produce no cases and a gap.
                # Inventing plausible limits would assert a fiction.
                model.undetermined_boundaries.append(spec.requirement_id)
                model.items.append(
                    CoverageItem(
                        id=item_id,
                        requirement_id=spec.requirement_id,
                        test_type=test_type,
                        technique=technique,
                        planned_count=0,
                        rationale="boundaries undetermined; routed to gap report",
                        is_required=False,
                        model_version=model_version,
                    )
                )
                continue

            required_items.append(
                CoverageItem(
                    id=item_id,
                    requirement_id=spec.requirement_id,
                    test_type=test_type,
                    technique=technique,
                    planned_count=max(count, 1),
                    rationale=_rationale(test_type, technique, max(count, 1)),
                    is_required=True,
                    model_version=model_version,
                )
            )

        subtotal = sum(item.planned_count for item in required_items)
        if subtotal > REDUCTION_THRESHOLD:
            technique = select_reduction(spec)
            if technique is not ReductionTechnique.NONE:
                reduced_items = []
                for item in required_items:
                    reduced = _reduce(item.planned_count, technique)
                    reduced_items.append(
                        CoverageItem(
                            id=item.id,
                            requirement_id=item.requirement_id,
                            test_type=item.test_type,
                            technique=item.technique,
                            planned_count=reduced,
                            rationale=f"{item.rationale}; reduced by {technique.value}",
                            is_required=True,
                            reduction_applied=technique.value,
                            model_version=model_version,
                        )
                    )
                model.reductions.append(
                    {
                        "requirement_id": spec.requirement_id,
                        "technique": technique.value,
                        "before": subtotal,
                        "after": sum(i.planned_count for i in reduced_items),
                    }
                )
                required_items = reduced_items

        model.items.extend(required_items)

    return model


@dataclass(frozen=True, slots=True)
class YieldForecast:
    total: int
    per_feature: dict[str, int]
    per_test_type: dict[str, int]
    disproportionate: list[str] = field(default_factory=list)
    zero_yield: list[str] = field(default_factory=list)


def compute_yield(
    model: CoverageModel, feature_of: dict[str, str], risk_of: dict[str, RiskBand | None]
) -> YieldForecast:
    """BR-2.7 and FR-COV-04. Expected counts with the derivation visible.

    Flags features whose yield is disproportionate to their risk, and any feature
    forecast at zero - a testable feature with no planned coverage is a defect in
    the model, not a result.
    """
    per_feature: dict[str, int] = {}
    per_type: dict[str, int] = {}
    for item in model.items:
        feature = feature_of.get(item.requirement_id, "unknown")
        per_feature[feature] = per_feature.get(feature, 0) + item.planned_count
        per_type[item.test_type.value] = per_type.get(item.test_type.value, 0) + item.planned_count

    zero = sorted(f for f, count in per_feature.items() if count == 0)

    disproportionate = []
    if per_feature:
        mean = sum(per_feature.values()) / len(per_feature)
        for requirement_id, band in risk_of.items():
            feature = feature_of.get(requirement_id, "unknown")
            count = per_feature.get(feature, 0)
            if band is RiskBand.LOW and count > mean * 1.5:
                disproportionate.append(feature)
            elif band is RiskBand.CRITICAL and count < mean * 0.5:
                disproportionate.append(feature)

    return YieldForecast(
        total=model.planned_total,
        per_feature=per_feature,
        per_test_type=per_type,
        disproportionate=sorted(set(disproportionate)),
        zero_yield=zero,
    )


def find_uncovered(model: CoverageModel, requirement_ids: list[str]) -> list[str]:
    """FR-COV-05. Requirements with no required coverage item."""
    covered = {
        item.requirement_id for item in model.items if item.is_required and item.planned_count > 0
    }
    return sorted(r for r in requirement_ids if r not in covered)
