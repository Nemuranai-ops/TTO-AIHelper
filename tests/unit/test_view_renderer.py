"""L10 ViewRenderer.

Byte-stability is the load-bearing property. Every other guarantee here depends on
it: if two renders of unchanged content differ, every file looks hand-edited on
every run and the report that protects the operator's work becomes noise.
"""

from __future__ import annotations

import pytest

from tests.fakes import FakeEmittedViewRepository
from tto_testgen.adapters.view_renderer import (
    BANNER,
    ViewManifest,
    ViewRenderer,
    digest,
    render_markdown,
    render_yaml,
)
from tto_testgen.domain.model import (
    AutomatabilityClass,
    EntityKind,
    LinkType,
    TestCase as Case,
    TestData as Data,
    TestStep as Step,
    TestType as Kind,
    TraceLink,
    encode_id,
)


def make_case(seq: int = 1, *, title: str = "Reject an empty basket") -> Case:
    return Case(
        id=encode_id(EntityKind.TEST_CASE, "checkout", seq),
        feature_id=1,
        coverage_item_id=encode_id(EntityKind.COVERAGE_ITEM, "checkout", 1),
        title=title,
        test_type=Kind.BOUNDARY,
        priority="high",
        preconditions="A signed-in customer",
        steps=[
            Step(1, "Open the basket", "The basket page is shown"),
            Step(2, "Submit with no items", "An empty-basket message is shown"),
        ],
        expected_result="An empty-basket message is shown",
        test_data=[Data("quantity", "0", "boundary-low", step_ordinal=2)],
        automatability=AutomatabilityClass.AUTOMATABLE,
        tags=["checkout", "boundary"],
        trace_links=[
            TraceLink("test_case", "x", "PAY-12", LinkType.DIRECT_STORY,
                      resolved_jira_key="PAY-12")
        ],
    )


@pytest.fixture()
def renderer(tmp_path):
    return ViewRenderer(tmp_path / "generated" / "testcases")


# --- byte stability -----------------------------------------------------------

def test_two_renders_of_the_same_cases_are_byte_identical() -> None:
    cases = [make_case(1), make_case(2, title="Accept a single item")]
    assert render_markdown("checkout", cases) == render_markdown("checkout", cases)
    assert render_yaml("checkout", cases) == render_yaml("checkout", cases)


def test_render_order_does_not_depend_on_input_order() -> None:
    """Sorted by identifier, which is stable; insertion order is not.

    Two runs producing the same corpus by different routes must render the same
    bytes, or every one of them looks like an edit.
    """
    a, b = make_case(1), make_case(2, title="Accept a single item")
    assert render_markdown("checkout", [a, b]) == render_markdown("checkout", [b, a])
    assert render_yaml("checkout", [a, b]) == render_yaml("checkout", [b, a])


def test_no_timestamp_run_id_or_absolute_path_appears_in_a_view() -> None:
    """The three exclusions U4-NFR-MNT-01 depends on."""
    content = render_markdown("checkout", [make_case()]) + render_yaml(
        "checkout", [make_case()]
    )
    assert "20" + "26-" not in content  # no ISO date
    assert "run_id" not in content
    assert "/Users/" not in content and "/tmp/" not in content


def test_every_view_states_that_it_is_generated() -> None:
    md = render_markdown("checkout", [make_case()])
    yaml_text = render_yaml("checkout", [make_case()])
    assert "system of record" in md and "system of record" in yaml_text
    assert BANNER in md


def test_the_banner_is_inside_the_hashed_content() -> None:
    """Removing it is itself a hand-edit, and is reported rather than accepted."""
    with_banner = render_markdown("checkout", [make_case()])
    without = with_banner.replace(BANNER, "")
    assert digest(with_banner) != digest(without)


# --- content -------------------------------------------------------------------

def test_the_markdown_view_carries_steps_data_and_traces() -> None:
    content = render_markdown("checkout", [make_case()])
    assert "Open the basket" in content
    assert "boundary-low" in content
    assert "PAY-12" in content
    assert "Reject an empty basket" in content


def test_a_pipe_in_a_step_does_not_break_the_table() -> None:
    case = make_case()
    case.steps[0] = Step(1, "Enter a|b", "Accepted")
    row = [l for l in render_markdown("checkout", [case]).splitlines() if "Enter a" in l][0]
    assert "Enter a\\|b" in row  # the pipe is escaped, not dropped
    # Four cell delimiters once the escaped pipe is removed - the table still parses.
    assert row.replace("\\|", "").count("|") == 4


def test_the_yaml_view_escapes_quotes_and_newlines() -> None:
    case = make_case(title='He said "no"\nthen left')
    content = render_yaml("checkout", [case])
    assert '\\"no\\"' in content
    assert "\\n" in content
    assert len([l for l in content.splitlines() if l.startswith("    title:")]) == 1


# --- the three outcomes ---------------------------------------------------------

def test_a_first_emission_writes_both_files(renderer) -> None:
    views = FakeEmittedViewRepository()
    manifest = renderer.emit("checkout", [make_case()], views)
    assert len(manifest.written) == 2
    assert manifest.unchanged == [] and manifest.hand_edited == []
    assert all(p.endswith((".md", ".yaml")) for p in manifest.written)


def test_a_re_emission_of_unchanged_content_writes_nothing(renderer) -> None:
    """`unchanged` is not folded into `written`.

    A re-emission that writes nothing is exactly right and indistinguishable from
    a broken one unless the report says so - and U4-NFR-PRF-06 is only checkable
    because it does.
    """
    views = FakeEmittedViewRepository()
    cases = [make_case()]
    renderer.emit("checkout", cases, views)
    manifest = renderer.emit("checkout", cases, views)
    assert manifest.written == []
    assert len(manifest.unchanged) == 2


def test_a_corpus_change_rewrites_the_view(renderer) -> None:
    views = FakeEmittedViewRepository()
    renderer.emit("checkout", [make_case()], views)
    manifest = renderer.emit("checkout", [make_case(), make_case(2)], views)
    assert len(manifest.written) == 2
    assert manifest.hand_edited == []


def test_a_hand_edited_view_is_skipped_and_reported(renderer) -> None:
    views = FakeEmittedViewRepository()
    renderer.emit("checkout", [make_case()], views)
    edited = renderer.path_for("checkout", ".md")
    edited.write_text(
        edited.read_text(encoding="utf-8") + "\n<!-- reviewed by the test lead -->\n",
        encoding="utf-8",
    )

    manifest = renderer.emit("checkout", [make_case()], views)

    assert str(edited) in manifest.hand_edited
    assert str(edited) not in manifest.written
    assert "reviewed by the test lead" in edited.read_text(encoding="utf-8")


def test_a_hand_edit_survives_even_when_the_corpus_also_changed(renderer) -> None:
    """Hand-edit is checked before unchanged, deliberately.

    Overwriting an operator's edit because the corpus happened to move is a rule
    they would find arbitrary, and the edit is not derivable from anything.
    """
    views = FakeEmittedViewRepository()
    renderer.emit("checkout", [make_case()], views)
    edited = renderer.path_for("checkout", ".md")
    edited.write_text("entirely replaced by hand", encoding="utf-8")

    manifest = renderer.emit("checkout", [make_case(), make_case(2)], views)

    assert str(edited) in manifest.hand_edited
    assert edited.read_text(encoding="utf-8") == "entirely replaced by hand"
    # The YAML view was not edited, so it still tracks the corpus.
    assert str(renderer.path_for("checkout", ".yaml")) in manifest.written


def test_a_deleted_view_is_rewritten(renderer) -> None:
    views = FakeEmittedViewRepository()
    renderer.emit("checkout", [make_case()], views)
    renderer.path_for("checkout", ".md").unlink()
    manifest = renderer.emit("checkout", [make_case()], views)
    assert str(renderer.path_for("checkout", ".md")) in manifest.written


# --- paths ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "slug", ["../etc/passwd", "/absolute", "has space", "Upper", "", "a/b", "..", "-lead"]
)
def test_an_unsafe_feature_slug_is_refused(renderer, slug: str) -> None:
    """Refused, not sanitised.

    Rewriting `../etc` to `etc` writes a file the caller did not ask for, which is
    a different wrong answer rather than a right one.
    """
    with pytest.raises(ValueError):
        renderer.path_for(slug, ".md")


def test_views_are_written_under_the_configured_root(renderer, tmp_path) -> None:
    views = FakeEmittedViewRepository()
    manifest = renderer.emit("checkout", [make_case()], views)
    root = tmp_path / "generated" / "testcases"
    assert all(str(root) in p for p in manifest.written)


def test_the_manifest_reports_all_three_buckets() -> None:
    assert ViewManifest().as_dict() == {"written": [], "unchanged": [], "hand_edited": []}
