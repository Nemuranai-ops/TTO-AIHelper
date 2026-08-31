"""X1 ResultAndErrors. Requirements: NFR-SEC-07, NFR-SEC-08, NFR-USA-03."""

from pathlib import Path

import pytest

from tto_testgen.platform.result import (
    REMEDIATION,
    ErrorCode,
    Err,
    Ok,
    err,
    is_rejection,
    ok,
    sanitise,
)


class TestErrorTaxonomy:
    def test_every_code_belongs_to_exactly_one_family(self):
        for code in ErrorCode:
            assert code.value.startswith(("REJECTED_", "FAILED_")), code

    def test_rejection_flag_matches_prefix(self):
        for code in ErrorCode:
            assert code.is_rejection == code.value.startswith("REJECTED_")

    def test_every_code_has_remediation(self):
        # An error the agent cannot act on is an error it will retry blindly.
        missing = [c for c in ErrorCode if not REMEDIATION.get(c)]
        assert missing == []

    def test_taxonomy_has_the_designed_size(self):
        """Pinned so a code is added deliberately, not absent-mindedly.

        U4 added REJECTED_PERSONAL_DATA (11th rejection). Reusing an existing code
        was the alternative and it would have misdescribed the fault: the agent's
        remediation for a personal-data rejection is to substitute a synthetic
        value, which no other code's guidance says.
        """
        rejected = [c for c in ErrorCode if c.is_rejection]
        failed = [c for c in ErrorCode if not c.is_rejection]
        assert len(rejected) == 11
        assert len(failed) == 6


class TestResultConstruction:
    def test_ok_carries_value(self):
        assert ok(42).value == 42
        assert ok(42).ok is True

    def test_err_carries_code_and_remediation(self):
        e = err(ErrorCode.REJECTED_NO_STEPS, "no steps")
        assert e.ok is False
        assert e.code is ErrorCode.REJECTED_NO_STEPS
        assert e.remediation == REMEDIATION[ErrorCode.REJECTED_NO_STEPS]

    def test_explicit_remediation_overrides_default(self):
        e = err(ErrorCode.FAILED_INTERNAL, "boom", remediation="do the thing")
        assert e.remediation == "do the thing"

    def test_context_is_preserved(self):
        e = err(ErrorCode.REJECTED_DUPLICATE, "dup", existing_id="TC-CHECKOUT-00007")
        assert e.context["existing_id"] == "TC-CHECKOUT-00007"

    def test_is_rejection_distinguishes_families(self):
        assert is_rejection(err(ErrorCode.REJECTED_NO_JIRA_KEY, "x")) is True
        assert is_rejection(err(ErrorCode.FAILED_DB_UNAVAILABLE, "x")) is False
        assert is_rejection(ok("fine")) is False


class TestSanitisation:
    def test_strips_absolute_paths_outside_workspace(self):
        out = sanitise("failed reading /etc/passwd during load")
        assert "/etc/passwd" not in out
        assert "<path>" in out

    def test_keeps_workspace_relative_paths_actionable(self):
        # "resources.md not found" is something the agent can act on; masking it
        # would turn a fixable problem into an opaque one.
        root = Path("/work/project")
        out = sanitise("could not open /work/project/resources.md", root)
        assert "resources.md" in out

    def test_redacts_secret_shaped_text(self):
        assert "abc123" not in sanitise("auth failed with token=abc123")
        assert "xyz789" not in sanitise("header Bearer xyz789 rejected")

    def test_strips_stack_trace_lines(self):
        message = 'boom\n  File "/deep/internal/module.py", line 42, in handler\n  raise'
        out = sanitise(message)
        assert "module.py" not in out
        assert "line 42" not in out

    def test_err_sanitises_on_construction(self):
        e = err(ErrorCode.FAILED_INTERNAL, "crash with password=hunter2")
        assert "hunter2" not in e.message

    @pytest.mark.parametrize(
        "message",
        ["plain failure", "case TC-CHECKOUT-00001 has no steps", ""],
    )
    def test_leaves_benign_messages_intact(self, message):
        assert sanitise(message) == " ".join(message.split())
