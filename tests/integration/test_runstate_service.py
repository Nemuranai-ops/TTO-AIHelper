"""S10 RunStateService. Requirements: FR-BAT-01 to FR-BAT-07, U7-NFR-REL-01 to -05."""

from datetime import datetime, timedelta, timezone

import pytest

from tto_testgen.adapters.sqlite.repositories import unit_of_work
from tto_testgen.domain.gates import Role
from tto_testgen.domain.model import StageName, UnitState
from tto_testgen.platform.result import ErrorCode
from tto_testgen.services.runstate import (
    FORBIDDEN_STATUS_FIELDS,
    LeaseClassification,
    ReportContext,
    RunStateService,
)

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def service(conn):
    return RunStateService(lambda: unit_of_work(conn), clock=lambda: NOW)


@pytest.fixture
def later_service(conn):
    def make(minutes):
        return RunStateService(
            lambda: unit_of_work(conn), clock=lambda: NOW + timedelta(minutes=minutes)
        )

    return make


class TestLeaseLifecycle:
    def test_begin_issues_a_lease(self, service):
        result = service.begin_unit("checkout", StageName.INGEST)
        assert result.ok and result.value.lease_id

    def test_complete_requires_the_matching_lease(self, service):
        service.begin_unit("checkout", StageName.INGEST)
        result = service.complete_unit("wrong", "checkout", StageName.INGEST, {})
        assert result.code is ErrorCode.FAILED_LOCKED

    def test_complete_with_the_right_lease_succeeds(self, service):
        lease = service.begin_unit("checkout", StageName.INGEST).value
        assert service.complete_unit(
            lease.lease_id, "checkout", StageName.INGEST, {"cases_produced": 40}
        ).ok

    def test_completing_a_unit_never_begun_is_refused(self, service):
        result = service.complete_unit("x", "never", StageName.INGEST, {})
        assert not result.ok

    def test_claiming_an_in_progress_unit_is_refused(self, service):
        service.begin_unit("checkout", StageName.INGEST)
        result = service.begin_unit("checkout", StageName.INGEST)
        assert result.code is ErrorCode.FAILED_LOCKED
        assert "lease_status" in result.context

    def test_completed_unit_needs_the_regenerate_flag(self, service):
        lease = service.begin_unit("checkout", StageName.INGEST).value
        service.complete_unit(lease.lease_id, "checkout", StageName.INGEST, {})
        assert service.begin_unit("checkout", StageName.INGEST).code is (
            ErrorCode.REJECTED_ALREADY_COMPLETE
        )
        assert service.begin_unit("checkout", StageName.INGEST, regenerate=True).ok

    def test_failed_unit_may_be_retried_without_a_flag(self, service):
        # Retrying a failure is the expected next action; re-running a success can
        # discard reviewed work, which is why only the latter needs stating.
        lease = service.begin_unit("checkout", StageName.INGEST).value
        service.fail_unit(lease.lease_id, "checkout", StageName.INGEST, "Jira unreachable")
        assert service.begin_unit("checkout", StageName.INGEST).ok

    def test_failure_requires_a_reason(self, service):
        lease = service.begin_unit("checkout", StageName.INGEST).value
        assert not service.fail_unit(lease.lease_id, "checkout", StageName.INGEST, "  ").ok

    def test_metrics_commit_with_the_state(self, service, conn):
        lease = service.begin_unit("checkout", StageName.INGEST).value
        service.complete_unit(
            lease.lease_id, "checkout", StageName.INGEST, {"cases_produced": 40}
        )
        row = conn.execute(
            "SELECT state, metrics FROM unit_state WHERE unit_ref='checkout' AND stage='ingest'"
        ).fetchone()
        assert row["state"] == "completed"
        assert "40" in row["metrics"]

    def test_approval_survives_a_regeneration(self, service, conn):
        """Re-claiming a completed unit must not silently discard its approval.

        The gate re-checks the content hash regardless, so retaining the approval is
        safe - and discarding it would force a re-approval for a re-run the operator
        explicitly asked for.
        """
        lease = service.begin_unit("checkout", StageName.INGEST).value
        service.complete_unit(lease.lease_id, "checkout", StageName.INGEST, {})
        service.approve_stage("checkout", StageName.INGEST, "sam", Role.TEST_ANALYST)
        service.begin_unit("checkout", StageName.INGEST, regenerate=True)
        row = conn.execute(
            "SELECT approved_by FROM unit_state WHERE unit_ref='checkout' AND stage='ingest'"
        ).fetchone()
        assert row["approved_by"] == "sam"


class TestStaleDetection:
    def test_a_fresh_lease_is_active(self, service, conn):
        service.begin_unit("checkout", StageName.INGEST)
        record = conn.execute(
            "SELECT * FROM unit_state WHERE unit_ref='checkout' AND stage='ingest'"
        ).fetchone()
        assert service.classify_lease(record).classification is LeaseClassification.ACTIVE

    def test_an_old_lease_is_stale(self, service, later_service, conn):
        service.begin_unit("checkout", StageName.INGEST)
        record = conn.execute(
            "SELECT * FROM unit_state WHERE unit_ref='checkout' AND stage='ingest'"
        ).fetchone()
        status = later_service(45).classify_lease(record)
        assert status.classification is LeaseClassification.STALE
        assert status.age_minutes == 45

    def test_stale_guidance_states_what_was_produced(self, service, later_service, conn):
        # An operator deciding whether to restart needs to know whether the unit got
        # nowhere or nearly finished.
        lease = service.begin_unit("checkout", StageName.INGEST).value
        service.heartbeat(lease.lease_id, "checkout", StageName.INGEST)
        record = conn.execute(
            "SELECT * FROM unit_state WHERE unit_ref='checkout' AND stage='ingest'"
        ).fetchone()
        assert "regenerate=true" in later_service(60).classify_lease(record).guidance

    def test_heartbeat_keeps_a_lease_active(self, service, later_service, conn):
        lease = service.begin_unit("checkout", StageName.INGEST).value
        later_service(40).heartbeat(lease.lease_id, "checkout", StageName.INGEST)
        record = conn.execute(
            "SELECT * FROM unit_state WHERE unit_ref='checkout' AND stage='ingest'"
        ).fetchone()
        assert later_service(50).classify_lease(record).classification is (
            LeaseClassification.ACTIVE
        )

    def test_heartbeat_requires_the_matching_lease(self, service):
        service.begin_unit("checkout", StageName.INGEST)
        assert not service.heartbeat("wrong", "checkout", StageName.INGEST).ok

    def test_classification_never_clears_the_lease(self, service, later_service, conn):
        # U7-NFR-REL-02. Clearing a lock another process still holds is how databases
        # get corrupted, and the service cannot tell a dead session from a slow one.
        service.begin_unit("checkout", StageName.INGEST)
        before = conn.execute(
            "SELECT lease_id FROM unit_state WHERE unit_ref='checkout' AND stage='ingest'"
        ).fetchone()["lease_id"]
        record = conn.execute(
            "SELECT * FROM unit_state WHERE unit_ref='checkout' AND stage='ingest'"
        ).fetchone()
        later_service(999).classify_lease(record)
        after = conn.execute(
            "SELECT lease_id, state FROM unit_state WHERE unit_ref='checkout' AND stage='ingest'"
        ).fetchone()
        assert after["lease_id"] == before
        assert after["state"] == UnitState.IN_PROGRESS.value


class TestGates:
    def test_first_stage_gate_is_open(self, service):
        assert service.is_gate_open("checkout", StageName.INGEST).is_open

    def test_gate_closed_when_prior_incomplete(self, service):
        result = service.is_gate_open("checkout", StageName.ANALYSE)
        assert not result.is_open
        assert result.failed_condition.value == "not-completed"

    def test_gate_closed_when_prior_unapproved(self, service):
        lease = service.begin_unit("checkout", StageName.INGEST).value
        service.complete_unit(lease.lease_id, "checkout", StageName.INGEST, {})
        result = service.is_gate_open("checkout", StageName.ANALYSE)
        assert result.failed_condition.value == "not-approved"

    def test_gate_opens_after_completion_and_approval(self, service):
        lease = service.begin_unit("checkout", StageName.INGEST).value
        service.complete_unit(lease.lease_id, "checkout", StageName.INGEST, {})
        service.approve_stage("checkout", StageName.INGEST, "sam", Role.TEST_ANALYST)
        assert service.is_gate_open("checkout", StageName.ANALYSE).is_open

    def test_only_the_test_lead_approves_coverage(self, service):
        for role in (Role.TEST_ANALYST, Role.TEST_AUTOMATION_ENGINEER):
            result = service.approve_stage("checkout", StageName.COVERAGE, "sam", role)
            assert result.code is ErrorCode.REJECTED_ROLE_NOT_PERMITTED
            assert result.context["attempted_by"] == "sam"  # the attempt is recorded
        assert service.approve_stage(
            "checkout", StageName.COVERAGE, "lead", Role.TEST_LEAD
        ).ok

    def test_approval_records_actor_role_and_time(self, service):
        result = service.approve_stage("checkout", StageName.CASES, "sam", Role.TEST_ANALYST)
        assert result.value["approved_by"] == "sam"
        assert result.value["role"] == "test-analyst"
        assert result.value["approved_at"]

    def test_gate_evaluation_writes_nothing(self, service, conn):
        before = conn.execute("SELECT COUNT(*) FROM unit_state").fetchone()[0]
        service.is_gate_open("checkout", StageName.CASES)
        assert conn.execute("SELECT COUNT(*) FROM unit_state").fetchone()[0] == before


class TestStatusComposition:
    def test_report_contains_no_forbidden_field(self, service):
        # C-12. A report surfacing one candidate is a proposal in disguise.
        service.begin_unit("checkout", StageName.INGEST)
        payload = service.get_status().to_dict()
        assert FORBIDDEN_STATUS_FIELDS.isdisjoint(payload)
        for row in payload["units"]:
            assert FORBIDDEN_STATUS_FIELDS.isdisjoint(row)

    def test_rows_sort_by_unit_then_stage_order(self, service):
        service.begin_unit("zebra", StageName.CASES)
        service.begin_unit("alpha", StageName.HANDOVER)
        service.begin_unit("alpha", StageName.INGEST)
        rows = service.get_status().units
        assert [(r["unit_ref"], r["stage"]) for r in rows] == [
            ("alpha", "ingest"), ("alpha", "handover"), ("zebra", "cases"),
        ]

    def test_report_states_it_is_reporting_only(self, service):
        assert "operator names" in service.get_status().note

    def test_in_progress_rows_carry_lease_status(self, service):
        service.begin_unit("checkout", StageName.INGEST)
        row = service.get_status().units[0]
        assert row["lease_status"]["classification"] == "active"

    def test_completed_rows_carry_no_lease_status(self, service):
        lease = service.begin_unit("checkout", StageName.INGEST).value
        service.complete_unit(lease.lease_id, "checkout", StageName.INGEST, {})
        assert service.get_status().units[0]["lease_status"] is None

    def test_scope_filters_by_unit(self, service):
        service.begin_unit("checkout", StageName.INGEST)
        service.begin_unit("payments", StageName.INGEST)
        assert len(service.get_status("checkout").units) == 1

    def test_corpus_totals_are_included(self, service, seeded):
        report = service.get_status()
        assert report.corpus["features"] == 1
        assert report.corpus["active_cases"] == 0


class TestReportContext:
    def test_hash_is_computed_once_per_feature(self, conn, seeded):
        calls = {"n": 0}

        class CountingRepo:
            def content_hash_for(self, feature_id):
                calls["n"] += 1
                return "a" * 64

        ctx = ReportContext(CountingRepo())
        for _ in range(10):
            ctx.coverage_hash(seeded)
        assert calls["n"] == 1
        assert ctx.hits == 9 and ctx.misses == 1

    def test_none_feature_needs_no_lookup(self):
        class Boom:
            def content_hash_for(self, feature_id):
                raise AssertionError("should not be called")

        assert ReportContext(Boom()).coverage_hash(None) is None


class TestResume:
    def test_resume_reports_interrupted_units(self, service):
        service.begin_unit("checkout", StageName.INGEST)
        view = service.resume_view()
        assert len(view["interrupted"]) == 1

    def test_resume_states_nothing_was_lost(self, service):
        # An operator returning after a crash needs to know whether partial output
        # is lurking. It is not, and saying so removes the impulse to go looking.
        assert "Nothing was lost" in service.resume_view()["note"]

    def test_context_exhaustion_looks_like_a_crash(self, service, later_service, conn):
        # BR-U7-5.1: the recovery is identical, so the causes are not distinguished.
        service.begin_unit("checkout", StageName.INGEST)
        view = later_service(120).resume_view()
        assert view["interrupted"][0]["lease_status"]["classification"] == "stale"
