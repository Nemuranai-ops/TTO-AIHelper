"""S8 ReportingService against a real database.

The most important test is the one on an empty corpus: a report that fails whole
because one section has no data is useless during the period it would be most useful.
"""

from __future__ import annotations

import csv
import io

import pytest

from tto_testgen.adapters.report_renderer import ReportRenderer, SectionStatus
from tto_testgen.adapters.sqlite.repositories import unit_of_work
from tto_testgen.domain.model import (
    AutomatabilityClass,
    AutomatedTest,
    EntityKind,
    LinkType,
    TestCase as Case,
    TestData as Data,
    TestStep as Step,
    TestType as Kind,
    TraceLink,
    encode_id,
)
from tto_testgen.platform.logging import configure
from tto_testgen.services.reporting import GAP_CATEGORIES, REPORTS, SECTIONS, ReportingService

CASE_ID = encode_id(EntityKind.TEST_CASE, "checkout", 1)


@pytest.fixture
def service(conn, tmp_path):
    return ReportingService(
        lambda: unit_of_work(conn),
        ReportRenderer(tmp_path / "reports"),
        configure("CRITICAL"),
    )


@pytest.fixture
def populated(conn, seeded):
    with unit_of_work(conn) as uow:
        uow.cases.upsert_many(
            [Case(
                id=CASE_ID, feature_id=seeded,
                coverage_item_id=encode_id(EntityKind.COVERAGE_ITEM, "checkout", 1),
                title="Reject an empty basket", test_type=Kind.BOUNDARY,
                steps=[Step(1, "Open the basket", "Shown")], expected_result="Shown",
                test_data=[Data("quantity", "0", "boundary", step_ordinal=1)],
                automatability=AutomatabilityClass.AUTOMATABLE, tags=["checkout"],
                trace_links=[TraceLink("test_case", CASE_ID, "PAY-12",
                                       LinkType.DIRECT_STORY, resolved_jira_key="PAY-12")],
            )],
            "checkout",
        )
        uow.automation.upsert(AutomatedTest(
            id=encode_id(EntityKind.AUTOMATED_TEST, "checkout", 1), case_id=CASE_ID,
            spec_path="tests/checkout.spec.ts", test_name="a test",
        ))
        uow.gaps.add({"category": "manual-only", "subject": "TC-CHECKOUT-00002",
                      "feature_slug": "checkout", "detail": "visual judgement"})
    return seeded


# --- the registry ---------------------------------------------------------------

def test_every_section_declares_a_precondition_and_a_derivation():
    """The registry makes this structural rather than a convention."""
    for spec in SECTIONS:
        assert spec.precondition is not None
        assert spec.derivation, spec.name
        assert spec.columns, spec.name
        assert spec.report in REPORTS, spec.name


# --- a populated corpus ------------------------------------------------------------

def test_the_coverage_report_states_planned_against_generated(service, populated):
    report = service.build("coverage").value
    section = next(s for s in report.sections if s.name == "by-feature")
    assert section.status is SectionStatus.COMPUTED
    row = section.rows[0]
    assert row["planned"] == 3 and row["generated"] == 1
    assert row["variance"] == -2
    assert "planned_count" in section.derivation


def test_the_gap_report_lists_every_category_including_empty_ones(service, populated):
    """An absent category is indistinguishable from one nobody checked."""
    report = service.build("gaps").value
    summary = next(s for s in report.sections if s.name == "summary")
    assert {r["category"] for r in summary.rows} == set(GAP_CATEGORIES)
    assert next(r for r in summary.rows if r["category"] == "manual-only")["open"] == 1
    assert next(r for r in summary.rows if r["category"] == "reduced-depth")["open"] == 0


def test_the_automation_report_lists_tests_and_deferrals(service, conn, populated):
    with unit_of_work(conn) as uow:
        uow.cases.upsert_many(
            [Case(
                id=encode_id(EntityKind.TEST_CASE, "checkout", 2), feature_id=populated,
                coverage_item_id=encode_id(EntityKind.COVERAGE_ITEM, "checkout", 1),
                title="Confirm the layout", test_type=Kind.UI_BEHAVIOUR,
                steps=[Step(1, "Look", "Correct")], expected_result="Correct",
                automatability=AutomatabilityClass.MANUAL_ONLY,
                automatability_reason="requires visual judgement",
                trace_links=[TraceLink("test_case", "x", "PAY-12",
                                       LinkType.DIRECT_STORY, resolved_jira_key="PAY-12")],
            )],
            "checkout",
        )
    report = service.build("automation").value
    tests = next(s for s in report.sections if s.name == "tests")
    deferred = next(s for s in report.sections if s.name == "deferred")
    assert len(tests.rows) == 1
    assert deferred.rows[0]["reason"] == "requires visual judgement"


def test_every_report_writes_markdown_and_csv(service, populated, tmp_path):
    result = service.generate().value
    names = {p.rsplit("/", 1)[-1] for p in result["files_written"]}
    assert "coverage.md" in names and "gaps.md" in names
    assert any(n.endswith(".csv") for n in names)


def test_a_csv_section_round_trips(service, populated, tmp_path):
    service.generate(["coverage"])
    path = tmp_path / "reports" / "coverage-by-feature.csv"
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"))))
    assert rows[0][0] == "feature"
    assert rows[1][0] == "checkout"


# --- an empty corpus -------------------------------------------------------------------

def test_a_report_on_an_empty_corpus_renders_rather_than_failing(service, conn):
    """The period the report is most useful is the one where it has least data."""
    result = service.generate()
    assert result.ok
    assert result.value["sections_unavailable"], "sections without data should be named"


def test_an_unavailable_section_names_its_producing_stage(service, conn):
    report = service.build("coverage").value
    section = next(s for s in report.sections if s.name == "by-feature")
    assert section.status is SectionStatus.NOT_AVAILABLE
    assert section.producing_stage == "coverage"
    assert "coverage model" in section.unavailable_reason


def test_the_gap_report_is_available_from_the_very_first_run(service, conn):
    """Gaps have no precondition, deliberately: 'no requirements yet' is itself the
    useful finding at that point."""
    report = service.build("gaps").value
    assert all(s.status is SectionStatus.COMPUTED for s in report.sections)


def test_an_unknown_report_is_refused(service):
    result = service.build("nonsense")
    assert not result.ok
    assert "coverage" in result.remediation


# --- determinism ---------------------------------------------------------------------------

def test_two_generations_produce_identical_bytes(service, populated, tmp_path):
    service.generate(["coverage"])
    first = (tmp_path / "reports" / "coverage.md").read_bytes()
    service.generate(["coverage"])
    assert (tmp_path / "reports" / "coverage.md").read_bytes() == first


def test_a_retired_case_leaves_the_coverage_count(service, conn, populated):
    """Retirement takes effect through queries that already filter on is_obsolete -
    no separate step."""
    before = next(
        s for s in service.build("coverage").value.sections if s.name == "by-feature"
    ).rows[0]["generated"]
    with unit_of_work(conn) as uow:
        uow.cases.mark_obsolete(CASE_ID, "requirement deleted", 1)
    after = next(
        s for s in service.build("coverage").value.sections if s.name == "by-feature"
    ).rows[0]["generated"]
    assert before == 1 and after == 0
