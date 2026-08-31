"""Example-based coverage of every documented rule in business-rules.md (BR-1..BR-9)."""

from datetime import datetime, timedelta, timezone

import pytest

from tto_testgen.domain.classification import (
    CaseSignals,
    RiskFactor,
    UNAVAILABLE,
    apply_override,
    band_for,
    classify_automatability,
    rate_risk,
)
from tto_testgen.domain.coverage import (
    RequirementSpec,
    TechniqueInputs,
    compute_yield,
    derive_coverage,
    find_uncovered,
    planned_count,
    select_technique,
)
from tto_testgen.domain.identity import (
    SequenceExhausted,
    SequenceState,
    allocate,
    allocate_many,
    stable_id_for,
)
from tto_testgen.domain.impact import ChangedRef, TraceEdge, map_impact
from tto_testgen.domain.model import (
    AutomatabilityClass,
    ChangeClassification,
    CoverageTechnique,
    DomainError,
    EntityKind,
    LinkType,
    RiskBand,
    TestCase as Case,
    TestData as Data,
    TestStep as Step,
    TestType as Kind,
    TraceLink,
    decode_id,
    encode_id,
)
from tto_testgen.domain.similarity import (
    DuplicateVerdict,
    bucket_key,
    classify,
    normalise,
    similarity,
)
from tto_testgen.domain.traceability import (
    CommitRecord,
    Gap,
    build_matrix,
    derive_key_from_commits,
    link_counts_by_type,
    require_jira_key,
)
from tto_testgen.domain.validation import validate_batch, validate_case
from tto_testgen.platform.result import ErrorCode

NOW = datetime(2026, 8, 29, tzinfo=timezone.utc)


def make_case(seq=1, *, steps=None, action="Enter quantity 5", expected="Accepted",
              cls="valid-mid-range", key="PAY-12", links=True):
    trace = (
        [TraceLink("test_case", "x", key, LinkType.DIRECT_STORY, resolved_jira_key=key)]
        if links
        else []
    )
    return Case(
        id=encode_id(EntityKind.TEST_CASE, "checkout", seq),
        feature_id=1,
        coverage_item_id=encode_id(EntityKind.COVERAGE_ITEM, "checkout", 1),
        title=f"case {seq}",
        test_type=Kind.BOUNDARY,
        steps=[Step(1, action, expected)] if steps is None else steps,
        expected_result="ok",
        test_data=[Data("qty", "5", cls)],
        trace_links=trace,
    )


class TestBR1DuplicateDetection:
    def test_normalisation_lowercases_and_collapses_whitespace(self):
        a = normalise(make_case(action="Enter   QUANTITY 5", expected="Accepted."))
        b = normalise(make_case(action="enter quantity 5", expected="accepted"))
        assert a.text == b.text

    def test_step_order_is_preserved_not_sorted(self):
        # Two cases doing the same things in a different order are different tests;
        # one may exist precisely to check that order matters.
        forward = make_case(steps=[Step(1, "Add item", "Added"), Step(2, "Pay", "Paid")])
        reverse = make_case(steps=[Step(1, "Pay", "Paid"), Step(2, "Add item", "Added")])
        assert normalise(forward).text != normalise(reverse).text

    def test_identical_cases_are_identical(self):
        assert classify(normalise(make_case(1)), normalise(make_case(2))) is DuplicateVerdict.IDENTICAL

    def test_differing_equivalence_class_is_always_material(self):
        # BR-1.4. Two boundary cases at opposite ends share nearly every word; a
        # pure text threshold would reject one and halve the boundary coverage.
        low = normalise(make_case(cls="just-below-minimum"))
        high = normalise(make_case(cls="just-above-maximum"))
        assert similarity(low, high) == 1.0
        assert classify(low, high) is DuplicateVerdict.DISTINCT

    def test_clearly_different_cases_are_distinct(self):
        a = normalise(make_case(action="Enter quantity 5", expected="Accepted"))
        b = normalise(make_case(action="Delete the account permanently", expected="Account removed"))
        assert classify(a, b) is DuplicateVerdict.DISTINCT

    def test_threshold_is_honoured(self):
        a = normalise(make_case(action="alpha beta gamma delta epsilon"))
        b = normalise(make_case(action="alpha beta gamma delta zeta"))
        assert classify(a, b, threshold=0.01) is DuplicateVerdict.NEAR_DUPLICATE
        assert classify(a, b, threshold=0.99) is DuplicateVerdict.DISTINCT

    def test_invalid_threshold_is_rejected(self):
        with pytest.raises(ValueError):
            classify(normalise(make_case()), normalise(make_case()), threshold=1.5)

    def test_bucket_key_groups_by_feature_type_and_step_count(self):
        assert bucket_key(make_case(), "checkout") == "checkout|boundary|1"


class TestBR2CoverageDepth:
    def test_equivalence_partitioning_yields_one_per_class(self):
        inputs = TechniqueInputs(valid_classes=3, invalid_classes=2)
        assert planned_count(CoverageTechnique.EQUIVALENCE_PARTITIONING, inputs) == 5

    def test_boundary_analysis_yields_three_per_boundary(self):
        inputs = TechniqueInputs(boundaries=2)
        assert planned_count(CoverageTechnique.BOUNDARY_VALUE_ANALYSIS, inputs) == 6

    def test_decision_table_yields_one_per_rule(self):
        assert planned_count(CoverageTechnique.DECISION_TABLE, TechniqueInputs(decision_rules=7)) == 7

    def test_state_transition_includes_forbidden_transitions(self):
        # An unenforced prohibition is a common, high-consequence defect.
        inputs = TechniqueInputs(valid_transitions=4, forbidden_transitions=3)
        assert planned_count(CoverageTechnique.STATE_TRANSITION, inputs) == 7

    def test_undetermined_boundaries_produce_no_cases_and_a_gap(self):
        model = derive_coverage(
            [RequirementSpec("TR-X-00001", "x", "validation", None,
                             TechniqueInputs(boundaries=2, boundaries_undetermined=True))]
        )
        assert model.undetermined_boundaries == ["TR-X-00001"]

    def test_not_required_rows_are_kept(self):
        # BR-2.6. An absent row and a deliberate exclusion look identical unless
        # the exclusion is recorded.
        model = derive_coverage(
            [RequirementSpec("TR-A-00001", "a", "business-rule", None,
                             TechniqueInputs(valid_classes=1))]
        )
        not_required = [i for i in model.items if not i.is_required]
        assert not_required
        assert all(i.rationale for i in not_required)
        assert all(i.planned_count == 0 for i in not_required)

    def test_reduction_never_increases_the_count(self):
        spec = RequirementSpec("TR-B-00001", "b", "api-contract", RiskBand.LOW,
                               TechniqueInputs(valid_classes=20, invalid_classes=20,
                                               decision_rules=30, independent_parameters=3))
        model = derive_coverage([spec])
        for record in model.reductions:
            assert record["after"] <= record["before"]

    def test_reduction_is_recorded_not_silent(self):
        spec = RequirementSpec("TR-B-00001", "b", "api-contract", RiskBand.LOW,
                               TechniqueInputs(valid_classes=30, invalid_classes=30,
                                               independent_parameters=3))
        model = derive_coverage([spec])
        assert model.reductions
        assert model.reductions[0]["technique"]

    def test_yield_forecast_flags_zero_yield_features(self):
        model = derive_coverage(
            [RequirementSpec("TR-P-00001", "perf", "performance", None, TechniqueInputs())]
        )
        forecast = compute_yield(model, {"TR-P-00001": "perf"}, {"TR-P-00001": None})
        assert "perf" in forecast.zero_yield

    def test_find_uncovered_names_requirements_with_no_coverage(self):
        model = derive_coverage(
            [RequirementSpec("TR-A-00001", "a", "business-rule", None,
                             TechniqueInputs(valid_classes=1))]
        )
        assert find_uncovered(model, ["TR-A-00001", "TR-A-00002"]) == ["TR-A-00002"]

    def test_technique_selection_prefers_available_inputs(self):
        assert select_technique(Kind.BOUNDARY, TechniqueInputs(boundaries=1)) is (
            CoverageTechnique.BOUNDARY_VALUE_ANALYSIS
        )
        assert select_technique(Kind.VALIDATION, TechniqueInputs()) is CoverageTechnique.DIRECT


class TestBR3CommitDerivation:
    def test_most_recent_known_key_wins(self):
        recent = CommitRecord("a" * 40, "PAY-12 fix", NOW - timedelta(days=10), 40)
        older = CommitRecord("b" * 40, "PAY-99 initial", NOW - timedelta(days=30), 900)
        resolution = derive_key_from_commits(
            "src/pay.py", [recent, older], frozenset({"PAY-12", "PAY-99"}), now=NOW
        )
        assert resolution.jira_key == "PAY-12"
        assert resolution.link_type is LinkType.DERIVED_FROM_COMMIT

    def test_alternatives_are_retained(self):
        recent = CommitRecord("a" * 40, "PAY-12 fix", NOW - timedelta(days=10))
        older = CommitRecord("b" * 40, "PAY-99 initial", NOW - timedelta(days=30))
        resolution = derive_key_from_commits(
            "src/pay.py", [recent, older], frozenset({"PAY-12", "PAY-99"}), now=NOW
        )
        assert [a["jira_key"] for a in resolution.alternatives] == ["PAY-99"]

    def test_selection_basis_is_recorded(self):
        commit = CommitRecord("a" * 40, "PAY-12 fix", NOW - timedelta(days=10))
        resolution = derive_key_from_commits(
            "src/pay.py", [commit], frozenset({"PAY-12"}), now=NOW
        )
        assert resolution.selection_basis

    def test_commits_outside_the_window_are_ignored(self):
        # Without the window, a five-year-old refactor becomes the provenance of
        # today's behaviour: technically present, substantively meaningless.
        ancient = CommitRecord("c" * 40, "PAY-1 first", NOW - timedelta(days=900))
        result = derive_key_from_commits(
            "src/old.py", [ancient], frozenset({"PAY-1"}), now=NOW
        )
        assert isinstance(result, Gap)

    def test_keys_not_in_the_ingested_set_do_not_count(self):
        commit = CommitRecord("a" * 40, "NOPE-9 change", NOW - timedelta(days=5))
        result = derive_key_from_commits(
            "src/x.py", [commit], frozenset({"PAY-12"}), now=NOW
        )
        assert isinstance(result, Gap)

    def test_gap_records_what_was_attempted(self):
        result = derive_key_from_commits("src/x.py", [], frozenset(), now=NOW)
        assert isinstance(result, Gap)
        assert "direct-story" in result.attempted

    def test_derived_links_are_counted_separately(self):
        links = [
            TraceLink("c", "1", "PAY-1", LinkType.DIRECT_STORY, resolved_jira_key="PAY-1"),
            TraceLink("c", "2", "PAY-2", LinkType.DERIVED_FROM_COMMIT,
                      selection_basis="most recent", resolved_jira_key="PAY-2"),
        ]
        counts = link_counts_by_type(links)
        assert counts["direct-story"] == 1
        assert counts["derived-from-commit"] == 1


class TestBR4RiskRating:
    def test_criticality_dominates(self):
        high_crit = rate_risk({RiskFactor.BUSINESS_CRITICALITY: 5, RiskFactor.COMPLEXITY: 1,
                               RiskFactor.INTEGRATION_SURFACE: 1, RiskFactor.CHANGE_FREQUENCY: 1})
        high_churn = rate_risk({RiskFactor.BUSINESS_CRITICALITY: 1, RiskFactor.COMPLEXITY: 1,
                                RiskFactor.INTEGRATION_SURFACE: 1, RiskFactor.CHANGE_FREQUENCY: 5})
        assert high_crit.score > high_churn.score

    def test_unavailable_factor_is_flagged_not_zeroed(self):
        rating = rate_risk({RiskFactor.BUSINESS_CRITICALITY: 5, RiskFactor.COMPLEXITY: 5,
                            RiskFactor.INTEGRATION_SURFACE: None, RiskFactor.CHANGE_FREQUENCY: None})
        assert rating.is_partial
        assert rating.factors["integration_surface"] == UNAVAILABLE
        # Scoring the unknown as zero would make an unmeasured requirement look safe.
        assert rating.band is RiskBand.CRITICAL

    def test_no_signals_yields_no_score(self):
        rating = rate_risk({f: None for f in RiskFactor})
        assert rating.score is None and rating.band is None and rating.is_partial

    def test_every_factor_is_recorded(self):
        rating = rate_risk({RiskFactor.BUSINESS_CRITICALITY: 3})
        assert set(rating.factors) == {f.value for f in RiskFactor}

    @pytest.mark.parametrize(
        "score,band",
        [(0, RiskBand.LOW), (25, RiskBand.LOW), (26, RiskBand.MEDIUM), (50, RiskBand.MEDIUM),
         (51, RiskBand.HIGH), (75, RiskBand.HIGH), (76, RiskBand.CRITICAL), (100, RiskBand.CRITICAL)],
    )
    def test_band_boundaries(self, score, band):
        assert band_for(score) is band

    def test_out_of_range_score_is_rejected(self):
        with pytest.raises(ValueError):
            rate_risk({RiskFactor.COMPLEXITY: 9})


class TestBR5Automatability:
    @pytest.mark.parametrize(
        "signals,expected,rule",
        [
            (CaseSignals(requires_visual_judgement=True), AutomatabilityClass.MANUAL_ONLY, 1),
            (CaseSignals(requires_external_step=True), AutomatabilityClass.MANUAL_ONLY, 2),
            (CaseSignals(requires_unprovisionable_data=True), AutomatabilityClass.MANUAL_ONLY, 3),
            (CaseSignals(is_exploratory=True), AutomatabilityClass.MANUAL_ONLY, 4),
            (CaseSignals(is_api_case=True, api_shape_source="specified"),
             AutomatabilityClass.AUTOMATABLE, 5),
            (CaseSignals(is_api_case=True), AutomatabilityClass.AUTOMATABLE, 6),
            (CaseSignals(is_ui_case=True, all_elements_have_locators=True,
                         all_locators_verified=True), AutomatabilityClass.AUTOMATABLE, 7),
            (CaseSignals(is_ui_case=True, all_elements_have_locators=True),
             AutomatabilityClass.AUTOMATABLE, 8),
            (CaseSignals(is_ui_case=True, has_fragile_locator_without_alternative=True),
             AutomatabilityClass.NEEDS_REVIEW, 9),
            (CaseSignals(), AutomatabilityClass.NEEDS_REVIEW, 10),
        ],
    )
    def test_decision_list_verdicts(self, signals, expected, rule):
        verdict = classify_automatability(signals)
        assert verdict.verdict is expected
        assert verdict.rule_number == rule

    def test_first_match_wins(self):
        # Visual judgement (rule 1) beats a specified API contract (rule 5).
        both = CaseSignals(requires_visual_judgement=True, is_api_case=True,
                           api_shape_source="specified")
        assert classify_automatability(both).rule_number == 1

    def test_every_verdict_cites_its_rule(self):
        verdict = classify_automatability(CaseSignals(is_exploratory=True))
        assert verdict.reason.startswith("rule 4:")

    def test_inferred_contract_is_annotated(self):
        verdict = classify_automatability(CaseSignals(is_api_case=True))
        assert verdict.annotation == "contract-inferred"

    def test_override_records_actor_and_reason(self):
        base = classify_automatability(CaseSignals())
        overridden = apply_override(base, "alex", "we can stub the device",
                                    AutomatabilityClass.AUTOMATABLE)
        assert overridden.verdict is AutomatabilityClass.AUTOMATABLE
        assert overridden.overridden_by == "alex"
        assert overridden.reason == base.reason  # original basis preserved

    def test_override_requires_actor_and_reason(self):
        base = classify_automatability(CaseSignals())
        with pytest.raises(ValueError):
            apply_override(base, "", "reason", AutomatabilityClass.AUTOMATABLE)


class TestBR6Identifiers:
    def test_format(self):
        assert encode_id(EntityKind.TEST_CASE, "checkout", 1) == "TC-CHECKOUT-00001"

    def test_round_trip(self):
        assert decode_id("TC-CHECKOUT-00042") == (EntityKind.TEST_CASE, "checkout", 42)

    def test_allocation_is_monotonic_within_a_feature(self):
        state = SequenceState()
        first, state = allocate(EntityKind.TEST_CASE, "checkout", state)
        second, state = allocate(EntityKind.TEST_CASE, "checkout", state)
        assert decode_id(second)[2] == decode_id(first)[2] + 1

    def test_sequences_are_independent_per_feature_and_kind(self):
        state = SequenceState()
        a, state = allocate(EntityKind.TEST_CASE, "checkout", state)
        b, state = allocate(EntityKind.TEST_CASE, "payments", state)
        c, state = allocate(EntityKind.REQUIREMENT, "checkout", state)
        assert decode_id(a)[2] == decode_id(b)[2] == decode_id(c)[2] == 1

    def test_rebuild_from_existing_never_reissues(self):
        # Obsolete cases are retained, so a count would collide with them.
        state = SequenceState.from_existing(["TC-CHECKOUT-00001", "TC-CHECKOUT-00007"])
        nxt, _ = allocate(EntityKind.TEST_CASE, "checkout", state)
        assert nxt == "TC-CHECKOUT-00008"

    def test_exhaustion_raises_rather_than_wrapping(self):
        state = SequenceState({(EntityKind.TEST_CASE, "checkout"): 99999})
        with pytest.raises(SequenceExhausted):
            allocate(EntityKind.TEST_CASE, "checkout", state)

    def test_allocate_many_is_consecutive(self):
        ids, _ = allocate_many(EntityKind.TEST_CASE, "checkout", 3, SequenceState())
        assert [decode_id(i)[2] for i in ids] == [1, 2, 3]

    def test_stability_reuses_an_existing_identifier(self):
        existing = [("TC-CHECKOUT-00003", "CI-CHECKOUT-00001", "Checkout works", False)]
        assert stable_id_for("CI-CHECKOUT-00001", "Checkout works", existing) == "TC-CHECKOUT-00003"

    def test_obsolete_cases_do_not_reclaim_their_identifier(self):
        existing = [("TC-CHECKOUT-00003", "CI-CHECKOUT-00001", "Checkout works", True)]
        assert stable_id_for("CI-CHECKOUT-00001", "Checkout works", existing) is None

    def test_malformed_identifier_is_rejected(self):
        with pytest.raises(DomainError):
            decode_id("TC-checkout-1")


class TestBR7Validation:
    KNOWN = frozenset({"PAY-12"})

    def test_case_without_steps_cannot_be_constructed(self):
        with pytest.raises(DomainError):
            make_case(steps=[])

    def test_case_without_links_is_rejected(self):
        failures = validate_case(make_case(links=False), self.KNOWN)
        assert [f.code for f in failures] == [ErrorCode.REJECTED_NO_JIRA_KEY]

    def test_unknown_key_is_distinguished_from_no_key(self):
        # The remediation differs: ingest the issue, versus add a link.
        failures = validate_case(make_case(key="NOPE-9"), self.KNOWN)
        assert [f.code for f in failures] == [ErrorCode.REJECTED_UNKNOWN_JIRA_KEY]

    def test_closed_gate_stops_the_batch(self):
        result = validate_batch([make_case(1)], self.KNOWN, gate_open=False)
        assert [r.code for r in result.rejections] == [ErrorCode.REJECTED_GATE_CLOSED]
        assert not result.accepted

    def test_batch_reports_every_failure_not_the_first(self):
        # At forty cases, failing on the first fault means forty correction rounds.
        result = validate_batch(
            [make_case(1, links=False), make_case(2, key="NOPE-1")],
            self.KNOWN,
            feature_slug="checkout",
        )
        assert len(result.rejections) == 2

    def test_a_batch_with_any_rejection_accepts_none(self):
        result = validate_batch(
            [make_case(1), make_case(2, links=False)], self.KNOWN, feature_slug="checkout"
        )
        assert result.accepted == []

    def test_intra_batch_duplicates_are_caught(self):
        result = validate_batch([make_case(1), make_case(2)], self.KNOWN, feature_slug="checkout")
        assert any(r.code is ErrorCode.REJECTED_DUPLICATE for r in result.rejections)

    def test_distinct_cases_are_accepted(self):
        result = validate_batch(
            [make_case(1), make_case(2, action="Enter quantity 9999", cls="just-outside")],
            self.KNOWN,
            feature_slug="checkout",
        )
        assert result.ok and len(result.accepted) == 2

    def test_self_supplied_identifier_is_rejected(self):
        failures = validate_case(make_case(), self.KNOWN, supplied_id=True)
        assert any(f.code is ErrorCode.REJECTED_SELF_SUPPLIED_ID for f in failures)

    def test_summary_counts_by_code(self):
        result = validate_batch([make_case(1, links=False)], self.KNOWN, feature_slug="checkout")
        assert result.summary()["by_code"] == {"REJECTED_NO_JIRA_KEY": 1}


class TestBR8Traceability:
    def test_strongest_link_wins(self):
        links = [
            TraceLink("c", "1", "PAY-2", LinkType.DERIVED_FROM_COMMIT,
                      selection_basis="x", resolved_jira_key="PAY-2"),
            TraceLink("c", "1", "PAY-1", LinkType.DIRECT_STORY, resolved_jira_key="PAY-1"),
        ]
        assert require_jira_key(links, frozenset({"PAY-1", "PAY-2"})) == "PAY-1"

    def test_unknown_keys_do_not_resolve(self):
        links = [TraceLink("c", "1", "PAY-9", LinkType.DIRECT_STORY, resolved_jira_key="PAY-9")]
        assert require_jira_key(links, frozenset({"PAY-1"})) is None

    def test_matrix_is_bidirectional(self):
        from tto_testgen.domain.traceability import MatrixEdge

        matrix = build_matrix([MatrixEdge("r", "TR-A-00001", "c", "TC-A-00001")])
        assert matrix.targets_of("TR-A-00001") == ["TC-A-00001"]
        assert matrix.sources_of("TC-A-00001") == ["TR-A-00001"]
        assert matrix.is_bidirectionally_consistent()

    def test_requirements_with_no_cases_still_appear(self):
        # An absent row hides exactly what the matrix exists to reveal.
        matrix = build_matrix([], all_sources=["TR-A-00001"])
        assert matrix.targets_of("TR-A-00001") == []
        assert matrix.uncovered(["TR-A-00001"]) == ["TR-A-00001"]


class TestBR9ImpactClassification:
    def test_deleted_requirement_makes_cases_obsolete(self):
        result = map_impact(
            [ChangedRef("src/a.py", "bitbucket")],
            [TraceEdge("src/a.py", "TC-A-00001", "TR-A-00001", requirement_deleted=True)],
            corpus_size=10,
        )
        assert result.impacts[0].classification is ChangeClassification.OBSOLETE

    def test_changed_statement_requires_update(self):
        result = map_impact(
            [ChangedRef("src/a.py", "bitbucket")],
            [TraceEdge("src/a.py", "TC-A-00001", "TR-A-00001", statement_changed=True)],
            corpus_size=10,
        )
        assert result.impacts[0].classification is ChangeClassification.REQUIRES_UPDATE

    def test_source_change_without_behaviour_change_is_unchanged(self):
        result = map_impact(
            [ChangedRef("src/a.py", "bitbucket")],
            [TraceEdge("src/a.py", "TC-A-00001", "TR-A-00001")],
            corpus_size=10,
        )
        assert result.impacts[0].classification is ChangeClassification.UNCHANGED

    def test_unmapped_change_is_reported_not_assumed_harmless(self):
        # "We found no link" and "there is no impact" are different statements.
        result = map_impact([ChangedRef("src/orphan.py", "bitbucket")], [], corpus_size=10)
        assert [c.ref for c in result.unmapped] == ["src/orphan.py"]

    def test_scale_is_reported(self):
        edges = [TraceEdge("src/a.py", f"TC-A-{i:05d}", "TR-A-00001", statement_changed=True)
                 for i in range(1, 4)]
        result = map_impact([ChangedRef("src/a.py", "bitbucket")], edges, corpus_size=10)
        assert result.scale == 0.3
        assert result.is_large

    def test_unchanged_cases_do_not_count_toward_scale(self):
        result = map_impact(
            [ChangedRef("src/a.py", "bitbucket")],
            [TraceEdge("src/a.py", "TC-A-00001", "TR-A-00001")],
            corpus_size=10,
        )
        assert result.scale == 0.0
