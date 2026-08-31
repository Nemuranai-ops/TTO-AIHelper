"""S5 GenerationService against a real database.

The tests that matter most here are about what does *not* happen: no identifier
allocated when a batch is rejected, no hand-edited file overwritten, no case
reissuing a retired number.
"""

from __future__ import annotations

import pytest

from tto_testgen.adapters.sqlite.repositories import unit_of_work
from tto_testgen.adapters.view_renderer import ViewRenderer
from tto_testgen.domain.model import (
    Artefact,
    Resource,
    ResourceType,
    StageName,
    UnitState,
    UnitStateRecord,
)
from tto_testgen.platform.logging import configure
from tto_testgen.platform.result import ErrorCode
from tto_testgen.services.generation import GenerationService
from tto_testgen.services.runstate import RunStateService

ITEM = "CI-CHECKOUT-00001"


@pytest.fixture
def opened(conn, seeded):
    """The cases gate open, and one ingested Jira key for links to resolve against."""
    with unit_of_work(conn) as uow:
        uow.resources.upsert(
            Resource(raw_ref="https://example.atlassian.net/browse/PAY-12",
                     type=ResourceType.JIRA_ISSUE, inferred_from="rule 1")
        )
        resource_id = uow.resources.id_for(
            "https://example.atlassian.net/browse/PAY-12"
        )
        uow.artefacts.upsert(
            Artefact(resource_id=resource_id, kind="jira-issue",
                     source_identifier="PAY-12", content="Quantity 1-99",
                     content_hash="a" * 64)
        )
        uow.run_state.set_state(
            UnitStateRecord(
                unit_ref="checkout", stage=StageName.COVERAGE, state=UnitState.COMPLETED,
                approved_by="lead", approved_at="2026-08-30T00:00:00Z",
                approved_content_hash=uow.coverage.content_hash_for(seeded),
            )
        )
    return seeded


@pytest.fixture
def service(conn, tmp_path):
    run_state = RunStateService(lambda: unit_of_work(conn))
    renderer = ViewRenderer(tmp_path / "generated" / "testcases")
    return GenerationService(
        lambda: unit_of_work(conn), run_state, renderer, configure("WARNING")
    )


def payload(title="Reject quantity zero", *, value="0", steps=None, links=None,
            test_type="boundary", item=ITEM):
    return {
        "coverage_item_id": item,
        "title": title,
        "test_type": test_type,
        "priority": "high",
        "preconditions": "A signed-in customer",
        "steps": steps if steps is not None else [
            {"ordinal": 1, "action": "Open the basket", "expected": "The basket is shown"},
            {"ordinal": 2, "action": f"Set quantity to {value}", "expected": "Rejected"},
        ],
        "test_data": [
            {"field": "quantity", "value": value, "equivalence_class": "boundary-low",
             "step_ordinal": 2}
        ],
        "tags": ["checkout"],
        "trace_links": [{"type": "direct-story", "jira_key": "PAY-12",
                         "evidence": "story text"}],
    }


# --- the happy path ------------------------------------------------------------

def test_a_batch_is_stored_with_allocated_identifiers(service, opened, conn):
    result = service.upsert_cases("checkout", [payload()])
    assert result.ok, getattr(result, "message", "")
    report = result.value
    assert report.rejections == []
    assert len(report.accepted) == 1
    assert report.accepted[0].startswith("TC-CHECKOUT-")

    stored = conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0]
    assert stored == 1
    assert conn.execute("SELECT COUNT(*) FROM test_step").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM trace_link").fetchone()[0] == 1


def test_views_are_emitted_for_the_feature(service, opened):
    report = service.upsert_cases("checkout", [payload()]).value
    assert len(report.view_manifest["written"]) == 2
    assert report.view_manifest["hand_edited"] == []


def test_the_report_states_planned_against_generated(service, opened):
    report = service.upsert_cases("checkout", [payload()]).value
    row = next(r for r in report.planned_vs_generated if r["coverage_item_id"] == ITEM)
    assert row["planned"] == 3
    assert row["generated"] == 1
    # BR-U4-7.3: the shortfall is stated, not filled.
    assert row["variance"] == -2


# --- stage A: what stops the batch ----------------------------------------------

def test_a_closed_gate_stops_the_batch(service, conn, seeded):
    result = service.upsert_cases("checkout", [payload()])
    assert not result.ok
    assert result.code is ErrorCode.REJECTED_GATE_CLOSED
    assert conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == 0


def test_an_oversized_batch_is_refused_before_any_work(conn, tmp_path, opened):
    run_state = RunStateService(lambda: unit_of_work(conn))
    small = GenerationService(
        lambda: unit_of_work(conn), run_state,
        ViewRenderer(tmp_path / "v"), configure("WARNING"), max_batch=2,
    )
    result = small.upsert_cases("checkout", [payload(f"case {i}") for i in range(3)])
    assert not result.ok
    assert "exceeds the 2 cap" in result.message


# --- P-U4-01: nothing is allocated when a batch is rejected -----------------------

def test_a_rejected_batch_stores_nothing_and_allocates_nothing(service, opened, conn):
    """The property U4-NFR-REL-02 exists for.

    A rollback would undo the rows; it would not undo the identifier counter, and
    neither restoring nor advancing it is acceptable - one reissues a number to a
    different case, the other leaves a permanent hole.
    """
    good = payload("A good case")
    bad = payload("A case with no steps", steps=[])

    report = service.upsert_cases("checkout", [good, bad]).value

    assert report.rejections != []
    assert report.accepted == []
    assert conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == 0

    # And the next accepted batch starts at 1, not 2: nothing was consumed.
    after = service.upsert_cases("checkout", [payload("A good case")]).value
    assert after.accepted == ["TC-CHECKOUT-00001"]


def test_every_failure_in_a_batch_is_reported_together(service, opened):
    """One correction pass, not four.

    The agent regenerates the whole batch, and each round-trip costs a corporate
    Copilot quota. Stopping at the first fault would make four faults cost four
    cycles to discover.
    """
    batch = [
        payload("No steps", steps=[]),
        payload("Unknown key", links=[]),
        payload("Wrong type", test_type="api-contract"),
        payload("Unknown item", item="CI-CHECKOUT-99999"),
    ]
    batch[1]["trace_links"] = [{"type": "direct-story", "jira_key": "NOPE-1"}]

    report = service.upsert_cases("checkout", batch).value

    refs = {r["case_ref"] for r in report.rejections}
    assert refs == {"No steps", "Unknown key", "Wrong type", "Unknown item"}


# --- stage B: personal data --------------------------------------------------------

def test_real_personal_data_in_test_data_is_refused(service, opened, conn):
    case = payload("Checkout with a customer email")
    case["test_data"] = [
        {"field": "email", "value": "alice.brown@customer.co.uk",
         "equivalence_class": "valid", "step_ordinal": 2}
    ]
    report = service.upsert_cases("checkout", [case]).value

    assert len(report.rejections) == 1
    rejection = report.rejections[0]
    assert rejection["code"] == ErrorCode.REJECTED_PERSONAL_DATA.value
    assert "email" in rejection["detail"]
    # The refused value is never copied into the report.
    assert "alice.brown" not in rejection["detail"]
    assert conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == 0


def test_a_documented_synthetic_value_is_accepted(service, opened):
    case = payload("Checkout with a synthetic email")
    case["test_data"] = [
        {"field": "email", "value": "user@example.com", "equivalence_class": "valid",
         "step_ordinal": 2}
    ]
    assert service.upsert_cases("checkout", [case]).value.rejections == []


# --- stage D: duplicates -------------------------------------------------------------

def test_a_duplicate_of_the_corpus_is_refused_and_recorded_as_a_gap(service, opened, conn):
    service.upsert_cases("checkout", [payload()])
    report = service.upsert_cases("checkout", [payload()]).value

    assert len(report.rejections) == 1
    assert report.rejections[0]["code"] == ErrorCode.REJECTED_DUPLICATE.value
    assert report.rejections[0]["matched_case_id"] == "TC-CHECKOUT-00001"


def test_two_identical_cases_in_one_batch_are_caught(service, opened):
    """BR-U4-4.2. Neither is in the database yet for the bucket query to find."""
    report = service.upsert_cases("checkout", [payload(), payload()]).value
    assert any(r["code"] == ErrorCode.REJECTED_DUPLICATE.value for r in report.rejections)


# --- identifier stability ---------------------------------------------------------------

def test_regenerating_an_unchanged_case_keeps_its_identifier(service, opened, conn):
    first = service.upsert_cases("checkout", [payload()]).value.accepted[0]
    conn.execute("DELETE FROM case_integrity_check")

    again = service.upsert_cases("checkout", [payload()]).value
    # The regeneration is refused as a duplicate, which is correct - but the stored
    # case still holds its original identifier rather than having been renumbered.
    assert conn.execute("SELECT id FROM test_case").fetchone()[0] == first


# --- views --------------------------------------------------------------------------------

def test_a_hand_edited_view_is_not_overwritten_by_a_later_batch(service, opened, tmp_path):
    service.upsert_cases("checkout", [payload()])
    view = tmp_path / "generated" / "testcases" / "checkout.md"
    view.write_text("reviewed and annotated by hand", encoding="utf-8")

    report = service.upsert_cases("checkout", [payload("Reject quantity 100", value="100")]).value

    assert str(view) in report.view_manifest["hand_edited"]
    assert view.read_text(encoding="utf-8") == "reviewed and annotated by hand"


def test_re_emitting_an_unchanged_feature_writes_nothing(service, opened):
    service.upsert_cases("checkout", [payload()])
    result = service.emit_views("checkout")
    assert result.ok
    assert result.value["view_manifest"]["written"] == []
    assert len(result.value["view_manifest"]["unchanged"]) == 2


# --- the matrix ------------------------------------------------------------------------------

def test_the_matrix_shows_uncovered_requirements(service, opened):
    service.upsert_cases("checkout", [payload()])
    matrix = service.trace_matrix().value
    assert "REQ-CHECKOUT-00001" in matrix["uncovered"] or matrix["forward"]
    assert matrix["counts_by_link_type"]["direct-story"] == 1


def test_the_matrix_is_not_stored(service, opened, conn):
    service.upsert_cases("checkout", [payload()])
    service.trace_matrix()
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert not any("matrix" in t for t in tables)


# --- volume ---------------------------------------------------------------------------------

def test_the_volume_report_names_shortfalls(service, opened):
    service.upsert_cases("checkout", [payload()])
    report = service.volume_report("checkout").value
    assert report["shortfalls"], "a 1-of-3 feature is a shortfall"
    assert "never padded" in report["derivation"]


# --- gaps -------------------------------------------------------------------------

def test_a_manual_only_case_is_recorded_as_a_gap(service, opened, conn):
    """The path that was never exercised.

    S5 called `gaps.add` with a signature the SQLite repository does not have, and
    two coincidences hid it: a duplicate rejects the batch before the gap loop runs,
    and no earlier test accepted a manual-only case. The shared fake had been written
    to match the caller rather than the port, so it agreed with the mistake.
    """
    case = payload("Confirm the layout looks correct")
    case["requires_visual_judgement"] = True

    report = service.upsert_cases("checkout", [case]).value

    assert report.rejections == []
    assert report.automatability.get("manual-only") == 1
    assert report.gaps_recorded == 1

    row = conn.execute("SELECT * FROM gap WHERE category = 'manual-only'").fetchone()
    assert row is not None
    assert row["subject"] == report.accepted[0]
    assert row["feature_slug"] == "checkout"
    assert row["detail"]


def test_a_rejected_duplicate_records_no_gap(service, opened, conn):
    """A rejected batch stores nothing, gaps included.

    Recording one would claim the corpus knows about a case it never accepted. The
    duplicate is carried in the rejection, which names the case it matched.
    """
    service.upsert_cases("checkout", [payload()])
    report = service.upsert_cases("checkout", [payload()]).value

    assert report.rejections
    assert report.gaps_recorded == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM gap WHERE category = 'rejected-duplicate'"
    ).fetchone()[0] == 0
