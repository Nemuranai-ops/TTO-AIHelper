"""L9 PersonalDataDetector - what may not appear in test data.

The agent reads real Jira stories. A story citing a customer's actual email address
is exactly how real personal data reaches a test corpus, and that corpus is pushed
to a different Bitbucket repository - which is where a confidentiality problem
becomes a disclosure (NFR-SEC-11, U4-NFR-SEC-01).

Pure by construction: a value in, a finding or None out. No I/O, no configuration
lookup, no logging. That keeps it inside the `domain-is-pure` import contract and
makes the four L9 properties testable without a database, which matters because
those properties are the whole of U4-NFR-SEC-01's assurance.

Rejection rather than a warning was chosen deliberately (U4 NFR Requirements Q3):
the false-positive cost is one substitution, and the false-negative cost is a real
person's data in a repository the test team pushes to CI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps the module import-light
    from tto_testgen.domain.model import TestCase


@dataclass(frozen=True, slots=True)
class PrivacyFinding:
    """Why a value was refused, and what an acceptable one looks like.

    `permitted_form` is what makes the rejection actionable. Without it the agent
    knows only that its value was wrong, and its next attempt is a guess - which
    over 6,000 cases is a lot of guessing.
    """

    field: str
    pattern: str
    permitted_form: str

    def message(self) -> str:
        return (
            f"{self.field} matches a {self.pattern} pattern. "
            f"Use a documented synthetic value instead: {self.permitted_form}."
        )


# --- the pattern set ---------------------------------------------------------
# Deliberately broad. A pattern that matches too little is a pattern that lets real
# data through, and the allow-list below is what keeps the breadth workable.

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
# Three shapes, not one open-ended digit run. A pattern that accepts any 9-15 digit
# string matches order references, batch ids, correlation tokens and ISO timestamps
# - all ordinary test data. Requiring a phone-shaped prefix or NANP grouping keeps
# detection while removing the false positives that would get the check disabled.
_PHONE_SHAPES = (
    # International: must carry a country-code plus.
    re.compile(r"(?<![\d+])(\+\d[\d\s().\-]{6,16}\d)(?!\d)"),
    # National trunk prefix, optionally parenthesised: (020) 7946 1234, 07700 900456.
    re.compile(r"(?<![\d+])(\(?0\d[\d\s().\-]{6,12}\d)(?!\d)"),
    # NANP grouped: 415-555-0142, (415) 555 0142.
    re.compile(r"(?<![\d+])(\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4})(?!\d)"),
)
_NINO = re.compile(r"(?<![A-Za-z0-9])[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D](?![A-Za-z0-9])")
_SSN = re.compile(r"(?<!\d)(\d{3})-(\d{2})-(\d{4})(?!\d)")
_DIGITS = re.compile(r"(?<!\d)(?:\d[ \-]?){12,18}\d(?!\d)")

# RFC 2606 and RFC 6761 reserve these precisely so examples cannot collide with a
# real domain. Anything outside them may belong to someone.
_RESERVED_DOMAINS = frozenset({"example.com", "example.org", "example.net"})
_RESERVED_TLDS = (".test", ".example", ".invalid", ".localhost")

# Reserved for fiction by the NANP, and the equivalent UK Ofcom drama range.
_RESERVED_PHONE = (
    re.compile(r"^\+?1?[\s\-.()]*\d{3}[\s\-.()]*555[\s\-.()]*01\d{2}$"),
    re.compile(r"^\+?44[\s\-.()]*7700[\s\-.()]*900\d{3}$"),
    re.compile(r"^0?7700[\s\-.()]*900\d{3}$"),
    re.compile(r"^\+?44[\s\-.()]*1632[\s\-.()]*960\d{3}$"),
    re.compile(r"^0?1632[\s\-.()]*960\d{3}$"),
)

# Never issued by the SSA: area 000, 666, and 900-999.
_SSN_NEVER_ISSUED_AREAS = frozenset({"000", "666"} | {str(n) for n in range(900, 1000)})
# Never issued by HMRC as a National Insurance prefix.
_NINO_NEVER_ISSUED = frozenset({"BG", "GB", "NK", "KN", "TN", "NT", "ZZ"})

# Published network test numbers. Every one is documented by the scheme itself as
# non-transactable, which is what makes them safe to commit.
_TEST_CARDS = frozenset({
    "4242424242424242", "4111111111111111", "4012888888881881", "4000056655665556",
    "5555555555554444", "5200828282828210", "5105105105105100", "2223003122003222",
    "378282246310005", "371449635398431", "6011111111111117", "6011000990139424",
    "3530111333300000", "3566002020360505", "6200000000000005",
})

# Major industry identifiers actually used by payment schemes: 2 and 5 Mastercard,
# 3 Amex/Diners/JCB, 4 Visa, 6 Discover/UnionPay. 0, 1, 7, 8 and 9 are reserved for
# other industries and never appear on a payment card.
_CARD_LEADING_DIGITS = frozenset("23456")

PATTERN_NAMES = ("email", "phone", "nino", "ssn", "card")

_PERMITTED = {
    "email": "an RFC 2606 reserved domain, e.g. user@example.com",
    "phone": "a reserved drama range, e.g. 555-0123 or +44 7700 900123",
    "nino": "a never-issued prefix, e.g. QQ123456C",
    "ssn": "a never-issued area, e.g. 000-12-3456",
    "card": "a published network test number, e.g. 4242424242424242",
}


def _digits(value: str) -> str:
    return "".join(c for c in value if c.isdigit())


def luhn_valid(value: str) -> bool:
    """The Luhn check digit, as used by every major card scheme.

    Part of *detection*, not a refinement of it. A 16-digit order reference, a batch
    id and a correlation token are all plausible test data and none are card
    numbers; a detector that flagged every 16-digit string would fire constantly on
    legitimate values, and a check that fires constantly gets turned off. A real
    card number passes Luhn by construction, so requiring it costs no detection.
    """
    digits = _digits(value)
    if len(digits) < 13:
        return False
    total, parity = 0, len(digits) % 2
    for index, char in enumerate(digits):
        digit = int(char)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _email_is_synthetic(domain: str, extra_domains: frozenset[str]) -> bool:
    lowered = domain.lower().rstrip(".")
    if lowered in _RESERVED_DOMAINS or lowered in extra_domains:
        return True
    return any(lowered.endswith(tld) for tld in _RESERVED_TLDS)


def _phone_is_synthetic(value: str) -> bool:
    compact = value.strip()
    return any(pattern.match(compact) for pattern in _RESERVED_PHONE)


def screen_value(
    field: str,
    value: str,
    *,
    enabled_patterns: Iterable[str] = PATTERN_NAMES,
    extra_synthetic_domains: frozenset[str] = frozenset(),
) -> PrivacyFinding | None:
    """Return a finding when `value` looks like real personal data, else None.

    Checked in a fixed order so a value matching two patterns reports the same one
    every time. An unstable report would make the same batch fail differently on
    two runs, which is indistinguishable from a flaky check.
    """
    if not value or not value.strip():
        return None
    enabled = frozenset(enabled_patterns)
    text = value.strip()

    if "email" in enabled:
        match = _EMAIL.search(text)
        if match and not _email_is_synthetic(match.group(1), extra_synthetic_domains):
            return PrivacyFinding(field, "email", _PERMITTED["email"])

    nino_match = _NINO.search(text.upper())
    if "nino" in enabled and nino_match:
        if nino_match.group(0).replace(" ", "")[:2] not in _NINO_NEVER_ISSUED:
            return PrivacyFinding(field, "nino", _PERMITTED["nino"])

    ssn_match = _SSN.search(text)
    if "ssn" in enabled and ssn_match:
        if ssn_match.group(1) not in _SSN_NEVER_ISSUED_AREAS:
            return PrivacyFinding(field, "ssn", _PERMITTED["ssn"])

    if "card" in enabled:
        for match in _DIGITS.finditer(text):
            candidate = _digits(match.group(0))
            if candidate in _TEST_CARDS:
                continue
            # Luhn alone is not enough: roughly one in ten arbitrary digit strings
            # passes it, and a 15-digit batch id that happens to is not a card
            # number. Every payment scheme issues from major industry identifier
            # 2-6, so requiring one costs no detection and removes the whole class
            # of false positive.
            if candidate[:1] in _CARD_LEADING_DIGITS and luhn_valid(candidate):
                return PrivacyFinding(field, "card", _PERMITTED["card"])

    # The phone pattern is the broadest of the five, so it runs last and yields to
    # every shape already recognised as something else. `000-12-3456` is an
    # allow-listed SSN; without this it would come back as a phone number, and a
    # documented synthetic value that is refused anyway teaches the operator that
    # the allow-list does not work.
    if "phone" in enabled and ssn_match is None and nino_match is None:
        match = next(
            (m for m in (shape.search(text) for shape in _PHONE_SHAPES) if m), None
        )
        if match and not _phone_is_synthetic(match.group(1)):
            # A long digit string that failed Luhn is not a phone number either.
            # Without the length bound the two patterns overlap and the report names
            # whichever check happens to run first.
            if len(_digits(match.group(1))) <= 15:
                return PrivacyFinding(field, "phone", _PERMITTED["phone"])

    return None


def screen_case(
    case: "TestCase",
    *,
    enabled_patterns: Iterable[str] = PATTERN_NAMES,
    extra_synthetic_domains: frozenset[str] = frozenset(),
) -> list[PrivacyFinding]:
    """Every finding in a case, not the first.

    The same reasoning as the batch validator: an agent that fixes one value and
    resubmits, four times over, has spent four model round-trips on one correction
    pass. Every offending value is named at once.
    """
    findings: list[PrivacyFinding] = []
    for datum in case.test_data:
        finding = screen_value(
            f"step {datum.step_ordinal} data '{datum.field_name}'",
            datum.value,
            enabled_patterns=enabled_patterns,
            extra_synthetic_domains=extra_synthetic_domains,
        )
        if finding is not None:
            findings.append(finding)
    return findings
