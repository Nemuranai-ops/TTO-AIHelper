"""S3 and S4. Requirements: FR-TRQ-01 to -05, FR-COV-01 to -07, FR-TRC-02 to -04."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tto_testgen.adapters.sqlite.repositories import unit_of_work
from tto_testgen.domain.gates import Role
from tto_testgen.domain.model import Artefact, Feature, RiskBand, StageName, content_hash
from tto_testgen.domain.traceability import CommitRecord
from tto_testgen.platform.logging import configure
from tto_testgen.platform.result import ErrorCode, ok
from tto_testgen.services.coverage import CoverageService
from tto_testgen.services.requirements import (
    TestableRequirementService as RequirementService,
    band,
)
from tto_testgen.services.runstate import RunStateService

NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)


class StubBitbucket:
    def __init__(self, commits=None):
        self.commits = commits or {}

    def log(self, repo_slug, *, path=None, since=None):
        return ok(self.commits.get(path, []))


@pytest.fixture
def log():
    return configure("CRITICAL")


@pytest.fixture
def feature(conn):
    from tto_testgen.domain.model import Resource, ResourceType

    with unit_of_work(conn) as uow:
        uow.features.upsert(Feature(slug="checkout", name="Checkout"))
        uow.resources.upsert(Resource(raw_ref="PAY-12", type=ResourceType.JIRA_ISSUE))
        resource_id = uow.resources.id_for("PAY-12")
        uow.artefacts.upsert(Artefact.of(
            resource_id=resource_id, kind="jira-issue", source_identifier="PAY-12",
            content="Checkout story",
        ))
    return "checkout"


@pytest.fixture
def requirements_service(conn, log):
    return RequirementService(
        lambda: unit_of_work(conn), StubBitbucket(), log, clock=lambda: NOW
    )


@pytest.fixture
def coverage_service(conn, log):
    run_state = RunStateService(lambda: unit_of_work(conn), clock=lambda: NOW)
    return CoverageService(lambda: unit_of_work(conn), run_state, log)


def requirement(statement="The cart displays the running total", **kw):
    base = {
        "statement": statement, "category": "business-rule",
        "source_artefact_ids": ["PAY-12"],
        "links": [{"type": "direct-story", "jira_key": "PAY-12"}],
    }
    base.update(kw)
    return base


class TestRiskBanding:
    @pytest.mark.parametrize(
        "value,expected", [(0, 1), (1, 1), (2, 2), (3, 2), (4, 3), (7, 4), (11, 5), (99, 5)]
    )
    def test_complexity_bands(self, value, expected):
        assert band(value, (1, 3, 6, 10)) == expected

    def test_banding_is_monotonic(self):
        previous = 0
        for value in range(0, 50):
            current = band(value, (1, 3, 6, 10))
            assert current >= previous
            previous = current


class TestRequirementValidation:
    def test_a_valid_requirement_is_accepted(self, requirements_service, feature):
        report = requirements_service.upsert_requirements(
            feature, {"requirements": [requirement()]}
        ).value
        assert report.ok and len(report.accepted) == 1

    def test_a_bundled_requirement_is_rejected(self, requirements_service, feature):
        report = requirements_service.upsert_requirements(
            feature,
            {"requirements": [requirement("The request returns 200 and the order is stored")]},
        ).value
        assert not report.ok
        assert report.rejections[0]["code"] == ErrorCode.REJECTED_INVALID_STEPS.value
        assert report.rejections[0]["suspected_split"]

    def test_force_atomic_overrides_and_is_recorded(self, requirements_service, feature):
        report = requirements_service.upsert_requirements(
            feature,
            {"requirements": [requirement(
                "The request returns 200 and the order is stored", force_atomic=True
            )]},
        ).value
        assert report.ok
        assert report.atomicity_overrides  # visible, so clustering is detectable

    def test_an_unknown_category_is_rejected(self, requirements_service, feature):
        report = requirements_service.upsert_requirements(
            feature, {"requirements": [requirement(category="invented")]}
        ).value
        assert not report.ok

    def test_a_requirement_with_no_source_artefact_is_rejected(
        self, requirements_service, feature
    ):
        report = requirements_service.upsert_requirements(
            feature, {"requirements": [requirement(source_artefact_ids=[])]}
        ).value
        assert not report.ok

    def test_a_rejected_batch_stores_nothing(self, requirements_service, feature, conn):
        requirements_service.upsert_requirements(
            feature,
            {"requirements": [requirement(), requirement(category="invented")]},
        )
        # A half-populated requirement set would produce a coverage model missing
        # items nobody knows are missing.
        assert conn.execute("SELECT COUNT(*) FROM testable_requirement").fetchone()[0] == 0

    def test_every_failure_is_reported_together(self, requirements_service, feature):
        report = requirements_service.upsert_requirements(
            feature,
            {"requirements": [
                requirement(category="invented"),
                requirement(source_artefact_ids=[]),
            ]},
        ).value
        assert len(report.rejections) == 2


class TestGapRouting:
    def test_an_untraceable_behaviour_becomes_a_gap_not_a_rejection(
        self, requirements_service, feature, conn
    ):
        # A rejected requirement is the agent's mistake; a gapped behaviour is a
        # fact about the sources. Failing the batch for it would leave the agent
        # retrying forever.
        report = requirements_service.upsert_requirements(
            feature,
            {"requirements": [requirement(links=[], source_files=["src/pay.py"])],
             "repo_slug": "orders"},
        ).value
        assert report.ok
        assert len(report.gaps) == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM gap WHERE category='untraceable-behaviour'"
        ).fetchone()[0] == 1

    def test_the_gap_records_what_was_attempted(self, requirements_service, feature, conn):
        requirements_service.upsert_requirements(
            feature,
            {"requirements": [requirement(links=[], source_files=["src/pay.py"])],
             "repo_slug": "orders"},
        )
        attempted = conn.execute("SELECT attempted FROM gap").fetchone()[0]
        assert "direct-story" in attempted

    def test_gaps_are_idempotent_across_runs(self, requirements_service, feature, conn):
        # A re-run finding the same behaviour untraceable must not accumulate a
        # duplicate per run - the report would then measure how often the pipeline
        # ran rather than how much is untraceable.
        payload = {"requirements": [requirement(links=[], source_files=["src/pay.py"])],
                   "repo_slug": "orders"}
        requirements_service.upsert_requirements(feature, payload)
        requirements_service.upsert_requirements(feature, payload)
        assert conn.execute("SELECT COUNT(*) FROM gap").fetchone()[0] == 1

    def test_a_requirement_with_no_links_and_no_files_is_rejected(
        self, requirements_service, feature
    ):
        report = requirements_service.upsert_requirements(
            feature, {"requirements": [requirement(links=[])]}
        ).value
        assert not report.ok


class TestCommitDerivation:
    def test_a_key_is_derived_from_commit_history(self, conn, log, feature):
        service = RequirementService(
            lambda: unit_of_work(conn),
            StubBitbucket({"src/pay.py": [
                CommitRecord("a" * 40, "PAY-12 fix rounding", NOW - timedelta(days=5), 40)
            ]}),
            log, clock=lambda: NOW,
        )
        report = service.upsert_requirements(
            feature,
            {"requirements": [requirement(links=[], source_files=["src/pay.py"])],
             "repo_slug": "orders"},
        ).value
        assert report.ok and report.derived_links == 1

    def test_a_derived_link_is_typed_and_counted_separately(self, conn, log, feature):
        service = RequirementService(
            lambda: unit_of_work(conn),
            StubBitbucket({"src/pay.py": [
                CommitRecord("a" * 40, "PAY-12 fix", NOW - timedelta(days=5), 40)
            ]}),
            log, clock=lambda: NOW,
        )
        service.upsert_requirements(
            feature,
            {"requirements": [requirement(links=[], source_files=["src/pay.py"])],
             "repo_slug": "orders"},
        )
        row = conn.execute("SELECT link_type, selection_basis FROM trace_link").fetchone()
        assert row["link_type"] == "derived-from-commit"
        assert row["selection_basis"]

    def test_the_index_report_reaches_the_result(self, conn, log, feature):
        service = RequirementService(
            lambda: unit_of_work(conn), StubBitbucket(), log, clock=lambda: NOW
        )
        report = service.upsert_requirements(
            feature,
            {"requirements": [requirement(links=[], source_files=["a.py"])],
             "repo_slug": "orders"},
        ).value
        assert "skipped_files" in report.index_report


class TestRiskRating:
    def test_a_partial_rating_is_flagged_not_zeroed(self, requirements_service, feature, conn):
        report = requirements_service.upsert_requirements(
            feature, {"requirements": [requirement()]}
        ).value
        assert report.partial_ratings == 1  # criticality not supplied
        row = conn.execute(
            "SELECT risk_is_partial, risk_factors FROM testable_requirement"
        ).fetchone()
        assert row["risk_is_partial"] == 1
        assert "unavailable" in row["risk_factors"]

    def test_supplied_criticality_is_used_with_its_evidence(
        self, requirements_service, feature, conn
    ):
        requirements_service.upsert_requirements(
            feature,
            {"requirements": [requirement(
                business_criticality=5, criticality_evidence="Jira priority Blocker"
            )]},
        )
        factors = conn.execute("SELECT risk_factors FROM testable_requirement").fetchone()[0]
        assert "Blocker" in factors

    def test_change_frequency_is_unavailable_without_history(
        self, requirements_service, feature, conn
    ):
        # Zero commits and no commit data are different facts.
        requirements_service.upsert_requirements(
            feature, {"requirements": [requirement()]}
        )
        factors = conn.execute("SELECT risk_factors FROM testable_requirement").fetchone()[0]
        assert '"change_frequency": "unavailable"' in factors


class TestCoverageBuild:
    def _seed(self, requirements_service, feature, count=2):
        return requirements_service.upsert_requirements(
            feature,
            {"requirements": [
                requirement(f"The cart shows value {i}") for i in range(count)
            ]},
        ).value

    def test_a_model_is_built_with_a_version_and_hash(
        self, requirements_service, coverage_service, feature
    ):
        self._seed(requirements_service, feature)
        result = coverage_service.build_model(feature).value
        assert result.model_version == 1
        assert len(result.content_hash) == 64
        assert result.planned_total > 0

    def test_not_required_items_are_stored(
        self, requirements_service, coverage_service, feature, conn
    ):
        # BR-2.6: an absent row and a deliberate exclusion look identical unless the
        # exclusion is recorded.
        self._seed(requirements_service, feature, count=1)
        result = coverage_service.build_model(feature).value
        assert result.items > result.required_items
        assert conn.execute(
            "SELECT COUNT(*) FROM coverage_item WHERE is_required = 0"
        ).fetchone()[0] > 0

    def test_the_derivation_is_stated(self, requirements_service, coverage_service, feature):
        self._seed(requirements_service, feature)
        payload = coverage_service.build_model(feature).value.to_dict()
        assert "ISTQB" in payload["derivation"]

    def test_a_feature_with_no_requirements_is_refused(self, coverage_service, feature):
        result = coverage_service.build_model(feature)
        assert not result.ok
        assert "requirements stage" in result.remediation

    def test_an_unchanged_rebuild_keeps_the_version(
        self, requirements_service, coverage_service, feature
    ):
        self._seed(requirements_service, feature)
        first = coverage_service.build_model(feature).value
        second = coverage_service.build_model(feature).value
        assert second.model_version == first.model_version
        assert second.content_hash == first.content_hash


class TestApprovalBinding:
    def _seed_and_build(self, requirements_service, coverage_service, feature):
        requirements_service.upsert_requirements(
            feature, {"requirements": [requirement()]}
        )
        return coverage_service.build_model(feature).value

    def test_only_the_test_lead_may_approve(
        self, requirements_service, coverage_service, feature
    ):
        self._seed_and_build(requirements_service, coverage_service, feature)
        refused = coverage_service.approve_baseline(feature, "sam", Role.TEST_ANALYST)
        assert refused.code is ErrorCode.REJECTED_ROLE_NOT_PERMITTED
        assert coverage_service.approve_baseline(feature, "lead", Role.TEST_LEAD).ok

    def test_approval_binds_to_the_content_hash(
        self, requirements_service, coverage_service, feature, conn
    ):
        build = self._seed_and_build(requirements_service, coverage_service, feature)
        coverage_service.approve_baseline(feature, "lead", Role.TEST_LEAD)
        stored = conn.execute(
            "SELECT approved_content_hash FROM unit_state WHERE stage='coverage'"
        ).fetchone()[0]
        assert stored == build.content_hash

    def test_approving_without_a_model_is_refused(self, coverage_service, feature):
        result = coverage_service.approve_baseline(feature, "lead", Role.TEST_LEAD)
        assert not result.ok
        assert "coverage_build" in result.remediation


class TestReduction:
    def _seed(self, requirements_service, coverage_service, feature, criticality=None):
        requirements_service.upsert_requirements(
            feature,
            {"requirements": [requirement(business_criticality=criticality)
                              if criticality else requirement()]},
        )
        return coverage_service.build_model(feature).value

    def test_a_reduction_records_both_yields(
        self, requirements_service, coverage_service, feature, conn
    ):
        self._seed(requirements_service, coverage_service, feature)
        result = coverage_service.apply_reduction(
            feature, "low-risk admin screen", "lead"
        ).value
        assert result.reduced_yield <= result.full_yield
        row = conn.execute(
            "SELECT full_yield, reduced_yield FROM coverage_reduction"
        ).fetchone()
        assert row["full_yield"] == result.full_yield

    def test_a_reduction_requires_a_reason(
        self, requirements_service, coverage_service, feature
    ):
        self._seed(requirements_service, coverage_service, feature)
        assert not coverage_service.apply_reduction(feature, "  ", "lead").ok

    def test_a_high_risk_feature_needs_an_override(
        self, requirements_service, coverage_service, feature
    ):
        self._seed(requirements_service, coverage_service, feature, criticality=5)
        refused = coverage_service.apply_reduction(feature, "we accept the risk", "lead")
        assert refused.code is ErrorCode.REJECTED_ROLE_NOT_PERMITTED
        assert "override=true" in refused.remediation
        allowed = coverage_service.apply_reduction(
            feature, "we accept the risk", "lead", override=True
        )
        assert allowed.ok

    def test_the_override_and_contradiction_are_recorded(
        self, requirements_service, coverage_service, feature, conn
    ):
        self._seed(requirements_service, coverage_service, feature, criticality=5)
        coverage_service.apply_reduction(feature, "accepted", "lead", override=True)
        row = conn.execute(
            "SELECT was_override, risk_band, decided_by FROM coverage_reduction"
        ).fetchone()
        assert row["was_override"] == 1
        assert row["risk_band"] in ("high", "critical")
        assert row["decided_by"] == "lead"

    def test_a_reduction_is_recorded_as_a_gap(
        self, requirements_service, coverage_service, feature, conn
    ):
        # Reduced coverage is a gap that was chosen rather than missed, and the gap
        # report should not distinguish them by omission.
        self._seed(requirements_service, coverage_service, feature)
        coverage_service.apply_reduction(feature, "low risk", "lead")
        assert conn.execute(
            "SELECT COUNT(*) FROM gap WHERE category='reduced-depth'"
        ).fetchone()[0] == 1
