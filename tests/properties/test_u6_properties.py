"""The 9 U6 properties.

PBT-U6-1 and -2 are the pair that pins BR-U6-2.4 — the rule that a skipped tier does
not block. It is the unit's least obvious rule and the one most likely to be
"corrected" by a later change being careful.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tto_testgen.adapters.structural_verifier import Check
from tto_testgen.ports.commands import CommandResult
from tto_testgen.services.handover import (
    LOCKFILE_COMMAND,
    TOOLCHAIN_COMMANDS,
    CheckStatus,
    HandoverReport,
    TierResult,
    _render_manifest,
)

SETTINGS = settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)

statuses = st.sampled_from(list(CheckStatus))


def tier(name: str, status: CheckStatus, failures: int = 0) -> TierResult:
    return TierResult(
        name=name,
        status=status,
        checks=[
            {"name": f"{name} check {i}", "passed": False, "location": f"file{i}.ts",
             "detail": "broken"}
            for i in range(failures)
        ],
    )


def report(structural, reconciliation, toolchain) -> HandoverReport:
    return HandoverReport(
        project_root="/p",
        structural=tier("structural", structural, 0 if structural is CheckStatus.PASSED else 1),
        reconciliation=tier("reconciliation", reconciliation,
                            0 if reconciliation is CheckStatus.PASSED else 1),
        toolchain=tier("toolchain", toolchain,
                       0 if toolchain is not CheckStatus.FAILED else 1),
    )


# --- readiness ---------------------------------------------------------------------

class TestReadiness:
    @SETTINGS
    @given(structural=statuses, reconciliation=statuses)
    def test_pbt_u6_1_a_skipped_toolchain_never_blocks_on_its_own(
        self, structural, reconciliation
    ):
        """A missing compiler is a fact about the machine, not a defect in the
        project. Blocking on it would mean the system can never declare a handover
        ready in the environment it was built for."""
        skipped = report(structural, reconciliation, CheckStatus.SKIPPED)
        passed = report(structural, reconciliation, CheckStatus.PASSED)
        assert skipped.is_ready == passed.is_ready

    @SETTINGS
    @given(structural=statuses, reconciliation=statuses)
    def test_pbt_u6_2_a_failed_toolchain_always_blocks(self, structural, reconciliation):
        assert not report(structural, reconciliation, CheckStatus.FAILED).is_ready

    @SETTINGS
    @given(toolchain=statuses, reconciliation=statuses)
    def test_a_failed_structural_tier_always_blocks(self, toolchain, reconciliation):
        assert not report(CheckStatus.FAILED, reconciliation, toolchain).is_ready

    @SETTINGS
    @given(toolchain=statuses, structural=statuses)
    def test_failed_reconciliation_always_blocks(self, toolchain, structural):
        assert not report(structural, CheckStatus.FAILED, toolchain).is_ready

    @SETTINGS
    @given(structural=statuses, reconciliation=statuses, toolchain=statuses)
    def test_readiness_is_pure(self, structural, reconciliation, toolchain):
        subject = report(structural, reconciliation, toolchain)
        assert subject.is_ready == subject.is_ready

    @SETTINGS
    @given(structural=statuses, reconciliation=statuses, toolchain=statuses)
    def test_pbt_u6_6_every_blocking_finding_names_a_file(
        self, structural, reconciliation, toolchain
    ):
        """A report saying 'structural check failed' without saying which file sends
        the engineer looking, which is the work U6 was supposed to save."""
        for finding in report(structural, reconciliation, toolchain).blocking():
            assert finding["location"], finding

    @SETTINGS
    @given(structural=statuses, reconciliation=statuses, toolchain=statuses)
    def test_a_ready_report_has_no_blocking_findings(
        self, structural, reconciliation, toolchain
    ):
        subject = report(structural, reconciliation, toolchain)
        if subject.is_ready:
            assert subject.blocking() == []


# --- the manifest ---------------------------------------------------------------------

entries = st.lists(
    st.fixed_dictionaries({
        "test_id": st.from_regex(r"\AAT-CHECKOUT-\d{5}\Z"),
        "case_id": st.from_regex(r"\ATC-CHECKOUT-\d{5}\Z"),
        "test_name": st.text(min_size=1, max_size=20),
        "spec_path": st.just("tests/checkout.spec.ts"),
        "jira_key": st.just("PAY-12"),
        "tags": st.lists(st.from_regex(r"\A[a-z]{2,8}\Z"), max_size=3),
        "is_at_risk": st.booleans(),
        "at_risk_reason": st.just(""),
    }),
    max_size=5,
    unique_by=lambda e: e["test_id"],
)


class TestManifest:
    @SETTINGS
    @given(rows=entries)
    def test_pbt_u6_4_the_manifest_is_byte_stable(self, rows):
        manifest = {"entries": rows, "totals": {"automated": len(rows)},
                    "at_risk_count": 0}
        assert _render_manifest(manifest) == _render_manifest(manifest)

    @SETTINGS
    @given(rows=entries)
    def test_pbt_u6_5_no_absolute_path_reaches_the_manifest(self, rows):
        manifest = {"entries": rows, "totals": {"automated": len(rows)},
                    "at_risk_count": 0}
        rendered = _render_manifest(manifest)
        assert "/Users/" not in rendered and "/private/" not in rendered

    @SETTINGS
    @given(rows=entries)
    def test_every_entry_appears_in_the_rendered_manifest(self, rows):
        manifest = {"entries": rows, "totals": {}, "at_risk_count": 0}
        rendered = _render_manifest(manifest)
        for row in rows:
            assert row["test_id"] in rendered


# --- subprocess containment ------------------------------------------------------------

class TestCommandContainment:
    def test_pbt_u6_7_every_argv_is_a_tuple_of_literals(self):
        """No project value is interpolated into any argv, so nothing agent-supplied
        can become a flag."""
        for _, argv in TOOLCHAIN_COMMANDS:
            assert isinstance(argv, tuple)
            assert all(isinstance(a, str) for a in argv)
            assert all("{" not in a and "%" not in a and "$" not in a for a in argv)
        assert all(isinstance(a, str) for a in LOCKFILE_COMMAND)

    def test_no_toolchain_command_uses_a_shell_construct(self):
        for _, argv in TOOLCHAIN_COMMANDS:
            joined = " ".join(argv)
            for metacharacter in ("&&", "||", ";", "|", ">", "<", "`"):
                assert metacharacter not in joined

    @SETTINGS
    @given(
        code=st.one_of(st.none(), st.integers(-8, 255)),
        timed_out=st.booleans(),
    )
    def test_pbt_u6_8_success_requires_a_zero_exit_and_no_timeout(self, code, timed_out):
        result = CommandResult(argv=("x",), exit_code=code, timed_out=timed_out)
        assert result.succeeded == (code == 0 and not timed_out)
