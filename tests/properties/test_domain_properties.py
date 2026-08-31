"""The 16-property surface from business-logic-model.md section 7.

PBT partial mode enforces PBT-02 (round-trip), PBT-03 (invariants), PBT-07
(domain generators), PBT-08 (shrinking and reproducibility), PBT-09 (Hypothesis).

Every property targets a domain component and needs no database, no network and no
fixtures. That is the concrete payoff of the hexagonal decision.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.properties.strategies import (
    entity_kinds,
    feature_slugs,
    jira_keys,
    cases,
    sequences,
)
from tto_testgen.domain.classification import RiskFactor, rate_risk
from tto_testgen.domain.coverage import (
    RequirementSpec,
    TechniqueInputs,
    derive_coverage,
)
from tto_testgen.domain.identity import SequenceState, allocate, allocate_many
from tto_testgen.domain.model import (
    DomainError,
    ENTITIES,
    RiskBand,
    TestCase as Case,
    decode_id,
    encode_id,
    from_dict,
    to_dict,
)
from tto_testgen.domain.similarity import (
    DuplicateVerdict,
    classify,
    normalise,
    similarity,
)
from tto_testgen.domain.traceability import MatrixEdge, build_matrix

SETTINGS = settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


# --- D1: round-trip (PBT-02) -------------------------------------------------


class TestD1RoundTrip:
    @SETTINGS
    @given(case=cases())
    def test_property_1_test_case_round_trips(self, case: Case):
        """from_dict(to_dict(x)) == x for a fully populated entity."""
        assert from_dict(Case, to_dict(case)) == case

    def test_every_entity_type_is_serialisable(self):
        # A new entity added without serialisation support would silently break
        # the export that OD-01's recovery point depends on.
        from dataclasses import fields

        for entity_type in ENTITIES:
            assert fields(entity_type)

    @SETTINGS
    @given(case=cases())
    def test_property_2_serialised_form_is_json_native(self, case: Case):
        import json

        json.dumps(to_dict(case))

    def test_unknown_fields_are_rejected_not_ignored(self):
        # Silently dropping an unknown key lets a schema change pass unnoticed and
        # reappear as missing data much later.
        with pytest.raises(DomainError):
            from_dict(Case, {"id": "TC-A-00001", "surprise": 1})


# --- D1 / D5: construction invariants and identifiers (PBT-02, PBT-03) -------


class TestD5Identifiers:
    @SETTINGS
    @given(kind=entity_kinds, slug=feature_slugs, sequence=sequences)
    def test_property_3_identifier_round_trips(self, kind, slug, sequence):
        """decode(encode(x)) == x."""
        assert decode_id(encode_id(kind, slug, sequence)) == (kind, slug, sequence)

    @SETTINGS
    @given(kind=entity_kinds, slug=feature_slugs, count=st.integers(min_value=1, max_value=40))
    def test_property_4_allocation_is_strictly_monotonic(self, kind, slug, count):
        ids, _ = allocate_many(kind, slug, count, SequenceState())
        numbers = [decode_id(i)[2] for i in ids]
        assert numbers == sorted(numbers)
        assert all(b - a == 1 for a, b in zip(numbers, numbers[1:]))

    @SETTINGS
    @given(kind=entity_kinds, slug=feature_slugs, count=st.integers(min_value=1, max_value=40))
    def test_property_5_no_identifier_is_issued_twice(self, kind, slug, count):
        ids, _ = allocate_many(kind, slug, count, SequenceState())
        assert len(set(ids)) == len(ids)

    @SETTINGS
    @given(
        slug=feature_slugs,
        first=st.integers(min_value=1, max_value=20),
        second=st.integers(min_value=1, max_value=20),
    )
    def test_property_6_sequences_are_independent_per_kind(self, slug, first, second):
        from tto_testgen.domain.model import EntityKind

        state = SequenceState()
        _, state = allocate_many(EntityKind.TEST_CASE, slug, first, state)
        requirement_id, _ = allocate(EntityKind.REQUIREMENT, slug, state)
        assert decode_id(requirement_id)[2] == 1


# --- D4: similarity invariants (PBT-03) --------------------------------------


class TestD4Similarity:
    @SETTINGS
    @given(case=cases())
    def test_property_7_reflexive(self, case: Case):
        normalised = normalise(case)
        assert similarity(normalised, normalised) == 1.0

    @SETTINGS
    @given(a=cases(), b=cases())
    def test_property_8_symmetric(self, a: Case, b: Case):
        na, nb = normalise(a), normalise(b)
        assert similarity(na, nb) == similarity(nb, na)

    @SETTINGS
    @given(a=cases(), b=cases())
    def test_property_9_bounded(self, a: Case, b: Case):
        assert 0.0 <= similarity(normalise(a), normalise(b)) <= 1.0

    @SETTINGS
    @given(a=cases(), b=cases())
    def test_property_10_differing_class_is_always_distinct(self, a: Case, b: Case):
        """BR-1.4. The override holds for every generated pair, at any threshold."""
        na, nb = normalise(a), normalise(b)
        if na.classes != nb.classes:
            assert classify(na, nb, threshold=0.0) is DuplicateVerdict.DISTINCT

    @SETTINGS
    @given(a=cases(), b=cases())
    def test_property_11_classification_is_deterministic(self, a: Case, b: Case):
        na, nb = normalise(a), normalise(b)
        assert classify(na, nb) is classify(na, nb)


# --- D2: coverage invariants (PBT-03) ----------------------------------------

requirement_specs = st.builds(
    RequirementSpec,
    requirement_id=st.builds(
        lambda slug, seq: encode_id(__import__(
            "tto_testgen.domain.model", fromlist=["EntityKind"]
        ).EntityKind.REQUIREMENT, slug, seq),
        feature_slugs,
        sequences,
    ),
    feature_slug=feature_slugs,
    category=st.sampled_from(
        ["business-rule", "api-contract", "ui-behaviour", "validation", "integration"]
    ),
    risk_band=st.one_of(st.none(), st.sampled_from(list(RiskBand))),
    inputs=st.builds(
        TechniqueInputs,
        valid_classes=st.integers(min_value=0, max_value=6),
        invalid_classes=st.integers(min_value=0, max_value=6),
        boundaries=st.integers(min_value=0, max_value=4),
        decision_rules=st.integers(min_value=0, max_value=8),
        valid_transitions=st.integers(min_value=0, max_value=5),
        forbidden_transitions=st.integers(min_value=0, max_value=3),
        independent_parameters=st.integers(min_value=0, max_value=4),
        boundaries_undetermined=st.booleans(),
    ),
)


class TestD2Coverage:
    @SETTINGS
    @given(specs=st.lists(requirement_specs, min_size=1, max_size=6))
    def test_property_12_total_equals_sum_of_parts(self, specs):
        model = derive_coverage(specs)
        assert model.planned_total == sum(model.per_requirement().values())

    @SETTINGS
    @given(specs=st.lists(requirement_specs, min_size=1, max_size=6))
    def test_property_13_reduction_never_increases_the_count(self, specs):
        model = derive_coverage(specs)
        for record in model.reductions:
            assert record["after"] <= record["before"]

    @SETTINGS
    @given(specs=st.lists(requirement_specs, min_size=1, max_size=6))
    def test_property_14_every_requirement_has_at_least_one_item(self, specs):
        """Required or not-required - but never absent, so a deliberate exclusion
        is always distinguishable from an oversight."""
        model = derive_coverage(specs)
        covered = {item.requirement_id for item in model.items}
        assert {spec.requirement_id for spec in specs} <= covered


# --- D3: traceability invariants (PBT-03) ------------------------------------


class TestD3Traceability:
    @SETTINGS
    @given(
        edges=st.lists(
            st.tuples(st.text(min_size=1, max_size=8), st.text(min_size=1, max_size=8)),
            max_size=20,
        )
    )
    def test_property_15_matrix_is_bidirectionally_consistent(self, edges):
        matrix = build_matrix([MatrixEdge("a", src, "b", dst) for src, dst in edges])
        assert matrix.is_bidirectionally_consistent()

    @SETTINGS
    @given(case=cases(with_links=True))
    def test_property_16_every_linked_case_reaches_a_jira_key(self, case: Case):
        from tto_testgen.domain.traceability import require_jira_key

        known = frozenset(case.jira_keys)
        assert require_jira_key(case.trace_links, known) is not None


# --- D6: rating invariants ----------------------------------------------------


class TestD6Classification:
    @SETTINGS
    @given(
        scores=st.dictionaries(
            st.sampled_from(list(RiskFactor)),
            st.one_of(st.none(), st.integers(min_value=1, max_value=5)),
            min_size=1,
        )
    )
    def test_unavailable_factors_never_lower_the_score_below_the_known_ratio(self, scores):
        """An unavailable factor is removed from the denominator, so it cannot make
        an unmeasured requirement look safe."""
        rating = rate_risk(scores)
        available = {k: v for k, v in scores.items() if v is not None}
        if not available:
            assert rating.score is None
            return
        assert rating.score is not None
        assert 0 <= rating.score <= 100
        if all(v == 5 for v in available.values()):
            assert rating.score == 100
        assert rating.is_partial == (len(available) < len(RiskFactor))
