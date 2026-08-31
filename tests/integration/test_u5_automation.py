"""S6 AutomationService against a real database and a real file system.

The tests that matter most are the refusals: a literal credential writes nothing, a
non-automatable case produces no test, and a hand-edited config survives.
"""

from __future__ import annotations

import json

import pytest

from tto_testgen.adapters.playwright_emitter import PlaywrightEmitter
from tto_testgen.adapters.sqlite.repositories import unit_of_work
from tto_testgen.adapters.templates import TemplateEnvironment
from tto_testgen.domain.model import (
    AutomatabilityClass,
    EntityKind,
    LinkType,
    StageName,
    TestCase as Case,
    TestData as Data,
    TestStep as Step,
    TestType as Kind,
    TraceLink,
    UnitState,
    UnitStateRecord,
    encode_id,
)
from tto_testgen.platform.logging import configure
from tto_testgen.platform.result import ErrorCode
from tto_testgen.services.automation import AutomationService
from tto_testgen.services.runstate import RunStateService


def make_case(seq, feature_id, *, automatability=AutomatabilityClass.AUTOMATABLE,
              reason="", data=None, title=None, test_type=Kind.BOUNDARY):
    case_id = encode_id(EntityKind.TEST_CASE, "checkout", seq)
    return Case(
        id=case_id,
        feature_id=feature_id,
        coverage_item_id=encode_id(EntityKind.COVERAGE_ITEM, "checkout", 1),
        title=title or f"Reject quantity {seq}",
        test_type=test_type,
        priority="high",
        preconditions="A signed-in customer",
        steps=[Step(1, "Open the basket", "The basket is shown"),
               Step(2, f"Set quantity to {seq}", "Rejected")],
        expected_result="Rejected",
        test_data=[Data(*d, step_ordinal=2) for d in (data or [("quantity", str(seq), "boundary")])],
        automatability=automatability,
        automatability_reason=reason,
        tags=["checkout", "boundary"],
        trace_links=[TraceLink("test_case", case_id, "PAY-12", LinkType.DIRECT_STORY,
                               resolved_jira_key="PAY-12")],
    )


@pytest.fixture
def ready(conn, seeded):
    """Cases stored, the automation gate open, and one screen with elements."""
    with unit_of_work(conn) as uow:
        uow.cases.upsert_many([make_case(1, seeded)], "checkout")
        uow.run_state.set_state(
            UnitStateRecord(unit_ref="checkout", stage=StageName.CASES,
                            state=UnitState.COMPLETED, approved_by="lead",
                            approved_at="2026-08-30T00:00:00Z")
        )
        conn.execute(
            "INSERT INTO screen (feature_id, name, state, route, source) "
            "VALUES (:f, 'Checkout', 'default', '/basket', 'figma')",
            {"f": seeded},
        )
        screen_id = conn.execute("SELECT id FROM screen").fetchone()[0]
        conn.execute(
            "INSERT INTO ui_element (screen_id, role, accessible_name, locator_chain, "
            "is_verified, is_fragile) VALUES (:s, 'button', 'Place order', '[]', 1, 0)",
            {"s": screen_id},
        )
    return seeded


@pytest.fixture
def service(conn, tmp_path):
    emitter = PlaywrightEmitter(tmp_path / "automation", TemplateEnvironment())
    return AutomationService(
        lambda: unit_of_work(conn), RunStateService(lambda: unit_of_work(conn)),
        emitter, configure("CRITICAL"),
    )


# --- the happy path -------------------------------------------------------------

def test_a_feature_emits_a_runnable_project(service, ready, tmp_path):
    result = service.emit("checkout")
    assert result.ok, getattr(result, "message", "")
    report = result.value
    assert report.refusals == []
    assert len(report.tests_emitted) == 1
    assert report.tests_emitted[0].startswith("AT-CHECKOUT-")

    root = tmp_path / "automation"
    for expected in ("package.json", "playwright.config.ts", "tsconfig.json",
                     ".env.example", "README.md", "fixtures/auth.ts",
                     "tests/checkout.spec.ts", "pages/checkout.page.ts"):
        assert (root / expected).exists(), f"{expected} was not written"


def test_the_spec_carries_annotations_and_tags(service, ready, tmp_path):
    service.emit("checkout")
    spec = (tmp_path / "automation" / "tests" / "checkout.spec.ts").read_text()
    assert "TC-CHECKOUT-00001" in spec
    assert '"PAY-12"' in spec
    assert '"@checkout"' in spec


def test_an_automated_test_row_is_recorded_with_its_input_hash(service, ready, conn):
    service.emit("checkout")
    row = conn.execute("SELECT * FROM automated_test").fetchone()
    assert row["case_id"] == "TC-CHECKOUT-00001"
    assert len(row["input_hash"]) == 64
    assert row["spec_path"].endswith("checkout.spec.ts")


# --- gate ---------------------------------------------------------------------------

def test_a_closed_gate_stops_the_emission(service, conn, seeded, tmp_path):
    with unit_of_work(conn) as uow:
        uow.cases.upsert_many([make_case(1, seeded)], "checkout")
    result = service.emit("checkout")
    assert not result.ok
    assert result.code is ErrorCode.REJECTED_GATE_CLOSED
    assert not (tmp_path / "automation").exists()


# --- what is emitted ------------------------------------------------------------------

def test_a_manual_only_case_produces_no_test(service, conn, ready):
    with unit_of_work(conn) as uow:
        uow.cases.upsert_many(
            [make_case(2, ready, automatability=AutomatabilityClass.MANUAL_ONLY,
                       reason="requires visual judgement")],
            "checkout",
        )
    report = service.emit("checkout").value
    assert len(report.tests_emitted) == 1
    assert [n.case_id for n in report.not_automated] == ["TC-CHECKOUT-00002"]
    assert report.not_automated[0].reason == "requires visual judgement"


def test_needs_review_and_manual_only_are_reported_apart(service, conn, ready):
    """manual-only is a decision; needs-review is the absence of one, and the second
    is the actionable half."""
    with unit_of_work(conn) as uow:
        uow.cases.upsert_many(
            [make_case(2, ready, automatability=AutomatabilityClass.MANUAL_ONLY,
                       reason="visual judgement"),
             make_case(3, ready, automatability=AutomatabilityClass.NEEDS_REVIEW,
                       reason="no locator evidence")],
            "checkout",
        )
    report = service.emit("checkout").value.to_dict()
    assert report["not_automated_by_class"] == {"manual-only": 1, "needs-review": 1}


# --- secrets -------------------------------------------------------------------------------

def test_a_literal_credential_refuses_the_whole_emission(service, conn, ready, tmp_path):
    """Nothing is written. A partial project runs, and the missing tests look like
    passes."""
    with unit_of_work(conn) as uow:
        uow.cases.upsert_many(
            [make_case(2, ready, data=[("password", "hunter2", "valid")])], "checkout"
        )
    report = service.emit("checkout").value
    assert report.refusals
    assert report.refusals[0]["case_id"] == "TC-CHECKOUT-00002"
    assert "hunter2" not in json.dumps(report.refusals)
    assert not (tmp_path / "automation").exists()


def test_an_environment_url_refuses_the_emission(service, conn, ready):
    with unit_of_work(conn) as uow:
        uow.cases.upsert_many(
            [make_case(2, ready, data=[("endpoint", "https://staging.acme.co.uk/x", "valid")])],
            "checkout",
        )
    report = service.emit("checkout").value
    assert any("environment-url" in r["detail"] for r in report.refusals)


# --- determinism and hand-edits -----------------------------------------------------------------

def test_a_second_emission_writes_nothing(service, ready):
    """U5-NFR-REL-05. The assertion an operator can run before a handover, and the
    one that fails loudly if a determinism exclusion was forgotten."""
    service.emit("checkout")
    report = service.emit("checkout").value
    assert report.manifest["written"] == []
    assert len(report.manifest["unchanged"]) >= 8


def test_a_hand_edited_config_survives_regeneration(service, ready, tmp_path):
    service.emit("checkout")
    config = tmp_path / "automation" / "playwright.config.ts"
    config.write_text("// tuned by the engineer\nretries: 5\n", encoding="utf-8")

    report = service.emit("checkout").value

    assert str(config) in report.manifest["hand_edited"]
    assert "tuned by the engineer" in config.read_text(encoding="utf-8")


def test_a_corpus_change_rewrites_the_spec(service, conn, ready, tmp_path):
    service.emit("checkout")
    with unit_of_work(conn) as uow:
        uow.cases.upsert_many([make_case(2, ready)], "checkout")
    report = service.emit("checkout").value
    spec = str(tmp_path / "automation" / "tests" / "checkout.spec.ts")
    assert spec in report.manifest["written"]


# --- locators and risk -------------------------------------------------------------------------------

def test_a_test_on_unverified_locators_is_marked_at_risk(service, conn, ready):
    conn.execute("UPDATE ui_element SET is_verified = 0")
    report = service.emit("checkout").value
    assert report.at_risk == report.tests_emitted
    assert len(report.at_risk) == 1


def test_a_verified_locator_is_not_at_risk(service, ready):
    report = service.emit("checkout").value
    assert report.at_risk == []


def test_the_page_object_annotates_an_unverified_locator(service, conn, ready, tmp_path):
    conn.execute("UPDATE ui_element SET is_verified = 0")
    service.emit("checkout")
    page = (tmp_path / "automation" / "pages" / "checkout.page.ts").read_text()
    assert "UNVERIFIED" in page


# --- API cases ------------------------------------------------------------------------------------------

def test_api_cases_go_to_their_own_spec_sharing_the_fixture(service, conn, ready, tmp_path):
    with unit_of_work(conn) as uow:
        uow.cases.upsert_many([make_case(2, ready, test_type=Kind.API_CONTRACT)], "checkout")
    service.emit("checkout")
    api_spec = tmp_path / "automation" / "tests" / "checkout.api.spec.ts"
    assert api_spec.exists()
    assert "from '../fixtures/auth'" in api_spec.read_text()


# --- the report -------------------------------------------------------------------------------------------

def test_the_automation_report_counts_at_risk_tests(service, conn, ready):
    conn.execute("UPDATE ui_element SET is_verified = 0")
    service.emit("checkout")
    report = service.automation_report("checkout").value
    assert report["total_tests"] == 1
    assert report["at_risk_total"] == 1
    assert "unconfirmed, not wrong" in report["derivation"]
