"""The 10 U3 properties from business-logic-model.md section 4.

Three of them pin down exactly what "modifying an approved model" means. The Test
Lead's approval rests on that definition, and a definition that holds only for the
examples someone thought of is not a definition.
"""

from __future__ import annotations

from dataclasses import dataclass

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tto_testgen.domain.atomicity import check as check_atomicity
from tto_testgen.domain.classification import RiskFactor, UNAVAILABLE, rate_risk
from tto_testgen.domain.coverage_hash import canonical_payload, coverage_hash, next_version
from tto_testgen.services.requirements import (
    CHANGE_BANDS,
    COMPLEXITY_BANDS,
    INTEGRATION_BANDS,
    band,
)

SETTINGS = settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)

thresholds = st.sampled_from([COMPLEXITY_BANDS, INTEGRATION_BANDS, CHANGE_BANDS])
ids = st.builds(lambda n: f"CI-CHECKOUT-{n:05d}", st.integers(1, 9999))
test_types = st.sampled_from(["boundary", "validation", "api-contract", "ui-behaviour"])
techniques = st.sampled_from(["boundary-value-analysis", "decision-table", "direct"])


@dataclass
class Item:
    id: str
    requirement_id: str = "TR-CHECKOUT-00001"
    test_type: str = "boundary"
    technique: str = "direct"
    planned_count: int = 1
    is_required: bool = True
    rationale: str = ""


items_strategy = st.builds(
    Item,
    id=ids, test_type=test_types, technique=techniques,
    planned_count=st.integers(0, 50),
    is_required=st.booleans(),
    rationale=st.text(max_size=40),
).filter(lambda i: i.is_required or i.planned_count == 0)

item_lists = st.lists(items_strategy, max_size=12, unique_by=lambda i: i.id)


class TestRiskBanding:
    @SETTINGS
    @given(a=st.integers(0, 500), b=st.integers(0, 500), t=thresholds)
    def test_property_1_banding_is_monotonic(self, a, b, t):
        if a <= b:
            assert band(a, t) <= band(b, t)

    @SETTINGS
    @given(value=st.integers(0, 5000), t=thresholds)
    def test_property_2_banding_is_always_one_to_five(self, value, t):
        assert 1 <= band(value, t) <= 5

    @SETTINGS
    @given(
        scores=st.dictionaries(
            st.sampled_from(list(RiskFactor)),
            st.one_of(st.none(), st.integers(1, 5)),
            min_size=1,
        )
    )
    def test_property_3_an_unavailable_factor_is_never_rendered_as_zero(self, scores):
        """Zero commits and no commit data are different facts.

        Scoring the second as the first reads as "stable" when it means "unknown".
        """
        rating = rate_risk(scores)
        for factor, value in scores.items():
            if value is None:
                assert rating.factors[factor.value] == UNAVAILABLE
                assert rating.factors[factor.value] != 0


class TestCoverageHash:
    """What "modifying an approved model" means."""

    @SETTINGS
    @given(items=item_lists)
    def test_property_4_order_does_not_affect_the_hash(self, items):
        assert coverage_hash(items) == coverage_hash(list(reversed(items)))

    @SETTINGS
    @given(items=item_lists, prose=st.text(max_size=60))
    def test_property_5_rationale_never_affects_the_hash(self, items, prose):
        # Requiring re-approval for a typo fix trains the Test Lead to approve
        # without reading.
        reworded = [
            Item(i.id, i.requirement_id, i.test_type, i.technique,
                 i.planned_count, i.is_required, prose)
            for i in items
        ]
        assert coverage_hash(items) == coverage_hash(reworded)

    @SETTINGS
    @given(items=st.lists(items_strategy, min_size=1, max_size=8,
                          unique_by=lambda i: i.id))
    def test_property_6_flipping_is_required_changes_the_hash(self, items):
        """A test type flipping to not-required changes coverage materially while
        leaving the planned total unchanged. A counts-only digest would miss it."""
        before = coverage_hash(items)
        flipped = list(items)
        first = flipped[0]
        flipped[0] = Item(
            first.id, first.requirement_id, first.test_type, first.technique,
            0 if first.is_required else first.planned_count,
            not first.is_required, first.rationale,
        )
        if (first.planned_count, first.is_required) != (
            flipped[0].planned_count, flipped[0].is_required
        ):
            assert coverage_hash(flipped) != before

    @SETTINGS
    @given(items=item_lists)
    def test_property_7_the_payload_carries_exactly_six_fields(self, items):
        for row in canonical_payload(items):
            assert len(row) == 6


class TestVersioning:
    @SETTINGS
    @given(
        version=st.integers(1, 100),
        digest=st.text(alphabet="0123456789abcdef", min_size=64, max_size=64),
    )
    def test_property_8_an_unchanged_hash_reuses_the_version(self, version, digest):
        assert next_version((version, digest), digest) == (version, False)

    @SETTINGS
    @given(
        version=st.integers(1, 100),
        old=st.text(alphabet="0123456789abcdef", min_size=64, max_size=64),
        new=st.text(alphabet="0123456789abcdef", min_size=64, max_size=64),
    )
    def test_property_9_a_changed_hash_increments_exactly_once(self, version, old, new):
        if old != new:
            assert next_version((version, old), new) == (version + 1, True)


class TestAtomicity:
    _VERBS_ABSENT = st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=60
    ).filter(lambda s: s.strip() and " and " not in s and " or " not in s)

    @SETTINGS
    @given(statement=_VERBS_ABSENT)
    def test_property_10_a_statement_with_no_conjunction_is_never_rejected(self, statement):
        """The heuristic errs toward acceptance by design.

        A false rejection costs one resubmission; a false acceptance costs a
        permanently untraceable case.
        """
        assert check_atomicity(statement).is_atomic

    @SETTINGS
    @given(statement=st.text(min_size=1, max_size=80))
    def test_the_verdict_is_deterministic(self, statement):
        assert check_atomicity(statement) == check_atomicity(statement)

    @SETTINGS
    @given(statement=st.text(min_size=1, max_size=80))
    def test_force_atomic_always_accepts(self, statement):
        assert check_atomicity(statement, force_atomic=True).is_atomic
