"""The 10 U5 properties plus the 3 on L11.

Six of these are statements about generated text, which is where the extension earns
its place: a fixed wait or an XPath reaching the output would come from a template
branch nobody exercised - precisely the branch a hand-written case does not cover,
because the person writing it is thinking about the path they just built.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from jinja2 import UndefinedError

from tto_testgen.adapters.playwright_emitter import PlaywrightEmitter, digest
from tto_testgen.adapters.templates import TemplateEnvironment, ts_literal, ts_tag
from tto_testgen.domain.locators import property_name, resolve
from tto_testgen.domain.secrets import scan_value

SETTINGS = settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)

FORBIDDEN_WAITS = ("waitForTimeout", "setTimeout(", "sleep(")

text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc")), min_size=1, max_size=40
).map(str.strip).filter(lambda s: len(s) > 0)
tags = st.lists(st.from_regex(r"\A[a-z][a-z0-9-]{0,12}\Z"), max_size=4, unique=True)


@st.composite
def cases(draw):
    seq = draw(st.integers(1, 9999))
    return {
        "id": f"TC-CHECKOUT-{seq:05d}",
        "title": draw(text),
        "tags": json.dumps(draw(tags)),
        "coverage_item_id": f"CI-CHECKOUT-{draw(st.integers(1, 99)):05d}",
        "preconditions": draw(st.one_of(st.just(""), text)),
        "steps": [
            {"ordinal": i + 1, "action": draw(text), "expected": draw(text)}
            for i in range(draw(st.integers(1, 3)))
        ],
        "trace_links": [{"resolved_jira_key": "PAY-12", "target_ref": "PAY-12"}],
    }


@st.composite
def elements(draw):
    return {
        "role": draw(st.one_of(st.none(), st.sampled_from(["button", "link", "textbox"]))),
        "accessible_name": draw(st.one_of(st.none(), text)),
        "label": draw(st.one_of(st.none(), text)),
        "placeholder": draw(st.one_of(st.none(), text)),
        "text": draw(st.one_of(st.none(), text)),
        "test_id": draw(st.one_of(st.none(), st.from_regex(r"\A[a-z][a-z0-9-]{0,10}\Z"))),
        "locator_chain": json.dumps(draw(st.lists(
            st.one_of(st.from_regex(r"\A\.[a-z][a-z0-9-]{0,10}\Z"),
                      st.from_regex(r"\A//div\[\d\]\Z")),
            max_size=2))),
        "is_verified": draw(st.booleans()),
        "is_fragile": draw(st.booleans()),
    }


@pytest.fixture(scope="module")
def emitter(tmp_path_factory):
    return PlaywrightEmitter(tmp_path_factory.mktemp("prop"), TemplateEnvironment())


# --- L11 ---------------------------------------------------------------------------

class TestTemplateEnvironmentProperties:
    @SETTINGS
    @given(value=st.text(max_size=80))
    def test_pbt_u5_a_ts_always_produces_a_parseable_js_literal(self, value):
        """The injection surface: agent text landing inside a TypeScript literal."""
        rendered = ts_literal(value)
        assert rendered.startswith('"') and rendered.endswith('"')
        # `json.loads` rejects trailing content, so a successful round-trip is
        # itself proof that the literal is exactly one complete string - nothing
        # escaped out of it and appended.
        assert json.loads(rendered) == value
        # And no bare quote survives in the interior. Scanned rather than counted:
        # counting escaped quotes miscounts `"\\"`, where the escaped backslash
        # precedes the closing quote.
        interior, index = rendered[1:-1], 0
        while index < len(interior):
            if interior[index] == "\\":
                index += 2
                continue
            assert interior[index] != '"', f"bare quote at {index} in {rendered!r}"
            index += 1

    def test_pbt_u5_b_an_undefined_variable_raises(self):
        env = TemplateEnvironment()
        with pytest.raises(UndefinedError):
            env.render("package.json.j2", project_name="only-one-of-four")

    @SETTINGS
    @given(value=st.text(min_size=1, max_size=20))
    def test_pbt_u5_c_tags_are_prefixed_exactly_once(self, value):
        assume(value.strip())
        rendered = json.loads(ts_tag(value))
        assert rendered.startswith("@")
        assert not rendered.startswith("@@") or value.strip().startswith("@@")


# --- rendering -------------------------------------------------------------------------

class TestRenderingProperties:
    @SETTINGS
    @given(batch=st.lists(cases(), min_size=1, max_size=4, unique_by=lambda c: c["id"]))
    def test_pbt_u5_1_rendering_is_byte_stable(self, batch, emitter):
        assert emitter.render_spec("checkout", "Checkout", batch) == emitter.render_spec(
            "checkout", "Checkout", batch
        )

    @SETTINGS
    @given(batch=st.lists(cases(), min_size=2, max_size=4, unique_by=lambda c: c["id"]))
    def test_pbt_u5_2_rendering_is_independent_of_input_order(self, batch, emitter):
        assert digest(emitter.render_spec("checkout", "C", batch)) == digest(
            emitter.render_spec("checkout", "C", list(reversed(batch)))
        )

    @SETTINGS
    @given(batch=st.lists(cases(), min_size=1, max_size=3, unique_by=lambda c: c["id"]))
    def test_pbt_u5_3_no_fixed_wait_is_ever_rendered(self, batch, emitter):
        content = emitter.render_spec("checkout", "Checkout", batch)
        content += emitter.render_spec("checkout", "Checkout", batch, api=True)
        for forbidden in FORBIDDEN_WAITS:
            assert forbidden not in content

    @SETTINGS
    @given(batch=st.lists(elements(), min_size=1, max_size=4))
    def test_pbt_u5_4_no_xpath_is_ever_rendered(self, batch, emitter):
        content = emitter.render_page_object({"screen_name": "checkout"}, batch)
        assert "//div" not in content
        assert "xpath=" not in content

    @SETTINGS
    @given(batch=st.lists(cases(), min_size=1, max_size=3, unique_by=lambda c: c["id"]))
    def test_pbt_u5_5_every_tests_tags_are_its_cases_tags(self, batch, emitter):
        content = emitter.render_spec("checkout", "Checkout", batch)
        for case in batch:
            for tag in json.loads(case["tags"]):
                assert f'"@{tag}"' in content

    @SETTINGS
    @given(batch=st.lists(cases(), min_size=1, max_size=3, unique_by=lambda c: c["id"]))
    def test_pbt_u5_6_every_test_names_its_case_id_and_jira_key(self, batch, emitter):
        content = emitter.render_spec("checkout", "Checkout", batch)
        for case in batch:
            assert case["id"] in content
        assert '"PAY-12"' in content

    @SETTINGS
    @given(batch=st.lists(cases(), min_size=1, max_size=3, unique_by=lambda c: c["id"]))
    def test_pbt_u5_9_no_generated_file_carries_a_credential_literal(self, batch, emitter):
        """The scaffold is the risk here: config and fixtures are where a literal
        would naturally be written."""
        content = emitter.render_spec("checkout", "Checkout", batch)
        content += "".join(c for _, c in emitter.render_scaffold())
        for line in content.splitlines():
            finding = scan_value("generated line", line)
            assert finding is None or finding.kind != "private-key", line

    @SETTINGS
    @given(batch=st.lists(cases(), min_size=1, max_size=3, unique_by=lambda c: c["id"]))
    def test_generated_code_contains_no_dynamic_evaluation(self, batch, emitter):
        """U5-NFR-SEC-04: case content is data, never a code fragment."""
        content = emitter.render_spec("checkout", "Checkout", batch)
        content += "".join(c for _, c in emitter.render_scaffold())
        for forbidden in ("eval(", "new Function(", "child_process", "execSync"):
            assert forbidden not in content


# --- the locator ladder -------------------------------------------------------------------

class TestLocatorProperties:
    @SETTINGS
    @given(element=elements())
    def test_pbt_u5_10_the_highest_available_rank_always_wins(self, element):
        got = resolve(element)
        assume(got is not None)
        if element["role"]:
            assert got.rank == 1
        elif element["label"]:
            assert got.rank == 2
        elif element["placeholder"] or element["text"]:
            assert got.rank == 3
        elif element["test_id"]:
            assert got.rank == 4
        else:
            assert got.rank == 5

    @SETTINGS
    @given(element=elements())
    def test_pbt_u5_8_an_unverified_locator_always_carries_its_annotation(self, element):
        got = resolve(element)
        assume(got is not None)
        if not element["is_verified"]:
            assert any("UNVERIFIED" in note for note in got.annotations)
            assert got.is_at_risk

    @SETTINGS
    @given(element=elements())
    def test_a_resolved_expression_is_always_a_single_line(self, element):
        """A newline in an accessible name must not break the page object."""
        got = resolve(element)
        assume(got is not None)
        assert "\n" not in got.expression

    @SETTINGS
    @given(element=elements())
    def test_a_property_name_is_always_a_valid_js_identifier(self, element):
        name = property_name(element)
        assert name
        assert name[0].isalpha() or name[0] == "_"
        assert all(c.isalnum() or c == "_" for c in name)

    @SETTINGS
    @given(element=elements())
    def test_pbt_u5_7_resolution_is_pure(self, element):
        first = resolve(element)
        assert resolve(element) == first
