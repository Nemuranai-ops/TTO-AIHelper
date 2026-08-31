"""S9 DeltaService against a real database.

The load-bearing test is `test_a_partial_detection_does_not_advance_the_baseline`.
Its failure would be permanent and silent: the next run would compare from the newer
head, so every change in the window the failed source covered would be skipped for
ever, and nothing downstream would ever reveal it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from tto_testgen.adapters.change_detector import DeltaBaseline, DetectionResult
from tto_testgen.adapters.sqlite.repositories import unit_of_work
from tto_testgen.domain.impact import ChangedRef
from tto_testgen.domain.model import (
    EntityKind,
    LinkType,
    Run,
    TestCase as Case,
    TestStep as Step,
    TestType as Kind,
    TraceLink,
    encode_id,
)
from tto_testgen.platform.logging import configure
from tto_testgen.services.delta import DeltaService, advance_baseline
from tto_testgen.services.runstate import RunStateService

CASE_ID = encode_id(EntityKind.TEST_CASE, "checkout", 1)


@dataclass
class StubDetector:
    result: DetectionResult = field(default_factory=DetectionResult)
    seen: list[DeltaBaseline] = field(default_factory=list)

    def detect(self, baseline: DeltaBaseline) -> DetectionResult:
        self.seen.append(baseline)
        return self.result


@dataclass
class RecordingRunState:
    advanced: list[tuple] = field(default_factory=list)

    def record_baseline(self, run_id, head_commits, jira_watermark):
        self.advanced.append((run_id, head_commits, jira_watermark))


def build(conn, detector):
    return DeltaService(
        lambda: unit_of_work(conn), RunStateService(lambda: unit_of_work(conn)),
        detector, configure("CRITICAL"),
    )


@pytest.fixture
def corpus(conn, seeded):
    with unit_of_work(conn) as uow:
        uow.cases.upsert_many(
            [Case(
                id=CASE_ID, feature_id=seeded,
                coverage_item_id=encode_id(EntityKind.COVERAGE_ITEM, "checkout", 1),
                title="Reject an empty basket", test_type=Kind.BOUNDARY,
                steps=[Step(1, "Open the basket", "Shown")], expected_result="Shown",
                trace_links=[TraceLink("test_case", CASE_ID, "PAY-12",
                                       LinkType.DIRECT_STORY, resolved_jira_key="PAY-12")],
            )],
            "checkout",
        )
    return seeded


@pytest.fixture
def completed_run(conn):
    with unit_of_work(conn) as uow:
        uow.run_state.start_run(Run(correlation_id="c1", kind="baseline",
                                    started_at="2026-08-30T00:00:00Z"))
        run_id = conn.execute("SELECT id FROM run ORDER BY id DESC LIMIT 1").fetchone()[0]
        uow.run_state.record_baseline(run_id, {"app": "abc123"}, "2026-08-30T00:00:00Z")
        uow.run_state.complete_run(run_id)
    return run_id


# --- the baseline guard, in isolation --------------------------------------------

def test_advance_baseline_refuses_when_a_source_failed():
    """P-U8-01. Advancing here would make the undetected changes invisible for ever."""
    state = RecordingRunState()
    detection = DetectionResult(
        head_commits={"app": "def456"}, jira_watermark="2026-08-31T00:00:00Z",
        unavailable_sources=[("bitbucket:app", "connection refused")],
    )
    assert advance_baseline(7, detection, state) is False
    assert state.advanced == []


def test_advance_baseline_advances_when_every_source_answered():
    state = RecordingRunState()
    detection = DetectionResult(head_commits={"app": "def456"},
                                jira_watermark="2026-08-31T00:00:00Z")
    assert advance_baseline(7, detection, state) is True
    assert state.advanced == [(7, {"app": "def456"}, "2026-08-31T00:00:00Z")]


# --- no baseline -------------------------------------------------------------------

def test_a_first_run_with_no_baseline_says_so_and_stops(conn, corpus):
    """Treating 'no baseline' as 'everything changed' would classify the whole corpus
    as affected - true, unhelpful, and it would obscure the real answer."""
    report = build(conn, StubDetector()).detect().value
    assert report.baseline_run_id is None
    assert "no completed run" in report.no_baseline_reason
    assert report.retired == []


def test_a_failed_run_is_not_a_baseline(conn, corpus):
    """`ended_at` is null on a run that failed partway, so it is not eligible."""
    with unit_of_work(conn) as uow:
        uow.run_state.start_run(Run(correlation_id="c1", kind="baseline",
                                    started_at="2026-08-30T00:00:00Z"))
    report = build(conn, StubDetector()).detect().value
    assert report.baseline_run_id is None


def test_the_baseline_is_the_last_completed_run(conn, corpus, completed_run):
    detector = StubDetector()
    build(conn, detector).detect()
    assert detector.seen[0].run_id == completed_run
    assert detector.seen[0].head_commits == {"app": "abc123"}


# --- the guard in the service ------------------------------------------------------------

def test_a_partial_detection_does_not_advance_the_baseline(conn, corpus, completed_run):
    """The test this unit exists for.

    Its failure is permanent and silent: the next run compares from the newer head,
    so everything in the window the failed source covered is skipped for ever.
    """
    detector = StubDetector(DetectionResult(
        head_commits={"app": "def456"},
        unavailable_sources=[("jira", "401 unauthorised")],
    ))
    report = build(conn, detector).detect(run_id=completed_run).value

    assert report.baseline_advanced is False
    row = conn.execute("SELECT head_commits FROM run WHERE id = ?", (completed_run,)).fetchone()
    assert "abc123" in row["head_commits"], "the baseline must not have moved"


def test_a_complete_detection_advances_the_baseline(conn, corpus, completed_run):
    detector = StubDetector(DetectionResult(
        head_commits={"app": "def456"}, jira_watermark="2026-08-31T00:00:00Z",
    ))
    report = build(conn, detector).detect(run_id=completed_run).value

    assert report.baseline_advanced is True
    row = conn.execute("SELECT head_commits FROM run WHERE id = ?", (completed_run,)).fetchone()
    assert "def456" in row["head_commits"]


def test_the_report_names_the_unreachable_source(conn, corpus, completed_run):
    detector = StubDetector(DetectionResult(
        unavailable_sources=[("bitbucket:app", "connection refused")],
    ))
    report = build(conn, detector).detect(run_id=completed_run).value
    assert report.detection["unavailable_sources"][0]["source"] == "bitbucket:app"
    assert report.detection["complete"] is False


# --- classification and retirement ----------------------------------------------------------

def test_an_unmapped_change_is_reported_not_assumed_harmless(conn, corpus, completed_run):
    """'We found no link' and 'there is no impact' are different statements."""
    detector = StubDetector(DetectionResult(
        changes=[ChangedRef(ref="src/untraced.py", source="bitbucket", kind="modified")],
        head_commits={"app": "def456"},
    ))
    report = build(conn, detector).detect(run_id=completed_run).value
    assert report.unmapped == [
        {"ref": "src/untraced.py", "source": "bitbucket", "kind": "modified"}
    ]


def test_a_removed_target_retires_its_case(conn, corpus, completed_run):
    detector = StubDetector(DetectionResult(
        changes=[ChangedRef(ref="PAY-12", source="bitbucket", kind="removed")],
        head_commits={"app": "def456"},
    ))
    report = build(conn, detector).detect(run_id=completed_run).value

    assert [r["case_id"] for r in report.retired] == [CASE_ID]
    row = conn.execute("SELECT * FROM test_case WHERE id = ?", (CASE_ID,)).fetchone()
    assert row["is_obsolete"] == 1
    assert row["obsolete_reason"]
    assert row["obsoleted_by_change_id"] == report.change_event_id


def test_retirement_deletes_nothing(conn, corpus, completed_run):
    """Steps, data, links and the automated test all remain and stay readable."""
    steps_before = conn.execute("SELECT COUNT(*) FROM test_step").fetchone()[0]
    links_before = conn.execute("SELECT COUNT(*) FROM trace_link").fetchone()[0]

    detector = StubDetector(DetectionResult(
        changes=[ChangedRef(ref="PAY-12", source="bitbucket", kind="removed")],
        head_commits={"app": "def456"},
    ))
    build(conn, detector).detect(run_id=completed_run)

    assert conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM test_step").fetchone()[0] == steps_before
    assert conn.execute("SELECT COUNT(*) FROM trace_link").fetchone()[0] == links_before


def test_a_requires_update_case_is_reported_and_left_untouched(conn, corpus, completed_run):
    """Regenerating would bypass every gate the baseline had to pass."""
    before = dict(conn.execute("SELECT * FROM test_case WHERE id = ?", (CASE_ID,)).fetchone())

    detector = StubDetector(DetectionResult(
        changes=[ChangedRef(ref="PAY-12", source="jira", kind="modified")],
        jira_watermark="2026-08-31T00:00:00Z",
    ))
    report = build(conn, detector).detect(run_id=completed_run).value

    assert [r["case_id"] for r in report.requires_update] == [CASE_ID]
    assert report.retired == []
    after = dict(conn.execute("SELECT * FROM test_case WHERE id = ?", (CASE_ID,)).fetchone())
    assert after == before


def test_a_change_event_is_recorded(conn, corpus, completed_run):
    detector = StubDetector(DetectionResult(
        changes=[ChangedRef(ref="PAY-12", source="jira", kind="modified")],
    ))
    report = build(conn, detector).detect(run_id=completed_run).value
    row = conn.execute("SELECT * FROM change_event WHERE id = ?",
                       (report.change_event_id,)).fetchone()
    assert row is not None
    assert "PAY-12" in row["changed_refs"]


# --- the boundary -----------------------------------------------------------------------------

def test_the_service_cannot_create_a_requirement_or_a_case(conn):
    """FR-DLT-06 by absence, for the fourth and last time in this system."""
    service = build(conn, StubDetector())
    for forbidden in ("create_case", "create_requirement", "regenerate",
                      "upsert_cases", "upsert_requirements"):
        assert not hasattr(service, forbidden), f"S9 must not expose {forbidden}"


def test_baseline_status_reports_what_the_next_run_would_compare_against(conn, completed_run):
    status = build(conn, StubDetector()).baseline_status().value
    assert status["has_baseline"] is True
    assert status["head_commits"] == {"app": "abc123"}
