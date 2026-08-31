"""L5 GateEvaluator. Requirements: FR-BAT-07, FR-COV-06, U7-NFR-REL-05."""

import itertools

import pytest

from tto_testgen.domain.gates import (
    ROLE_RESTRICTED,
    STAGE_ORDER,
    GateFailure,
    PriorRecord,
    Role,
    evaluate,
    is_role_permitted,
    next_stage,
    prior_stage,
    stage_index,
)
from tto_testgen.domain.model import StageName, UnitState

APPROVED = PriorRecord(UnitState.COMPLETED, "lead", "2026-08-29", "a" * 64)
HASH = "a" * 64


class TestStageOrdering:
    def test_pipeline_order_matches_the_design(self):
        assert [s.value for s in STAGE_ORDER] == [
            "ingest", "analyse", "requirements", "coverage",
            "cases", "automation", "handover",
        ]

    def test_every_stage_appears_exactly_once(self):
        assert len(STAGE_ORDER) == len(set(STAGE_ORDER)) == len(StageName)

    def test_first_stage_has_no_prior(self):
        assert prior_stage(StageName.INGEST) is None

    def test_last_stage_has_no_next(self):
        assert next_stage(StageName.HANDOVER) is None

    def test_prior_and_next_are_inverse(self):
        for stage in STAGE_ORDER[:-1]:
            assert prior_stage(next_stage(stage)) is stage

    def test_indices_are_consecutive(self):
        assert [stage_index(s) for s in STAGE_ORDER] == list(range(len(STAGE_ORDER)))


class TestGateConditions:
    def test_first_stage_gate_is_always_open(self):
        assert evaluate("checkout", StageName.INGEST, None).is_open

    def test_missing_prior_record_reads_as_not_completed(self):
        result = evaluate("checkout", StageName.CASES, None, HASH)
        assert not result.is_open
        assert result.failed_condition is GateFailure.NOT_COMPLETED

    @pytest.mark.parametrize(
        "state",
        [s for s in UnitState if s is not UnitState.COMPLETED],
    )
    def test_any_non_completed_state_closes_the_gate(self, state):
        prior = PriorRecord(state) if state is not UnitState.IN_PROGRESS else PriorRecord(state)
        result = evaluate("checkout", StageName.CASES, prior, HASH)
        assert result.failed_condition is GateFailure.NOT_COMPLETED

    def test_completed_but_unapproved_closes_the_gate(self):
        result = evaluate("checkout", StageName.CASES, PriorRecord(UnitState.COMPLETED), HASH)
        assert result.failed_condition is GateFailure.NOT_APPROVED

    def test_changed_content_closes_the_gate(self):
        # Without this condition, editing an approved coverage model would leave the
        # approval attached to content nobody approved.
        result = evaluate("checkout", StageName.CASES, APPROVED, "b" * 64)
        assert result.failed_condition is GateFailure.CONTENT_CHANGED

    def test_matching_content_opens_the_gate(self):
        result = evaluate("checkout", StageName.CASES, APPROVED, HASH)
        assert result.is_open
        assert result.approved_by == "lead"

    def test_approval_without_a_hash_is_honoured(self):
        # Honoured rather than blocking forever, but the weaker guarantee stays
        # visible in the detail rather than being silently assumed.
        prior = PriorRecord(UnitState.COMPLETED, "lead", "2026-08-29", None)
        assert evaluate("checkout", StageName.CASES, prior, HASH).is_open

    def test_exactly_one_condition_is_named_on_failure(self):
        for prior, current in [
            (None, HASH),
            (PriorRecord(UnitState.COMPLETED), HASH),
            (APPROVED, "b" * 64),
        ]:
            result = evaluate("checkout", StageName.CASES, prior, current)
            assert result.failed_condition is not None
            assert result.detail and result.remediation

    def test_open_gate_names_no_failed_condition(self):
        assert evaluate("checkout", StageName.CASES, APPROVED, HASH).failed_condition is None


class TestExhaustiveCoverage:
    """Three conditions across seven stages is small enough to cover completely."""

    def test_every_stage_and_condition_combination(self):
        priors = {
            "missing": None,
            "not-completed": PriorRecord(UnitState.NOT_STARTED),
            "unapproved": PriorRecord(UnitState.COMPLETED),
            "approved-match": APPROVED,
            "approved-mismatch": APPROVED,
        }
        for stage, (label, prior) in itertools.product(STAGE_ORDER, priors.items()):
            current = "b" * 64 if label == "approved-mismatch" else HASH
            result = evaluate("checkout", stage, prior, current)
            if prior_stage(stage) is None:
                assert result.is_open, f"{stage}/{label}"
            elif label == "approved-match":
                assert result.is_open, f"{stage}/{label}"
            else:
                assert not result.is_open, f"{stage}/{label}"
                assert result.failed_condition is not None


class TestRoleRestriction:
    def test_only_coverage_is_restricted(self):
        assert set(ROLE_RESTRICTED) == {StageName.COVERAGE}

    @pytest.mark.parametrize("role", [Role.TEST_ANALYST, Role.TEST_AUTOMATION_ENGINEER])
    def test_coverage_refuses_other_roles(self, role):
        assert not is_role_permitted(StageName.COVERAGE, role)

    def test_coverage_permits_the_test_lead(self):
        assert is_role_permitted(StageName.COVERAGE, Role.TEST_LEAD)

    @pytest.mark.parametrize("stage", [s for s in STAGE_ORDER if s is not StageName.COVERAGE])
    def test_other_stages_permit_every_role(self, stage):
        for role in Role:
            assert is_role_permitted(stage, role)

    def test_remediation_names_the_permitted_role(self):
        # "Gate closed" without the remedy sends the operator to documentation for
        # something the system already knows.
        result = evaluate("checkout", StageName.CASES, PriorRecord(UnitState.COMPLETED), HASH)
        assert "test lead" in result.remediation.lower()
        assert result.permitted_role is Role.TEST_LEAD

    def test_unrestricted_stage_names_no_role(self):
        result = evaluate("checkout", StageName.REQUIREMENTS, PriorRecord(UnitState.COMPLETED), HASH)
        assert result.permitted_role is None
        assert "must do this" not in result.remediation


class TestPurity:
    def test_evaluator_module_imports_nothing_outside_domain(self):
        # U7-NFR-REL-05 is structural: with no repository, there is nothing to write
        # through, and the evaluator can be called inside a caller's transaction.
        import ast
        import pathlib

        import tto_testgen.domain.gates as gates

        tree = ast.parse(pathlib.Path(gates.__file__).read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported.extend(a.name for a in node.names)
        external = [
            m for m in imported
            if m.startswith("tto_testgen") and not m.startswith("tto_testgen.domain")
        ]
        assert external == [], f"gates.py imports outside the domain: {external}"

    def test_evaluation_is_deterministic(self):
        first = evaluate("checkout", StageName.CASES, APPROVED, HASH)
        second = evaluate("checkout", StageName.CASES, APPROVED, HASH)
        assert first == second

    def test_to_dict_is_serialisable(self):
        import json

        json.dumps(evaluate("checkout", StageName.CASES, APPROVED, HASH).to_dict())
