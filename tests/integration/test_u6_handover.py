"""S7 HandoverService against a real database and file system.

Every toolchain path runs through the fake runner, because the suite must pass on a
machine with no Node — that being a feature of this unit rather than a limitation of
the test environment.
"""

from __future__ import annotations

import json

import pytest

from tests.fakes.commands import FakeCommandRunner, failing, timing_out
from tto_testgen.adapters.sqlite.repositories import unit_of_work
from tto_testgen.adapters.structural_verifier import REQUIRED_FILES, StructuralVerifier
from tto_testgen.domain.model import (
    AutomatabilityClass,
    AutomatedTest,
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
from tto_testgen.services.handover import CheckStatus, HandoverService, PROJECT_SLUG

CASE_ID = encode_id(EntityKind.TEST_CASE, "checkout", 1)
TEST_ID = encode_id(EntityKind.AUTOMATED_TEST, "checkout", 1)


@pytest.fixture
def project(tmp_path):
    """A complete generated project, as U5 would have left it."""
    root = tmp_path / "automation"
    for relative in REQUIRED_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// generated\n", encoding="utf-8")
    (root / ".env.example").write_text("TAAS_BASE_URL=\n", encoding="utf-8")
    (root / "pages").mkdir(exist_ok=True)
    (root / "pages" / "checkout.page.ts").write_text("export class CheckoutPage {}\n",
                                                     encoding="utf-8")
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "checkout.spec.ts").write_text(
        "import { test } from '../fixtures/auth';\n"
        "import { CheckoutPage } from '../pages/checkout.page';\n"
        f"test('{CASE_ID} Reject an empty basket', async () => {{}});\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def corpus(conn, seeded):
    """One automatable case with an automated test recorded against it."""
    with unit_of_work(conn) as uow:
        uow.cases.upsert_many(
            [
                Case(
                    id=CASE_ID, feature_id=seeded,
                    coverage_item_id=encode_id(EntityKind.COVERAGE_ITEM, "checkout", 1),
                    title="Reject an empty basket", test_type=Kind.BOUNDARY,
                    steps=[Step(1, "Open the basket", "Shown")],
                    expected_result="Shown",
                    test_data=[Data("quantity", "0", "boundary", step_ordinal=1)],
                    automatability=AutomatabilityClass.AUTOMATABLE,
                    tags=["checkout"],
                    trace_links=[TraceLink("test_case", CASE_ID, "PAY-12",
                                           LinkType.DIRECT_STORY,
                                           resolved_jira_key="PAY-12")],
                )
            ],
            "checkout",
        )
        uow.automation.upsert(
            AutomatedTest(id=TEST_ID, case_id=CASE_ID,
                          spec_path="tests/checkout.spec.ts",
                          test_name=f"{CASE_ID} Reject an empty basket")
        )
        uow.run_state.set_state(
            UnitStateRecord(unit_ref=PROJECT_SLUG, stage=StageName.AUTOMATION,
                            state=UnitState.COMPLETED, approved_by="engineer",
                            approved_at="2026-08-30T00:00:00Z")
        )
    return seeded


def build(conn, project, runner=None, **kwargs):
    from tto_testgen.services.runstate import RunStateService

    return HandoverService(
        lambda: unit_of_work(conn),
        RunStateService(lambda: unit_of_work(conn)),
        StructuralVerifier(),
        runner or FakeCommandRunner(),
        configure("CRITICAL"),
        project_root=project,
        **kwargs,
    )


# --- the happy path ---------------------------------------------------------------

def test_a_complete_project_is_ready(conn, project, corpus):
    service = build(conn, project)
    result = service.assemble()
    assert result.ok, getattr(result, "message", "")
    report = result.value
    assert report.is_ready
    assert report.structural.status is CheckStatus.PASSED
    assert report.toolchain.status is CheckStatus.PASSED
    assert report.reconciliation.status is CheckStatus.PASSED


def test_assembly_adds_the_three_files_u5_cannot_produce(conn, project, corpus):
    build(conn, project).assemble()
    assert (project / ".gitignore").exists()
    assert (project / "handover-manifest.json").exists()
    assert (project / "handover-manifest.md").exists()


def test_the_gitignore_excludes_the_env_file(conn, project, corpus):
    """.env.example is committed; .env holds the real credentials the engineer fills
    in, and a project inviting them to create it without excluding it invites a
    credential into the repository."""
    (project / ".gitignore").unlink()
    build(conn, project).assemble()
    content = (project / ".gitignore").read_text(encoding="utf-8")
    assert "\n.env\n" in content
    assert "node_modules/" in content


def test_the_manifest_lists_every_test_with_its_provenance(conn, project, corpus):
    build(conn, project).assemble()
    manifest = json.loads((project / "handover-manifest.json").read_text(encoding="utf-8"))
    entry = manifest["entries"][0]
    assert entry["case_id"] == CASE_ID
    assert entry["jira_key"] == "PAY-12"
    assert entry["tags"] == ["checkout"]


def test_manifest_spec_paths_are_relative(conn, project, corpus):
    """The manifest is committed and read on other machines; an absolute path would
    name the generating workstation."""
    build(conn, project).assemble()
    manifest = json.loads((project / "handover-manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["entries"]:
        assert not entry["spec_path"].startswith("/")


def test_the_manifest_states_the_corpus_totals(conn, project, corpus):
    """The Test Lead's question is not 'how many tests' but 'what proportion of the
    corpus is this, and what is not here'."""
    build(conn, project).assemble()
    manifest = json.loads((project / "handover-manifest.json").read_text(encoding="utf-8"))
    for key in ("automated", "manual_only", "needs_review", "corpus_total"):
        assert key in manifest["totals"]


def test_the_outcome_is_recorded_in_unit_state(conn, project, corpus):
    build(conn, project).assemble()
    row = conn.execute(
        "SELECT * FROM unit_state WHERE unit_ref = ? AND stage = 'handover'",
        (PROJECT_SLUG,),
    ).fetchone()
    assert row is not None
    assert json.loads(row["metrics"])["is_ready"] is True


# --- the gate ------------------------------------------------------------------------

def test_a_closed_gate_stops_assembly(conn, project, seeded):
    result = build(conn, project).assemble()
    assert not result.ok
    assert result.code is ErrorCode.REJECTED_GATE_CLOSED


def test_a_missing_project_is_reported_not_assumed(conn, tmp_path, corpus):
    result = build(conn, tmp_path / "nothing-here").assemble()
    assert not result.ok
    assert "automation_emit" in result.remediation


# --- structural failures block --------------------------------------------------------

def test_a_broken_import_blocks_readiness_and_names_the_file(conn, project, corpus):
    """US-HND-02 AC4, caught without a compiler."""
    (project / "tests" / "basket.spec.ts").write_text(
        "import { BasketPage } from '../pages/basket.page';\n", encoding="utf-8"
    )
    report = build(conn, project).assemble().value
    assert not report.is_ready
    assert report.structural.status is CheckStatus.FAILED
    blocking = report.blocking()
    assert any("basket.page" in b["name"] for b in blocking)
    assert all(b["location"] for b in blocking)


def test_a_missing_required_file_blocks_readiness(conn, project, corpus):
    (project / "tsconfig.json").unlink()
    report = build(conn, project).assemble().value
    assert not report.is_ready


# --- the skipped tier -------------------------------------------------------------------

def test_absent_node_skips_the_toolchain_without_blocking(conn, project, corpus):
    """The realistic case, and the unit's least obvious rule."""
    runner = FakeCommandRunner(available=set())
    report = build(conn, project, runner).assemble().value

    assert report.toolchain.status is CheckStatus.SKIPPED
    assert "not found on PATH" in report.toolchain.skipped_reason
    assert report.is_ready, "a missing toolchain must not block a structurally sound project"


def test_absent_node_names_the_lockfile_command(conn, project, corpus):
    runner = FakeCommandRunner(available=set())
    report = build(conn, project, runner).assemble().value
    assert not report.lockfile_present
    assert "npm install --package-lock-only" in report.lockfile_action


def test_skip_toolchain_configuration_produces_an_honest_skip(conn, project, corpus):
    report = build(conn, project, skip_toolchain=True).assemble().value
    assert report.toolchain.status is CheckStatus.SKIPPED
    assert report.is_ready


# --- toolchain failures do block ----------------------------------------------------------

def test_a_compilation_failure_blocks_readiness(conn, project, corpus):
    runner = FakeCommandRunner(
        outcomes={"npx tsc": failing(("npx", "tsc", "--noEmit"),
                                     "error TS2307: cannot find module")}
    )
    report = build(conn, project, runner).assemble().value
    assert report.toolchain.status is CheckStatus.FAILED
    assert not report.is_ready
    assert any("TS2307" in b["detail"] for b in report.blocking())


def test_a_timeout_is_a_failure_not_a_skip(conn, project, corpus):
    """A tool that was absent is skipped; one that ran and did not finish is failed.

    Folding the two together would tell the operator their machine lacks Node when
    it does not.
    """
    runner = FakeCommandRunner(
        outcomes={"npm ci": timing_out(("npm", "ci", "--ignore-scripts"))}
    )
    report = build(conn, project, runner).assemble().value
    assert report.toolchain.status is CheckStatus.FAILED
    assert not report.is_ready
    assert any("timed out" in b["detail"] for b in report.blocking())


def test_npm_ci_runs_with_ignore_scripts(conn, project, corpus):
    """npm runs lifecycle scripts from every transitive dependency by default, and
    verification must not be the path through which one executes."""
    runner = FakeCommandRunner()
    build(conn, project, runner).assemble()
    ci = next(c for c in runner.calls if c[0][:2] == ("npm", "ci"))
    assert "--ignore-scripts" in ci[0]


def test_toolchain_commands_stop_at_the_first_failure(conn, project, corpus):
    """tsc needs node_modules, which npm ci installs. Running on after it fails
    produces noise, not information."""
    runner = FakeCommandRunner(
        outcomes={"npm ci": failing(("npm", "ci", "--ignore-scripts"), "ELOCKVERIFY")}
    )
    build(conn, project, runner).assemble()
    assert not any(c[0][:2] == ("npx", "tsc") for c in runner.calls)


# --- reconciliation -------------------------------------------------------------------------

def test_a_spec_deleted_by_hand_blocks_readiness(conn, project, corpus):
    """The failure a database-to-manifest check alone would miss."""
    build(conn, project).assemble()
    (project / "tests" / "checkout.spec.ts").unlink()
    report = build(conn, project).verify().value
    assert report.reconciliation.status is CheckStatus.FAILED
    assert not report.is_ready
    assert any("not on disk" in b["name"] for b in report.blocking())


def test_a_test_on_disk_that_the_corpus_does_not_know_blocks_readiness(conn, project, corpus):
    """The failure a disk-to-manifest check alone would miss."""
    build(conn, project).assemble()
    (project / "tests" / "extra.spec.ts").write_text(
        "test('TC-CHECKOUT-09999 invented', async () => {});\n", encoding="utf-8"
    )
    report = build(conn, project).verify().value
    assert report.reconciliation.status is CheckStatus.FAILED
    assert any("not in the corpus" in b["name"] for b in report.blocking())


# --- idempotence -----------------------------------------------------------------------------

def test_two_handovers_produce_identical_manifest_bytes(conn, project, corpus):
    service = build(conn, project)
    service.assemble()
    first = (project / "handover-manifest.json").read_bytes()
    service.assemble()
    assert (project / "handover-manifest.json").read_bytes() == first


def test_verify_re_runs_every_check_without_caching(conn, project, corpus):
    """The operator re-runs after every fix, and the file most likely to have changed
    is the one they just fixed."""
    service = build(conn, project)
    service.assemble()
    (project / "tsconfig.json").unlink()
    assert not service.verify().value.is_ready
    (project / "tsconfig.json").write_text("{}\n", encoding="utf-8")
    assert service.verify().value.is_ready


def test_verify_does_not_rewrite_the_manifest(conn, project, corpus):
    service = build(conn, project)
    service.assemble()
    marker = (project / "handover-manifest.json")
    stamp = marker.stat().st_mtime_ns
    service.verify()
    assert marker.stat().st_mtime_ns == stamp


# --- the boundary --------------------------------------------------------------------------------

def test_the_service_cannot_push_branch_or_configure_ci(conn, project):
    """FR-HND-04 by absence: not a rule S7 follows, a capability it does not have."""
    service = build(conn, project)
    for forbidden in ("push", "branch", "commit", "git", "jenkins", "configure_ci"):
        assert not hasattr(service, forbidden), f"S7 must not expose {forbidden}"
