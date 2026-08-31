"""S1 and S2. Requirements: FR-ING-01 to FR-ING-10, FR-ANA-01 to FR-ANA-08."""

from __future__ import annotations

from pathlib import Path

import pytest

from tto_testgen.adapters.paging import PagedResult
from tto_testgen.adapters.sources.manifest import ResourceManifestAdapter
from tto_testgen.adapters.sqlite.repositories import unit_of_work
from tto_testgen.domain.apimodel import AuthRequirement, CodeEndpoint, SpecEndpoint
from tto_testgen.domain.discrepancy import screen_not_in_live
from tto_testgen.domain.model import Feature, ResourceType
from tto_testgen.platform.logging import configure
from tto_testgen.platform.resilience import RetryPolicy
from tto_testgen.platform.result import ErrorCode, err, ok
from tto_testgen.ports.sources import SourceRecord
from tto_testgen.services.analysis import AnalysisService, has_cycle
from tto_testgen.services.ingestion import IngestionService


class StubSource:
    def __init__(self, records=None, failure=None, guidance=""):
        self.records = records or []
        self.failure = failure
        self.guidance = guidance
        self.fetch_count = 0

    def fetch(self, resource):
        self.fetch_count += 1
        if self.failure:
            return err(*self.failure)
        return ok(PagedResult(records=list(self.records), guidance=self.guidance))


def record(identifier, content, kind="jira-issue", detail="full"):
    return SourceRecord(
        source_identifier=identifier, kind=kind, content=content, detail_level=detail
    )


@pytest.fixture
def log():
    return configure("CRITICAL")


@pytest.fixture
def manifest(tmp_path):
    (tmp_path / "resources.md").write_text("- PAY-1\n- PAY-2\n")
    return ResourceManifestAdapter(tmp_path / "resources.md", tmp_path)


def make_ingestion(conn, log, manifest, source):
    return IngestionService(
        lambda: unit_of_work(conn), manifest,
        lambda _type: source, log,
        retry_policy=RetryPolicy(attempts=1),
    )


class TestIngestion:
    def test_stores_artefacts_and_reports_totals(self, conn, log, manifest):
        source = StubSource([record("PAY-1", "body one")])
        report = make_ingestion(conn, log, manifest, source).ingest_resources().value
        # Two resources, identical content: the first stores, the second recognises
        # the hash and skips.
        assert report.totals["succeeded"] == 1
        assert report.totals["skipped_unchanged"] == 1
        assert report.totals["artefacts_stored"] == 1

    def test_every_resource_lands_in_exactly_one_bucket(self, conn, log, manifest):
        """A resource returning nothing must still appear.

        Conditional appends left an empty resource in neither bucket, which is the
        one outcome an operator would most want to see: the query ran and found
        nothing.
        """
        report = make_ingestion(
            conn, log, manifest, StubSource([])
        ).ingest_resources().value
        totals = report.totals
        assert totals["succeeded"] + totals["skipped_unchanged"] + totals["failed"] == 2
        assert all(entry["artefacts"] == 0 for entry in report.succeeded)

    def test_unchanged_content_is_skipped_without_a_store(self, conn, log, manifest):
        source = StubSource([record("PAY-1", "identical body")])
        service = make_ingestion(conn, log, manifest, source)
        service.ingest_resources()
        second = service.ingest_resources().value
        assert second.totals["artefacts_stored"] == 0
        assert second.totals["artefacts_skipped"] == 2

    def test_a_re_run_that_stores_nothing_is_visibly_correct(self, conn, log, manifest):
        # A run that fetches and stores nothing is exactly right, and
        # indistinguishable from a broken one unless the report says so.
        source = StubSource([record("PAY-1", "body")])
        service = make_ingestion(conn, log, manifest, source)
        service.ingest_resources()
        report = service.ingest_resources().value
        assert report.totals["artefacts_skipped"] > 0

    def test_one_failing_resource_does_not_stop_the_others(self, conn, log, tmp_path):
        (tmp_path / "resources.md").write_text("- PAY-1\n- https://bb.corp/projects/P/repos/r\n")
        manifest = ResourceManifestAdapter(tmp_path / "resources.md", tmp_path)

        def source_for(resource_type):
            if resource_type is ResourceType.BITBUCKET_REPO:
                return StubSource(failure=(ErrorCode.FAILED_MCP_UNREACHABLE, "down"))
            return StubSource([record("PAY-1", "body")])

        service = IngestionService(
            lambda: unit_of_work(conn), manifest, source_for, log,
            retry_policy=RetryPolicy(attempts=1),
        )
        report = service.ingest_resources().value
        assert report.totals["succeeded"] == 1
        assert report.totals["failed"] == 1
        assert report.is_partial

    def test_a_partial_run_still_completes(self, conn, log, tmp_path):
        # The system cannot know whether the missing repository mattered. Reporting
        # and stopping is the only honest option (BR-U2-8.2).
        (tmp_path / "resources.md").write_text("- PAY-1\n")
        manifest = ResourceManifestAdapter(tmp_path / "resources.md", tmp_path)
        source = StubSource(failure=(ErrorCode.FAILED_MCP_UNREACHABLE, "down"))
        result = IngestionService(
            lambda: unit_of_work(conn), manifest, lambda _t: source, log,
            retry_policy=RetryPolicy(attempts=1),
        ).ingest_resources()
        assert result.ok
        assert "weigh" in result.value.to_dict()["note"]

    def test_unclassifiable_entries_reach_the_report(self, conn, log, tmp_path):
        (tmp_path / "resources.md").write_text("- PAY-1\n- total nonsense\n")
        manifest = ResourceManifestAdapter(tmp_path / "resources.md", tmp_path)
        report = make_ingestion(
            conn, log, manifest, StubSource([record("PAY-1", "b")])
        ).ingest_resources().value
        assert report.unclassified == ["total nonsense"]

    def test_ceiling_guidance_reaches_the_report(self, conn, log, manifest):
        source = StubSource(
            [record("PAY-1", "b")], guidance="Stopped at the 2000-artefact ceiling"
        )
        report = make_ingestion(conn, log, manifest, source).ingest_resources().value
        assert report.ceiling_notices
        assert "ceiling" in report.ceiling_notices[0]["guidance"]

    def test_missing_manifest_is_reported_not_raised(self, conn, log, tmp_path):
        manifest = ResourceManifestAdapter(tmp_path / "absent.md", tmp_path)
        result = make_ingestion(conn, log, manifest, StubSource()).ingest_resources()
        assert not result.ok

    def test_four_outcomes_are_distinguished(self, conn, log, manifest):
        report = make_ingestion(
            conn, log, manifest, StubSource([record("PAY-1", "b")])
        ).ingest_resources().value
        assert set(report.totals) >= {
            "succeeded", "skipped_unchanged", "failed", "unclassified"
        }


class TestAnalysisFeatureModel:
    @pytest.fixture
    def service(self, conn, log):
        return AnalysisService(lambda: unit_of_work(conn), log)

    def test_a_feature_citing_no_artefact_is_rejected(self, service):
        report = service.upsert_feature_model(
            {"features": [{"slug": "checkout", "name": "Checkout"}]}
        ).value
        assert not report.ok
        assert report.rejections[0]["code"] == ErrorCode.REJECTED_NO_JIRA_KEY.value

    def test_a_rejection_stores_nothing(self, service, conn):
        service.upsert_feature_model(
            {"features": [{"slug": "checkout", "name": "Checkout"}]}
        )
        assert conn.execute("SELECT COUNT(*) FROM feature").fetchone()[0] == 0

    def test_a_cycle_is_rejected(self, service):
        report = service.upsert_feature_model({"features": [
            {"slug": "a", "name": "A", "parent_slug": "b", "source_artefact_ids": ["PAY-1"]},
            {"slug": "b", "name": "B", "parent_slug": "a", "source_artefact_ids": ["PAY-1"]},
        ]}).value
        assert any("cycle" in r["detail"] for r in report.rejections)

    def test_a_grounded_feature_is_stored(self, service, conn):
        report = service.upsert_feature_model({"features": [
            {"slug": "checkout", "name": "Checkout", "source_artefact_ids": ["PAY-1"]}
        ]}).value
        assert report.ok and report.features == 1
        assert conn.execute("SELECT COUNT(*) FROM feature").fetchone()[0] == 1

    def test_journeys_and_rules_are_stored(self, service, conn):
        report = service.upsert_feature_model({
            "features": [{"slug": "checkout", "name": "Checkout",
                          "source_artefact_ids": ["PAY-1"]}],
            "journeys": [{"name": "Place an order", "steps": [{"screen": "cart"}]}],
            "business_rules": [{"feature_slug": "checkout", "rule_kind": "validation",
                                "condition": "qty 1-99", "effect": "reject otherwise",
                                "is_documented": False}],
        }).value
        assert report.journeys == 1 and report.business_rules == 1
        assert conn.execute(
            "SELECT is_documented FROM business_rule"
        ).fetchone()[0] == 0

    def test_unassigned_artefacts_are_listed_not_forced(self, service):
        # Forcing an artefact into the nearest feature creates a false link that
        # later reads as evidence (US-ANA-01 AC3).
        report = service.upsert_feature_model({
            "features": [{"slug": "checkout", "name": "C", "source_artefact_ids": ["PAY-1"]}],
            "unassigned_artefact_ids": ["PAY-9"],
        }).value
        assert report.unassigned_artefacts == ["PAY-9"]

    @pytest.mark.parametrize(
        "features,expected",
        [
            ([{"slug": "a", "parent_slug": None}], False),
            ([{"slug": "a", "parent_slug": "a"}], True),
            ([{"slug": "a", "parent_slug": "b"}, {"slug": "b", "parent_slug": None}], False),
            ([{"slug": "a", "parent_slug": "b"}, {"slug": "b", "parent_slug": "a"}], True),
        ],
    )
    def test_cycle_detection(self, features, expected):
        assert has_cycle(features) is expected


class TestAnalysisApiModel:
    @pytest.fixture
    def service(self, conn, log):
        return AnalysisService(lambda: unit_of_work(conn), log)

    def test_spec_only_endpoint_is_a_discrepancy_not_an_endpoint(self, service, conn):
        result = service.derive_api_model([], [SpecEndpoint("GET", "/ghost")]).value
        assert result["endpoints"] == 0
        assert conn.execute("SELECT COUNT(*) FROM api_endpoint").fetchone()[0] == 0
        assert conn.execute(
            "SELECT kind FROM discrepancy"
        ).fetchone()[0] == "endpoint-not-implemented"

    def test_code_endpoint_is_stored_with_inferred_shapes(self, service, conn):
        service.derive_api_model([CodeEndpoint("GET", "/orders", "api.py", 1)], [])
        row = conn.execute("SELECT shape_source, auth_requirement FROM api_endpoint").fetchone()
        assert row["shape_source"] == "inferred"
        # Never defaulted to none.
        assert row["auth_requirement"] == "unknown"

    def test_spec_shapes_win_when_both_exist(self, service, conn):
        service.derive_api_model(
            [CodeEndpoint("GET", "/orders", "api.py", 1)],
            [SpecEndpoint("GET", "/orders", request_shape={"q": "str"},
                          auth_requirement=AuthRequirement.REQUIRED)],
        )
        row = conn.execute("SELECT shape_source, request_shape FROM api_endpoint").fetchone()
        assert row["shape_source"] == "specified"
        assert "q" in row["request_shape"]

    def test_discrepancies_are_persisted_symmetrically(self, service, conn):
        service.derive_api_model(
            [CodeEndpoint("GET", "/orders", "api.py", 1, status_codes=(200, 422))],
            [SpecEndpoint("GET", "/orders", status_codes=(200,))],
        )
        row = conn.execute(
            "SELECT source_a, claim_a, source_b, claim_b FROM discrepancy"
        ).fetchone()
        assert row["source_a"] != row["source_b"]
        assert row["claim_a"] and row["claim_b"]

    def test_nothing_writes_a_resolution(self, service, conn):
        # Resolution requires knowing intent, which is a human judgement.
        service.derive_api_model([], [SpecEndpoint("GET", "/ghost")])
        row = conn.execute("SELECT resolved_by, resolution FROM discrepancy").fetchone()
        assert row["resolved_by"] is None and row["resolution"] is None

    def test_a_recorded_discrepancy_is_retrievable_by_kind(self, service, conn):
        service.record_discrepancy(screen_not_in_live("checkout"))
        with unit_of_work(conn) as uow:
            assert len(uow.discrepancies.by_kind("screen-not-in-live")) == 1


class TestAnalysisUiModel:
    @pytest.fixture
    def service(self, conn, log):
        return AnalysisService(lambda: unit_of_work(conn), log)

    def test_screens_and_elements_are_stored(self, service, conn):
        report = service.upsert_ui_model({"screens": [
            {"name": "cart", "state": "empty", "elements": [
                {"role": "button", "accessible_name": "Checkout",
                 "locator_chain": ["getByRole"], "is_verified": True}]}
        ]}).value
        assert report.screens == 1 and report.ui_elements == 1
        assert conn.execute("SELECT is_verified FROM ui_element").fetchone()[0] == 1

    def test_unverified_locators_are_counted_and_flagged(self, service):
        # A locator that works and one that ought to are different facts.
        report = service.upsert_ui_model({"screens": [
            {"name": "cart", "elements": [
                {"role": "button", "is_verified": False},
                {"role": "link", "is_verified": False}]}
        ]}).value
        assert report.unverified_locators == 2
        assert "unverified" in report.to_dict()["note"]

    def test_verified_model_carries_no_warning_note(self, service):
        report = service.upsert_ui_model({"screens": [
            {"name": "cart", "elements": [{"role": "button", "is_verified": True}]}
        ]}).value
        assert "note" not in report.to_dict()

    def test_is_verified_defaults_to_false(self, service, conn):
        # Absence of confirmation is never read as confirmation.
        service.upsert_ui_model({"screens": [
            {"name": "cart", "elements": [{"role": "button"}]}]})
        assert conn.execute("SELECT is_verified FROM ui_element").fetchone()[0] == 0
