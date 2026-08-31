"""The 10 U4 properties.

Four of them belong to L9, and they carry the whole of U4-NFR-SEC-01's assurance.
Testing a detector by example tests the patterns the author was already thinking
about; the property is what catches the plus-tagged address and the spaced-out card
number that nobody wrote a case for.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from tto_testgen.adapters.view_renderer import (
    digest,
    render_markdown,
    render_yaml,
)
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
    luhn_valid,
    screen_value,
)
from tto_testgen.domain.privacy import _TEST_CARDS as TEST_CARDS

SETTINGS = settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)

#: For the converse properties, where a finding is the rare case by construction.
#: Filtering is inherent to "whenever X happens, Y holds" over random input; the
#: alternative would be to generate only inputs that trigger X, which is the
#: forward property and is tested separately.
RARE = settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)

# --- strategies ----------------------------------------------------------------

local_parts = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789.+-_", min_size=1, max_size=20
).filter(lambda s: not s.startswith(".") and not s.endswith("."))

reserved_domains = st.sampled_from(
    ["example.com", "example.org", "example.net", "checkout.test",
     "corp.invalid", "site.example", "host.localhost"]
)
real_domains = st.sampled_from(
    ["customer.co.uk", "acme.com", "supplier.io", "bank.de", "mail.example2.com"]
)

reserved_phones = st.sampled_from(
    ["555-0100", "555-0142", "+1 415 555 0123", "+44 7700 900123",
     "07700 900456", "01632 960123", "+44 1632 960999"]
)
test_cards = st.sampled_from(
    ["4242424242424242", "4111111111111111", "5555555555554444",
     "378282246310005", "6011111111111117", "3530111333300000"]
)
reserved_ssns = st.builds(
    lambda a, b, c: f"{a}-{b:02d}-{c:04d}",
    st.sampled_from(["000", "666", "900", "950", "999"]),
    st.integers(1, 99),
    st.integers(1, 9999),
)
reserved_ninos = st.builds(
    lambda p, n, s: f"{p}{n:06d}{s}",
    st.sampled_from(["BG", "GB", "NK", "KN", "TN", "NT", "ZZ"]),
    st.integers(0, 999999),
    st.sampled_from("ABCD"),
)

def _with_luhn(prefix: str) -> str:
    """Complete a partial card number with its Luhn check digit.

    Generating a *valid* card number is the only way to exercise the card path:
    filtering random digit strings for Luhn validity discards nine in ten, which
    Hypothesis rightly complains about and which distorts what it explores.
    """
    total, parity = 0, (len(prefix) + 1) % 2
    for index, char in enumerate(prefix):
        digit = int(char)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return prefix + str((10 - total % 10) % 10)


real_cards = st.builds(
    lambda lead, rest: _with_luhn(lead + rest),
    st.sampled_from("23456"),
    st.text(alphabet="0123456789", min_size=14, max_size=14),
)
real_phones = st.sampled_from(
    ["+44 7911 123456", "(020) 7946 1234", "+33 6 12 34 56 78",
     "0161 496 0123", "212-555-1234", "+1 212 867 5309"]
)
real_ssns = st.builds(
    lambda a, b, c: f"{a:03d}-{b:02d}-{c:04d}",
    st.integers(1, 665).filter(lambda n: n != 666),
    st.integers(1, 99),
    st.integers(1, 9999),
)
real_ninos = st.builds(
    lambda p, n, s: f"{p}{n:06d}{s}",
    st.sampled_from(["AB", "CE", "HJ", "PR", "WA", "MA"]),
    st.integers(0, 999999),
    st.sampled_from("ABCD"),
)

#: Values that must always be refused. Drawn from directly rather than filtered:
#: a finding is the precondition of these properties, not a rare accident.
refusable_values = st.one_of(
    st.builds(lambda l, d: f"{l}@{d}", local_parts, real_domains),
    real_phones,
    real_cards,
    real_ssns,
    real_ninos,
)

synthetic_values = st.one_of(
    st.builds(lambda l, d: f"{l}@{d}", local_parts, reserved_domains),
    reserved_phones,
    test_cards,
    reserved_ssns,
    reserved_ninos,
)

case_ids = st.builds(lambda n: encode_id(EntityKind.TEST_CASE, "checkout", n),
                     st.integers(1, 9999))
safe_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc")), min_size=1, max_size=40
).map(lambda s: s.strip()).filter(lambda s: len(s) > 0)


@st.composite
def cases(draw):
    step_count = draw(st.integers(1, 4))
    return Case(
        id=draw(case_ids),
        feature_id=1,
        coverage_item_id=encode_id(EntityKind.COVERAGE_ITEM, "checkout", 1),
        title=draw(safe_text),
        test_type=draw(st.sampled_from(list(Kind))),
        steps=[
            Step(i + 1, draw(safe_text), draw(safe_text)) for i in range(step_count)
        ],
        expected_result="ok",
        test_data=[Data(draw(safe_text), draw(safe_text), "valid", step_ordinal=1)],
        trace_links=[
            TraceLink("test_case", "x", "PAY-12", LinkType.DIRECT_STORY,
                      resolved_jira_key="PAY-12")
        ],
    )


# --- L9: the four screening properties -------------------------------------------

class TestPersonalDataScreening:
    @SETTINGS
    @given(value=synthetic_values)
    def test_pbt_u4_1_documented_synthetic_values_always_pass(self, value):
        """A documented synthetic value is never refused, for any pattern.

        The allow-list is what makes rejection workable. If it does not hold, the
        team is told to use values the system then refuses, and the check gets
        disabled - at which point U4-NFR-SEC-01 delivers nothing.
        """
        assert screen_value("field", value) is None

    @SETTINGS
    @given(local=local_parts, domain=real_domains)
    def test_pbt_u4_2_a_real_looking_address_is_always_refused(self, local, domain):
        """Including the plus-tagged and dotted forms nobody writes a case for."""
        finding = screen_value("field", f"{local}@{domain}")
        assert finding is not None
        assert finding.pattern == "email"

    @SETTINGS
    @given(field=safe_text, value=st.text(max_size=60))
    def test_pbt_u4_3_screening_is_pure(self, field, value):
        """The same value screens identically every time.

        An unstable verdict makes one batch fail differently on two runs, which is
        indistinguishable from a flaky check and destroys trust in the report.
        """
        first = screen_value(field, value)
        assert screen_value(field, value) == first
        assert screen_value(field, value) == first

    @SETTINGS
    @given(field=safe_text, value=refusable_values)
    def test_pbt_u4_4_a_finding_never_quotes_the_refused_value(self, field, value):
        """The control that keeps personal data out of the corpus must not put it
        into the audit trail instead."""
        finding = screen_value(field, value)
        assert finding is not None, f"{value!r} should have been refused"
        assert value.strip() not in finding.message()

    @SETTINGS
    @given(digits=real_cards)
    def test_a_luhn_valid_issuer_prefixed_number_is_refused_as_a_card(self, digits):
        assume(digits not in TEST_CARDS)
        assert luhn_valid(digits)
        finding = screen_value("field", digits)
        assert finding is not None and finding.pattern == "card"

    @RARE
    @given(digits=st.text(alphabet="0123456789", min_size=13, max_size=16))
    def test_a_card_verdict_always_passes_luhn_and_a_real_issuer_range(self, digits):
        """The converse. Luhn alone flags roughly one arbitrary digit string in
        ten; the issuer range is what stops a 15-digit batch id being called a
        card number."""
        finding = screen_value("field", digits)
        assume(finding is not None and finding.pattern == "card")
        assert luhn_valid(digits)
        assert digits[0] in "23456"

    @SETTINGS
    @given(value=st.text(max_size=60))
    def test_disabling_every_pattern_refuses_nothing(self, value):
        assert screen_value("field", value, enabled_patterns=[]) is None

    @SETTINGS
    @given(value=refusable_values)
    def test_a_finding_always_names_one_of_the_declared_patterns(self, value):
        finding = screen_value("field", value)
        assert finding is not None
        assert finding.pattern in PATTERN_NAMES
        assert finding.permitted_form


# --- L10: rendering ---------------------------------------------------------------

class TestViewRendering:
    @SETTINGS
    @given(batch=st.lists(cases(), min_size=1, max_size=6, unique_by=lambda c: c.id))
    def test_pbt_u4_5_rendering_is_byte_stable(self, batch):
        """Two renders of the same corpus produce identical bytes.

        Everything else about hand-edit detection rests on this. If it fails, every
        file looks edited on every run.
        """
        assert render_markdown("checkout", batch) == render_markdown("checkout", batch)
        assert render_yaml("checkout", batch) == render_yaml("checkout", batch)

    @SETTINGS
    @given(batch=st.lists(cases(), min_size=2, max_size=6, unique_by=lambda c: c.id))
    def test_pbt_u4_6_rendering_is_independent_of_input_order(self, batch):
        shuffled = list(reversed(batch))
        assert digest(render_markdown("checkout", batch)) == digest(
            render_markdown("checkout", shuffled)
        )
        assert digest(render_yaml("checkout", batch)) == digest(
            render_yaml("checkout", shuffled)
        )

    @SETTINGS
    @given(batch=st.lists(cases(), min_size=1, max_size=5, unique_by=lambda c: c.id))
    def test_pbt_u4_7_every_case_appears_in_the_view(self, batch):
        """A view that silently drops a case is worse than no view: the reviewer
        signs off on a corpus they did not see."""
        content = render_markdown("checkout", batch)
        for case in batch:
            assert case.id in content

    @SETTINGS
    @given(batch=st.lists(cases(), min_size=1, max_size=4, unique_by=lambda c: c.id))
    def test_pbt_u4_8_a_changed_corpus_changes_the_digest(self, batch):
        """Otherwise an emission would skip a file that genuinely needed rewriting."""
        extra = Case(
            id=encode_id(EntityKind.TEST_CASE, "checkout", 9999),
            feature_id=1,
            coverage_item_id=encode_id(EntityKind.COVERAGE_ITEM, "checkout", 1),
            title="an additional case",
            test_type=Kind.BOUNDARY,
            steps=[Step(1, "do a thing", "it happens")],
            expected_result="ok",
            trace_links=[
                TraceLink("test_case", "x", "PAY-12", LinkType.DIRECT_STORY,
                          resolved_jira_key="PAY-12")
            ],
        )
        assume(all(c.id != extra.id for c in batch))
        assert digest(render_markdown("checkout", batch)) != digest(
            render_markdown("checkout", batch + [extra])
        )

    @SETTINGS
    @given(batch=st.lists(cases(), min_size=1, max_size=4, unique_by=lambda c: c.id))
    def test_pbt_u4_9_the_yaml_view_has_one_case_entry_per_case(self, batch):
        content = render_yaml("checkout", batch)
        assert content.count("\n  - id: ") == len(batch)
        assert f"case_count: {len(batch)}" in content

    @SETTINGS
    @given(batch=st.lists(cases(), min_size=1, max_size=4, unique_by=lambda c: c.id))
    def test_pbt_u4_10_a_markdown_table_row_never_loses_a_cell(self, batch):
        """A pipe in a step must not split the cell it is in."""
        for line in render_markdown("checkout", batch).splitlines():
            if line.startswith("| ") and not line.startswith("|---"):
                assert line.replace("\\|", "").count("|") == line.count("|") - line.count("\\|")
