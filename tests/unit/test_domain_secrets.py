"""L13 SecretScanner.

As with L9, the negative tests carry the weight. A scanner that fires on UUIDs and
base64 fixtures is a scanner somebody turns off - U4 already paid that lesson when a
Luhn-only card check flagged batch ids.
"""

from __future__ import annotations

import pytest

from tto_testgen.domain.secrets import KINDS, scan_case, scan_value


# --- values that must be refused -------------------------------------------------

@pytest.mark.parametrize(
    "field,value,kind",
    [
        ("password", "hunter2", "credential-field"),
        ("api_key", "abc123", "credential-field"),
        ("step 2 data 'authorization'", "anything", "credential-field"),
        ("Client_Secret", "x", "credential-field"),
        ("header", "Bearer aGVsbG90aGVyZXRoaXNpc2Fsb25ndG9rZW4", "token-shape"),
        ("body", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVP", "token-shape"),
        ("key", "-----BEGIN RSA PRIVATE KEY-----", "private-key"),
        ("dsn", "postgres://user:pa55w0rd@db.internal:5432/app", "connection-string"),
        ("url", "https://checkout.acme-internal.com/api", "environment-url"),
        ("endpoint", "http://staging.acme.co.uk:8080/orders", "environment-url"),
    ],
)
def test_secrets_and_environment_values_are_refused(field, value, kind):
    finding = scan_value(field, value)
    assert finding is not None, f"{field}={value!r} was not detected"
    assert finding.kind == kind


# --- values that must pass ---------------------------------------------------------

@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", "5"),
        ("order_ref", "ORD-99887766"),
        ("correlation_id", "550e8400-e29b-41d4-a716-446655440000"),
        ("digest", "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"),
        ("payload", "eyJhIjoxfQ=="),
        ("email", "user@example.com"),
        ("url", "http://localhost:3000/checkout"),
        ("url", "https://example.com/orders"),
        ("url", "https://shop.test/basket"),
        ("note", "the user enters their password on this screen"),
        ("description", "Bearer tokens are covered by a separate case"),
        ("amount", "1234.56"),
        ("field", ""),
        ("field", "   "),
    ],
)
def test_ordinary_test_data_passes(field, value):
    assert scan_value(field, value) is None, f"{field}={value!r} was wrongly refused"


def test_a_uuid_is_not_a_token():
    """The exact failure an entropy threshold would produce.

    UUIDs, hashes and base64 fixtures are high-entropy and entirely ordinary. A
    control that fires on them is a control somebody turns off.
    """
    assert scan_value("id", "550e8400-e29b-41d4-a716-446655440000") is None
    assert scan_value("hash", "a" * 64) is None


# --- the report ---------------------------------------------------------------------

def test_a_finding_never_quotes_the_secret():
    """The refusal keeps the credential out of the log as well as out of the repo."""
    finding = scan_value("password", "hunter2-super-secret")
    assert finding is not None
    assert "hunter2" not in finding.message()
    assert "password" in finding.message()
    assert "process.env" in finding.message()


def test_a_finding_always_names_a_declared_kind():
    finding = scan_value("token", "x")
    assert finding.kind in KINDS
    assert finding.remedy


def test_detection_order_is_stable():
    value = "postgres://user:pw@db.internal/app and Bearer aGVsbG90aGVyZXRoaXNpc2E"
    first = scan_value("dsn_field", value)
    for _ in range(20):
        assert scan_value("dsn_field", value) == first


# --- configuration ---------------------------------------------------------------------

def test_an_extra_credential_field_name_is_honoured():
    assert scan_value("cardholder_pin", "1234") is None
    assert scan_value(
        "cardholder_pin", "1234", extra_credential_fields=["cardholder_pin"]
    ) is not None


# --- whole cases --------------------------------------------------------------------------

class _Datum:
    def __init__(self, field_name, value, step_ordinal=1):
        self.field_name, self.value, self.step_ordinal = field_name, value, step_ordinal


class _Step:
    def __init__(self, ordinal, action, expected):
        self.ordinal, self.action, self.expected = ordinal, action, expected


class _Case:
    def __init__(self, data=(), steps=(), preconditions=""):
        self.test_data, self.steps, self.preconditions = list(data), list(steps), preconditions


def test_scan_case_reports_every_offending_value():
    case = _Case(
        data=[_Datum("password", "hunter2"), _Datum("quantity", "5")],
        steps=[_Step(1, "Open https://staging.acme.co.uk", "The page loads")],
    )
    findings = scan_case(case)
    assert {f.kind for f in findings} == {"credential-field", "environment-url"}


def test_prose_describing_a_password_is_not_a_secret():
    """Field-name signals do not apply to prose.

    A step reading "enter the password" is a description of what the tester does,
    not a credential. Applying the field-name rule to step text would refuse most
    authentication cases in the corpus.
    """
    case = _Case(steps=[_Step(1, "Enter the password and submit", "Signed in")])
    assert scan_case(case) == []


def test_a_clean_case_yields_no_findings():
    case = _Case(
        data=[_Datum("quantity", "5")],
        steps=[_Step(1, "Open the basket", "The basket is shown")],
    )
    assert scan_case(case) == []
