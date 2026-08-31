"""L9 PersonalDataDetector.

The most important tests here are the negative ones. A detector that rejects real
personal data is easy; a detector that does so without refusing the synthetic values
the team is told to use is the whole problem, because a check that fires on correct
input gets disabled.
"""

from __future__ import annotations

import pytest

from tto_testgen.domain.model import (
    EntityKind,
    LinkType,
    TestCase as Case,
    TestData as Data,
    TestStep as Step,
    TestType as Kind,
    TraceLink,
    encode_id,
)
from tto_testgen.domain.privacy import (
    PATTERN_NAMES,
    PrivacyFinding,
    luhn_valid,
    screen_case,
    screen_value,
)


def make_case(data: list[tuple[str, str]]) -> Case:
    return Case(
        id=encode_id(EntityKind.TEST_CASE, "checkout", 1),
        feature_id=1,
        coverage_item_id=encode_id(EntityKind.COVERAGE_ITEM, "checkout", 1),
        title="a case",
        test_type=Kind.BOUNDARY,
        steps=[Step(1, "Submit the form", "Accepted")],
        expected_result="ok",
        test_data=[Data(name, value, "valid", step_ordinal=1) for name, value in data],
        trace_links=[
            TraceLink("test_case", "x", "PAY-12", LinkType.DIRECT_STORY,
                      resolved_jira_key="PAY-12")
        ],
    )


# --- values that must be refused ---------------------------------------------

@pytest.mark.parametrize(
    "value,expected",
    [
        ("alice.brown@customer.co.uk", "email"),
        ("ALICE@ACME.COM", "email"),
        ("contact us at bob@supplier.io please", "email"),
        ("+44 7911 123456", "phone"),
        ("(020) 7946 1234", "phone"),
        ("AB123456C", "nino"),
        ("ab 12 34 56 c", "nino"),
        ("123-45-6789", "ssn"),
        ("4539578763621486", "card"),
        ("4539 5787 6362 1486", "card"),
    ],
)
def test_real_looking_personal_data_is_refused(value: str, expected: str) -> None:
    finding = screen_value("field", value)
    assert finding is not None, f"{value!r} was not detected"
    assert finding.pattern == expected


# --- values that must pass -----------------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        "user@example.com",
        "qa+baseline@example.org",
        "someone@example.net",
        "tester@checkout.test",
        "admin@corp.invalid",
        "555-0123",
        "+1 415 555 0142",
        "+44 7700 900123",
        "07700 900456",
        "01632 960123",
        "QQ123456C",
        "000-12-3456",
        "666-01-0001",
        "900-11-2222",
        "4242424242424242",
        "5555555555554444",
        "378282246310005",
        "4111 1111 1111 1111",
    ],
)
def test_documented_synthetic_values_pass(value: str) -> None:
    """PBT-U4-1 as examples. The property generalises this over the whole set."""
    assert screen_value("field", value) is None, f"{value!r} was wrongly refused"


@pytest.mark.parametrize(
    "value",
    [
        "ORD-1234567890123456",
        "batch 900000000000001",
        "correlation 1234567890123",
        "",
        "   ",
        "a normal sentence with no identifiers in it",
        "GBP 1234.56",
        "2026-08-30T12:00:00Z",
    ],
)
def test_ordinary_test_data_passes(value: str) -> None:
    assert screen_value("field", value) is None, f"{value!r} was wrongly refused"


def test_a_sixteen_digit_order_reference_is_not_a_card_number() -> None:
    """The Luhn check earns its place here.

    Without it every 16-digit string is a card number, the detector fires on
    order references and batch ids, and somebody turns it off - at which point
    U4-NFR-SEC-01 is delivering nothing.
    """
    assert not luhn_valid("1234567890123456")
    assert screen_value("order_ref", "1234567890123456") is None
    assert luhn_valid("4539578763621486")
    assert screen_value("card", "4539578763621486") is not None


def test_luhn_rejects_short_strings() -> None:
    assert not luhn_valid("42")
    assert not luhn_valid("")


# --- the report ---------------------------------------------------------------

def test_a_finding_names_the_field_the_pattern_and_the_remedy() -> None:
    finding = screen_value("step 2 data 'email'", "real.person@customer.com")
    assert finding is not None
    assert finding.field == "step 2 data 'email'"
    assert finding.pattern == "email"
    assert "example.com" in finding.permitted_form
    message = finding.message()
    assert "step 2 data 'email'" in message and "example.com" in message


def test_the_refused_value_never_appears_in_the_message() -> None:
    """A rejection that quotes the offending value copies it into the log.

    The finding says where and what shape, never what. Otherwise the control that
    keeps personal data out of the corpus puts it into the audit trail instead.
    """
    finding = screen_value("field", "real.person@customer.com")
    assert finding is not None
    assert "real.person" not in finding.message()
    assert "customer.com" not in finding.message()


# --- overlapping shapes --------------------------------------------------------

def test_an_allow_listed_ssn_is_not_re_reported_as_a_phone_number() -> None:
    """The phone pattern is the broadest, so it yields to recognised shapes.

    `000-12-3456` is a documented synthetic SSN. Reporting it as a phone number
    would refuse a value the team was told to use, and an allow-list that does not
    hold is worse than none.
    """
    assert screen_value("ssn", "000-12-3456") is None
    assert screen_value("nino", "QQ123456C") is None


def test_detection_order_is_stable() -> None:
    """A value matching two patterns reports the same one every time.

    An unstable report makes one batch fail differently on two runs, which is
    indistinguishable from a flaky check.
    """
    value = "contact alice@acme.com or 4539578763621486"
    first = screen_value("f", value)
    assert first is not None
    for _ in range(20):
        assert screen_value("f", value) == first


# --- configuration -------------------------------------------------------------

def test_a_pattern_can_be_disabled() -> None:
    without_phone = [p for p in PATTERN_NAMES if p != "phone"]
    assert screen_value("f", "+44 7911 123456") is not None
    assert screen_value("f", "+44 7911 123456", enabled_patterns=without_phone) is None


def test_an_extra_synthetic_domain_is_honoured() -> None:
    assert screen_value("f", "qa@tto-sandbox.internal") is not None
    assert (
        screen_value(
            "f", "qa@tto-sandbox.internal",
            extra_synthetic_domains=frozenset({"tto-sandbox.internal"}),
        )
        is None
    )


# --- whole cases ----------------------------------------------------------------

def test_screen_case_reports_every_offending_value_not_the_first() -> None:
    case = make_case(
        [
            ("email", "real@customer.com"),
            ("phone", "+44 7911 123456"),
            ("reference", "ORD-99887766"),
        ]
    )
    findings = screen_case(case)
    assert len(findings) == 2
    assert {f.pattern for f in findings} == {"email", "phone"}
    assert all(isinstance(f, PrivacyFinding) for f in findings)


def test_a_clean_case_yields_no_findings() -> None:
    case = make_case([("email", "user@example.com"), ("card", "4242424242424242")])
    assert screen_case(case) == []
