"""D6 Classifier - risk rating and automatability, with reasons rather than verdicts.

BR-4 and BR-5.

Risk: four weighted factors, banded. An unavailable factor is removed from both
numerator and denominator and the rating flagged partial - never scored zero,
because scoring an unknown as zero makes an unmeasured requirement look safe.

Automatability: an ordered decision list, first match wins. Every verdict cites the
rule number that produced it, so "the classifier said 0.63" is never the answer to
an automation engineer asking why a test exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from tto_testgen.domain.model import AutomatabilityClass, RiskBand


class RiskFactor(str, Enum):
    BUSINESS_CRITICALITY = "business_criticality"
    COMPLEXITY = "complexity"
    INTEGRATION_SURFACE = "integration_surface"
    CHANGE_FREQUENCY = "change_frequency"


#: BR-4.1. Criticality dominates deliberately: a defect in a revenue or auth path
#: costs more than a defect in a rarely-touched administrative screen, whatever
#: their relative churn.
WEIGHTS: dict[RiskFactor, int] = {
    RiskFactor.BUSINESS_CRITICALITY: 3,
    RiskFactor.COMPLEXITY: 2,
    RiskFactor.INTEGRATION_SURFACE: 2,
    RiskFactor.CHANGE_FREQUENCY: 1,
}

UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class RiskRating:
    score: int | None
    band: RiskBand | None
    factors: dict[str, object]
    is_partial: bool
    note: str = ""


def band_for(score: int) -> RiskBand:
    """BR-4.3."""
    if score <= 25:
        return RiskBand.LOW
    if score <= 50:
        return RiskBand.MEDIUM
    if score <= 75:
        return RiskBand.HIGH
    return RiskBand.CRITICAL


def rate_risk(signals: dict[RiskFactor, int | None]) -> RiskRating:
    """BR-4.2 and BR-4.4. Weighted ratio over the factors actually available.

    Removing an unavailable factor from the denominator preserves the ratio among
    what is known. Diluting toward zero instead would let a missing signal read as
    a low risk, which is precisely backwards.
    """
    available = {
        factor: value
        for factor, value in signals.items()
        if value is not None
    }
    for factor, value in available.items():
        if not 1 <= value <= 5:
            raise ValueError(f"{factor.value} must be scored 1-5, got {value}")

    recorded: dict[str, object] = {
        factor.value: signals.get(factor) if signals.get(factor) is not None else UNAVAILABLE
        for factor in RiskFactor
    }
    is_partial = len(available) < len(RiskFactor)

    if not available:
        return RiskRating(
            score=None,
            band=None,
            factors=recorded,
            is_partial=True,
            note="no risk signals available",
        )

    weighted = sum(value * WEIGHTS[factor] for factor, value in available.items())
    maximum = sum(5 * WEIGHTS[factor] for factor in available)
    score = round(weighted / maximum * 100)
    note = (
        f"rated on {len(available)} of {len(RiskFactor)} factors"
        if is_partial
        else "rated on all factors"
    )
    return RiskRating(
        score=score, band=band_for(score), factors=recorded, is_partial=is_partial, note=note
    )


# ---------------------------------------------------------------------------
# BR-5 automatability
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CaseSignals:
    """What the decision list needs to know about a case."""

    requires_visual_judgement: bool = False
    requires_external_step: bool = False
    requires_unprovisionable_data: bool = False
    is_exploratory: bool = False
    is_api_case: bool = False
    api_shape_source: str = "inferred"
    is_ui_case: bool = False
    all_elements_have_locators: bool = False
    all_locators_verified: bool = False
    has_fragile_locator_without_alternative: bool = False


@dataclass(frozen=True, slots=True)
class AutomatabilityVerdict:
    verdict: AutomatabilityClass
    rule_number: int
    reason: str
    annotation: str | None = None
    overridden_by: str | None = None
    override_reason: str | None = None


@dataclass(frozen=True, slots=True)
class _Rule:
    number: int
    text: str
    verdict: AutomatabilityClass
    annotation: str | None
    matches: object  # Callable[[CaseSignals], bool]


#: BR-5.1. Order is significant: first match wins.
DECISION_LIST: tuple[_Rule, ...] = (
    _Rule(1, "requires visual or aesthetic judgement", AutomatabilityClass.MANUAL_ONLY, None,
          lambda s: s.requires_visual_judgement),
    _Rule(2, "requires a step outside the application", AutomatabilityClass.MANUAL_ONLY, None,
          lambda s: s.requires_external_step),
    _Rule(3, "requires data that cannot be provisioned programmatically",
          AutomatabilityClass.MANUAL_ONLY, None, lambda s: s.requires_unprovisionable_data),
    _Rule(4, "is exploratory or usability-oriented by nature", AutomatabilityClass.MANUAL_ONLY,
          None, lambda s: s.is_exploratory),
    _Rule(5, "API case with a specified contract", AutomatabilityClass.AUTOMATABLE, None,
          lambda s: s.is_api_case and s.api_shape_source == "specified"),
    _Rule(6, "API case with an inferred contract", AutomatabilityClass.AUTOMATABLE,
          "contract-inferred",
          lambda s: s.is_api_case and s.api_shape_source == "inferred"),
    _Rule(7, "UI case with every element verified", AutomatabilityClass.AUTOMATABLE, None,
          lambda s: s.is_ui_case and s.all_elements_have_locators and s.all_locators_verified),
    _Rule(8, "UI case with locators, some unverified", AutomatabilityClass.AUTOMATABLE,
          "unverified-locator",
          lambda s: s.is_ui_case and s.all_elements_have_locators
          and not s.all_locators_verified),
    _Rule(9, "UI case with a fragile locator and no alternative",
          AutomatabilityClass.NEEDS_REVIEW, "fragile-locator",
          lambda s: s.is_ui_case and s.has_fragile_locator_without_alternative),
)

_FALLBACK = _Rule(10, "no rule matched", AutomatabilityClass.NEEDS_REVIEW, None, lambda s: True)


def classify_automatability(signals: CaseSignals) -> AutomatabilityVerdict:
    """BR-5.1 and BR-5.2. First matching rule decides; the verdict cites it."""
    for rule in DECISION_LIST:
        if rule.matches(signals):  # type: ignore[operator]
            return AutomatabilityVerdict(
                verdict=rule.verdict,
                rule_number=rule.number,
                reason=f"rule {rule.number}: {rule.text}",
                annotation=rule.annotation,
            )
    return AutomatabilityVerdict(
        verdict=_FALLBACK.verdict,
        rule_number=_FALLBACK.number,
        reason=f"rule {_FALLBACK.number}: {_FALLBACK.text}",
    )


def apply_override(
    verdict: AutomatabilityVerdict, actor: str, reason: str, new_class: AutomatabilityClass
) -> AutomatabilityVerdict:
    """BR-5.3. A human decision, recorded and never recomputed away."""
    if not actor.strip() or not reason.strip():
        raise ValueError("An override requires both an actor and a reason")
    return AutomatabilityVerdict(
        verdict=new_class,
        rule_number=verdict.rule_number,
        reason=verdict.reason,
        annotation=verdict.annotation,
        overridden_by=actor,
        override_reason=reason,
    )
