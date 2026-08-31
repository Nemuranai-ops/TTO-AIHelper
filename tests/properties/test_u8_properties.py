"""The 12 U8 properties.

PBT-U8-10 and -12 are the pair that make a partial baseline advance unreachable rather
than merely refused. The failure they guard against is permanent and silent, so it
cannot be caught by testing what you expected — the property enumerates every
combination instead.
"""

from __future__ import annotations

import csv
import io

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tto_testgen.adapters.change_detector import DetectionResult
from tto_testgen.adapters.report_renderer import (
    Report,
    ReportSection,
    SectionStatus,
    render_csv,
    render_markdown,
)
from tto_testgen.services.delta import advance_baseline
from tto_testgen.services.reporting import REPORTS, SECTIONS

SETTINGS = settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)

slugs = st.from_regex(r"\A[a-z][a-z0-9-]{0,10}\Z")
shas = st.from_regex(r"\A[0-9a-f]{7,40}\Z")
sources = st.from_regex(r"\A(bitbucket|jira)(:[a-z-]{1,8})?\Z")
free_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc")), max_size=30
)


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def record_baseline(self, run_id, head_commits, jira_watermark) -> None:
        self.calls.append((run_id, head_commits, jira_watermark))


# --- the baseline guard -----------------------------------------------------------

class TestBaselineGuard:
    @SETTINGS
    @given(
        heads=st.dictionaries(slugs, shas, max_size=3),
        watermark=st.one_of(st.none(), st.just("2026-08-31T00:00:00Z")),
        unavailable=st.lists(st.tuples(sources, free_text), max_size=3),
    )
    def test_pbt_u8_10_advance_only_when_every_source_answered(
        self, heads, watermark, unavailable
    ):
        """Enumerated rather than exampled.

        Advancing after a partial detection makes the undetected changes invisible
        for ever, and nothing downstream would reveal it. An invisible failure
        cannot be caught by testing the cases someone thought of.
        """
        recorder = Recorder()
        detection = DetectionResult(
            head_commits=heads, jira_watermark=watermark,
            unavailable_sources=list(unavailable),
        )
        advanced = advance_baseline(1, detection, recorder)
        assert advanced == (not unavailable)
        assert bool(recorder.calls) == advanced

    @SETTINGS
    @given(unavailable=st.lists(st.tuples(sources, free_text), min_size=1, max_size=3))
    def test_a_partial_detection_writes_nothing(self, unavailable):
        recorder = Recorder()
        detection = DetectionResult(
            head_commits={"app": "abc123"}, jira_watermark="2026-08-31T00:00:00Z",
            unavailable_sources=list(unavailable),
        )
        assert advance_baseline(1, detection, recorder) is False
        assert recorder.calls == []

    @SETTINGS
    @given(heads=st.dictionaries(slugs, shas, max_size=3))
    def test_complete_is_the_inverse_of_having_unavailable_sources(self, heads):
        assert DetectionResult(head_commits=heads).complete is True
        assert DetectionResult(
            head_commits=heads, unavailable_sources=[("jira", "down")]
        ).complete is False


# --- the section registry ------------------------------------------------------------

class TestSectionRegistry:
    def test_pbt_u8_1_a_section_without_a_precondition_cannot_exist(self):
        """The registry makes this structural: a row cannot omit the field."""
        for spec in SECTIONS:
            assert spec.precondition is not None
            assert callable(spec.precondition)

    def test_pbt_u8_2_every_section_can_produce_a_complete_not_available_result(self):
        """Enumerated over the registry rather than over a hand-maintained list -
        which would only cover the sections someone remembered to add."""
        for spec in SECTIONS:
            section = ReportSection(
                name=spec.name, title=spec.title,
                status=SectionStatus.NOT_AVAILABLE, columns=spec.columns,
                derivation=spec.derivation, unavailable_reason="a reason",
                producing_stage=spec.producing_stage,
            )
            rendered = render_markdown(Report(spec.report, spec.report, [section]))
            assert "Not available: a reason" in rendered

    def test_pbt_u8_9_every_section_carries_a_derivation(self):
        for spec in SECTIONS:
            assert spec.derivation.strip(), spec.name

    def test_every_section_belongs_to_a_declared_report(self):
        for spec in SECTIONS:
            assert spec.report in REPORTS


# --- rendering ---------------------------------------------------------------------------

rows = st.lists(
    st.fixed_dictionaries({"feature": free_text, "planned": st.integers(0, 999),
                           "generated": st.integers(0, 999)}),
    max_size=6,
)


def section_of(rows_in, status=SectionStatus.COMPUTED):
    return ReportSection(
        name="coverage", title="Coverage", status=status,
        columns=("feature", "planned", "generated"), rows=list(rows_in),
        derivation="planned against generated",
    )


class TestRendering:
    @SETTINGS
    @given(data=rows)
    def test_pbt_u8_8_rendering_is_byte_stable(self, data):
        report = Report("coverage", "Coverage", [section_of(data)])
        assert render_markdown(report) == render_markdown(report)

    @SETTINGS
    @given(data=rows)
    def test_pbt_u8_3_a_not_available_section_never_suppresses_a_computed_one(self, data):
        """A report that fails whole because one section is empty is useless during
        the period it would be most useful."""
        report = Report("coverage", "Coverage", [
            ReportSection(name="missing", title="Missing",
                          status=SectionStatus.NOT_AVAILABLE,
                          columns=("a",), unavailable_reason="no model",
                          producing_stage="coverage"),
            section_of(data),
        ])
        rendered = render_markdown(report)
        assert "Not available" in rendered
        assert "planned against generated" in rendered

    @SETTINGS
    @given(data=rows)
    def test_pbt_u8_11_csv_round_trips_every_field(self, data):
        """A comma, a quote or a newline in a statement must not shift the columns."""
        section = section_of(data)
        parsed = list(csv.reader(io.StringIO(render_csv(section))))
        assert parsed[0] == list(section.columns)
        assert len(parsed) == len(data) + 1
        for original, row in zip(data, parsed[1:]):
            assert row[0] == str(original["feature"])
            assert row[1] == str(original["planned"])

    @SETTINGS
    @given(data=rows)
    def test_csv_never_emits_a_carriage_return(self, data):
        assert "\r" not in render_csv(section_of(data))

    @SETTINGS
    @given(data=st.lists(
        st.fixed_dictionaries({"feature": st.text(min_size=1, max_size=20),
                               "planned": st.integers(0, 99),
                               "generated": st.integers(0, 99)}),
        min_size=1, max_size=4,
    ))
    def test_a_markdown_row_never_loses_a_cell(self, data):
        report = Report("coverage", "Coverage", [section_of(data)])
        for line in render_markdown(report).splitlines():
            if line.startswith("| ") and not line.startswith("|---"):
                assert line.replace("\\|", "").count("|") == 4
