"""L16 ReportRenderer."""

from __future__ import annotations

import csv
import io

import pytest

from tto_testgen.adapters.report_renderer import (
    Report,
    ReportRenderer,
    ReportSection,
    SectionStatus,
    render_csv,
    render_markdown,
    scan_rendered,
)


def section(**over) -> ReportSection:
    base = {
        "name": "coverage", "title": "Coverage per feature",
        "columns": ("feature", "planned", "generated"),
        "rows": [
            {"feature": "checkout", "planned": 47, "generated": 40},
            {"feature": "basket", "planned": 12, "generated": 12},
        ],
        "derivation": "sum of coverage_item.planned_count against non-obsolete cases",
    }
    return ReportSection(**{**base, **over})


def report(*sections) -> Report:
    return Report(name="coverage", title="Coverage Report",
                  sections=list(sections) or [section()])


@pytest.fixture()
def renderer(tmp_path):
    return ReportRenderer(tmp_path / "reports")


# --- determinism ------------------------------------------------------------------

def test_two_renders_are_byte_identical():
    subject = report()
    assert render_markdown(subject) == render_markdown(subject)


def test_no_timestamp_run_id_or_absolute_path_is_rendered():
    content = render_markdown(report())
    assert "run_id" not in content
    assert "/Users/" not in content and "/private/" not in content
    assert "2026-" not in content


def test_the_banner_states_that_no_figure_is_composed():
    """FR-RPT-05 is the system's central claim; the report says so on its face."""
    content = render_markdown(report())
    assert "composed by a model" in content


# --- derivations --------------------------------------------------------------------

def test_every_section_renders_its_derivation():
    content = render_markdown(report())
    assert "sum of coverage_item.planned_count" in content


def test_a_figure_without_context_is_not_what_is_rendered():
    """'40 cases' is not a report. '40 from 47 planned' can be checked."""
    content = render_markdown(report())
    assert "47" in content and "40" in content


# --- the three states ------------------------------------------------------------------

def test_a_not_available_section_names_its_reason_and_stage():
    subject = report(section(
        status=SectionStatus.NOT_AVAILABLE,
        rows=[],
        unavailable_reason="no approved coverage model for this feature",
        producing_stage="coverage",
    ))
    content = render_markdown(subject)
    assert "Not available: no approved coverage model" in content
    assert "**coverage** stage" in content


def test_an_empty_computed_section_is_distinct_from_not_available():
    """A section with no rows means every requirement is uncovered - alarming. One
    that could not be computed means the model is not approved yet - ordinary."""
    empty = render_markdown(report(section(rows=[])))
    unavailable = render_markdown(report(section(
        status=SectionStatus.NOT_AVAILABLE, rows=[],
        unavailable_reason="no model", producing_stage="coverage",
    )))
    assert "_No rows._" in empty
    assert "Not available" not in empty
    assert "Not available" in unavailable


def test_a_not_available_section_never_fails_the_report():
    subject = report(
        section(status=SectionStatus.NOT_AVAILABLE, rows=[],
                unavailable_reason="no model", producing_stage="coverage"),
        section(name="gaps", title="Gaps"),
    )
    content = render_markdown(subject)
    assert "Not available" in content
    assert "checkout" in content, "the computable section still rendered"


# --- markdown escaping -------------------------------------------------------------------

def test_a_pipe_in_a_value_does_not_break_the_table():
    subject = report(section(rows=[{"feature": "a|b", "planned": 1, "generated": 1}]))
    row = [l for l in render_markdown(subject).splitlines() if "a\\|b" in l][0]
    assert row.replace("\\|", "").count("|") == 4


def test_a_newline_in_a_value_is_flattened():
    subject = report(section(rows=[{"feature": "one\ntwo", "planned": 1, "generated": 1}]))
    content = render_markdown(subject)
    assert "one two" in content


# --- CSV -------------------------------------------------------------------------------------

def test_csv_round_trips_a_comma_in_a_value():
    """String joining would shift the columns for exactly the rows whose text is most
    interesting, and a shifted matrix is worse than none because it looks right."""
    subject = section(rows=[{"feature": "checkout, express", "planned": 1, "generated": 1}])
    parsed = list(csv.reader(io.StringIO(render_csv(subject))))
    assert parsed[1] == ["checkout, express", "1", "1"]


def test_csv_round_trips_a_quote_and_a_newline():
    subject = section(rows=[{"feature": 'say "hi"\nagain', "planned": 1, "generated": 1}])
    parsed = list(csv.reader(io.StringIO(render_csv(subject))))
    assert parsed[1][0] == 'say "hi"\nagain'


def test_csv_uses_a_pinned_line_terminator():
    """The default \\r\\n would break byte-stability across platforms."""
    assert "\r\n" not in render_csv(section())


def test_csv_writes_a_header_row():
    parsed = list(csv.reader(io.StringIO(render_csv(section()))))
    assert parsed[0] == ["feature", "planned", "generated"]


# --- the last-line scan -----------------------------------------------------------------------

def test_a_personal_email_in_a_report_is_detected():
    findings = scan_rendered("| checkout | alice.brown@customer.co.uk | 1 |")
    assert any("email" in f for f in findings)


def test_a_connection_string_in_a_report_is_detected():
    findings = scan_rendered("| dsn | postgres://u:pw@db.internal/app | 1 |")
    assert any("connection-string" in f for f in findings)


def test_ordinary_report_content_is_clean():
    assert scan_rendered(render_markdown(report())) == []


def test_emission_refuses_a_report_carrying_personal_data(renderer):
    subject = report(section(rows=[
        {"feature": "alice.brown@customer.co.uk", "planned": 1, "generated": 1}
    ]))
    with pytest.raises(ValueError, match="email"):
        renderer.emit(subject)


def test_emission_refuses_a_report_carrying_an_absolute_path(renderer):
    subject = report(section(rows=[
        {"feature": "/Users/someone/project", "planned": 1, "generated": 1}
    ]))
    with pytest.raises(ValueError, match="absolute path"):
        renderer.emit(subject)


# --- emission --------------------------------------------------------------------------------------

def test_emission_writes_markdown_and_a_csv_per_populated_section(renderer, tmp_path):
    written = renderer.emit(report())
    names = {p.name for p in written}
    assert "coverage.md" in names
    assert "coverage-coverage.csv" in names
    assert all(str(tmp_path / "reports") in str(p) for p in written)


def test_a_not_available_section_produces_no_csv(renderer):
    written = renderer.emit(report(section(
        status=SectionStatus.NOT_AVAILABLE, rows=[],
        unavailable_reason="no model", producing_stage="coverage",
    )))
    assert not any(p.suffix == ".csv" for p in written)


def test_formats_can_be_narrowed(tmp_path):
    written = ReportRenderer(tmp_path / "r", formats=("markdown",)).emit(report())
    assert all(p.suffix == ".md" for p in written)


@pytest.mark.parametrize("name", ["../etc", "/abs", "has space", "Upper", "", "a/b"])
def test_an_unsafe_report_name_is_refused(renderer, name):
    with pytest.raises(ValueError):
        renderer.path_for(name, ".md")
