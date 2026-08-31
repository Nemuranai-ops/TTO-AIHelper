"""S8 ReportingService - the four reports, from SQLite.

**Every figure is a query result.** The agent may explain a report; it may not
produce one (FR-RPT-05). That is the system's central claim: a number the model
composed is a number nobody can reproduce, and one wrong figure in a report the Test
Lead signs off makes every other figure in it suspect.

Sections are declared, not written as methods (P-U8-02). U8-NFR-REL-02 requires every
`not_available` section to carry a reason and a producing stage - and with a method
per section, a test can only check the sections someone remembered to add to it, which
are exactly the sections that were never going to be the problem. A registry lets the
property enumerate it.

Requirements: FR-RPT-01 to FR-RPT-05.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from tto_testgen.adapters.report_renderer import Report, ReportSection, SectionStatus
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import ErrorCode, Result, err, ok

#: A precondition returns (available, reason). `reason` is ignored when available.
Precondition = Callable[[Any], tuple[bool, str]]


@dataclass(frozen=True, slots=True)
class Section:
    """One row of the registry. A section cannot be added without these fields."""

    name: str
    title: str
    report: str
    columns: tuple[str, ...]
    precondition: Precondition
    query: Callable[[Any], list[dict[str, Any]]]
    derivation: str
    producing_stage: str | None = None


# --- preconditions ---------------------------------------------------------------

def always(uow: Any) -> tuple[bool, str]:
    return True, ""


def has_coverage_model(uow: Any) -> tuple[bool, str]:
    rows = uow.reports.coverage_by_test_type()
    if not rows:
        return False, "no coverage model has been built"
    return True, ""


def has_automation(uow: Any) -> tuple[bool, str]:
    if not uow.automation.list_all():
        return False, "no automation has been generated"
    return True, ""


def has_trace_links(uow: Any) -> tuple[bool, str]:
    if not uow.traces.all_links():
        return False, "no traceability links exist yet"
    return True, ""


#: Migration 004's six. Declared here so the gap summary can report an empty
#: category, which is the difference between "nothing found" and "nobody looked".
GAP_CATEGORIES = (
    "untraceable-behaviour", "uncovered-requirement", "boundaries-undetermined",
    "reduced-depth", "rejected-duplicate", "manual-only",
)


# --- queries -----------------------------------------------------------------------

def _rows(records: list[Any]) -> list[dict[str, Any]]:
    return [dict(r) for r in records]


def coverage_by_feature(uow: Any) -> list[dict[str, Any]]:
    out = []
    for row in _rows(uow.reports.coverage_by_feature()):
        planned = int(row.get("planned") or 0)
        generated = int(row.get("generated") or 0)
        out.append({**row, "planned": planned, "generated": generated,
                    "variance": generated - planned})
    return out


def coverage_by_test_type(uow: Any) -> list[dict[str, Any]]:
    out = []
    for row in _rows(uow.reports.coverage_by_test_type()):
        planned = int(row.get("planned") or 0)
        generated = int(row.get("generated") or 0)
        out.append({**row, "planned": planned, "generated": generated,
                    "variance": generated - planned})
    return out


def gaps_by_category(uow: Any) -> list[dict[str, Any]]:
    """All six categories, including those with no entries.

    An absent category is indistinguishable from a category nobody checked
    (FR-RPT-02), which is the whole reason the gap report exists.
    """
    counts = {category: 0 for category in GAP_CATEGORIES}
    for row in _rows(uow.reports.open_gaps()):
        counts[str(row["category"])] = counts.get(str(row["category"]), 0) + 1
    return [{"category": c, "open": counts[c]} for c in sorted(counts)]


def gap_detail(uow: Any) -> list[dict[str, Any]]:
    return [
        {"category": r["category"], "subject": r["subject"],
         "feature": r["feature_slug"] or "", "detail": r["detail"] or ""}
        for r in _rows(uow.reports.open_gaps())
    ]


def automation_rows(uow: Any) -> list[dict[str, Any]]:
    return [
        {"test_id": r["test_id"], "case_id": r["case_id"],
         "case_title": r["case_title"],
         "at_risk": "yes" if r["is_at_risk"] else "",
         "at_risk_reason": r["at_risk_reason"] or ""}
        for r in _rows(uow.reports.automation())
    ]


def deferred_rows(uow: Any) -> list[dict[str, Any]]:
    """Cases with no automated test, and why. FR-RPT-04's second half."""
    return [
        {"case_id": r["case_id"], "title": r["title"],
         "classification": r["classification"], "reason": r["reason"] or ""}
        for r in _rows(uow.reports.deferred())
    ]


def retired_rows(uow: Any) -> list[dict[str, Any]]:
    return [
        {"case_id": r["id"], "title": r["title"],
         "reason": r["obsolete_reason"] or "",
         "change_event": r["obsoleted_by_change_id"] or ""}
        for r in _rows(uow.reports.retired())
    ]


#: The registry. Adding a section is adding a row, and the row cannot be added
#: without a precondition, a derivation and (where applicable) a producing stage.
SECTIONS: tuple[Section, ...] = (
    Section(
        name="by-feature", title="Coverage per feature and test type",
        report="coverage",
        columns=("feature", "test_type", "requirements", "coverage_items",
                 "planned", "generated", "variance"),
        precondition=has_coverage_model, query=coverage_by_feature,
        derivation=(
            "planned = sum of coverage_item.planned_count; generated = distinct "
            "non-obsolete test cases against those items. A coverage item that "
            "produced nothing still appears."
        ),
        producing_stage="coverage",
    ),
    Section(
        name="by-test-type", title="Coverage per test type across the corpus",
        report="coverage",
        columns=("test_type", "planned", "generated", "variance"),
        precondition=has_coverage_model, query=coverage_by_test_type,
        derivation="the same figures, grouped by test type rather than by feature.",
        producing_stage="coverage",
    ),
    Section(
        name="summary", title="Open gaps by category", report="gaps",
        columns=("category", "open"),
        precondition=always, query=gaps_by_category,
        derivation=(
            "open gap rows by category. All six categories appear, including those "
            "with none: an absent category is indistinguishable from one nobody "
            "checked."
        ),
    ),
    Section(
        name="detail", title="Open gaps", report="gaps",
        columns=("category", "subject", "feature", "detail"),
        precondition=always, query=gap_detail,
        derivation="every open gap row, with the reason recorded when it was found.",
    ),
    Section(
        name="tests", title="Generated automated tests", report="automation",
        columns=("test_id", "case_id", "case_title", "at_risk", "at_risk_reason"),
        precondition=has_automation, query=automation_rows,
        derivation=(
            "one row per automated_test. At risk means the locators are unverified "
            "or fragile - unconfirmed, not wrong."
        ),
        producing_stage="automation",
    ),
    Section(
        name="deferred", title="Cases not automated, and why", report="automation",
        columns=("case_id", "title", "classification", "reason"),
        precondition=always, query=deferred_rows,
        derivation=(
            "non-obsolete cases with no automated_test row, carrying the "
            "classifier's own reason. manual-only is a decision; needs-review is "
            "the absence of one."
        ),
    ),
    Section(
        name="retired", title="Retired cases", report="delta",
        columns=("case_id", "title", "reason", "change_event"),
        precondition=always, query=retired_rows,
        derivation=(
            "cases marked obsolete, with the change event that obsoleted them. "
            "Nothing is ever deleted."
        ),
    ),
)

REPORTS = {
    "coverage": "Coverage Report",
    "gaps": "Gap Report",
    "automation": "Automation Report",
    "delta": "Delta and Retirement Report",
}


class ReportingService:
    """Iterates the registry, renders, emits. Composes no figure."""

    def __init__(
        self, uow_factory: Callable[[], Any], renderer: Any, logger: Logger
    ) -> None:
        self._uow_factory = uow_factory
        self._renderer = renderer
        self._logger = logger

    def build(self, report_name: str) -> Result[Report]:
        if report_name not in REPORTS:
            return err(
                ErrorCode.FAILED_INTERNAL,
                f"Unknown report: {report_name}",
                remediation=f"Valid reports are: {', '.join(sorted(REPORTS))}.",
            )
        report = Report(name=report_name, title=REPORTS[report_name])
        with self._uow_factory() as uow:
            for spec in SECTIONS:
                if spec.report != report_name:
                    continue
                report.sections.append(self._section(spec, uow))
        return ok(report)

    def generate(self, report_names: list[str] | None = None) -> Result[dict[str, Any]]:
        names = report_names or sorted(REPORTS)
        built, written, unavailable = [], [], []
        for name in names:
            result = self.build(name)
            if not result.ok:
                return result
            report = result.value
            written += [str(p) for p in self._renderer.emit(report)]
            built.append(report.to_dict())
            unavailable += [
                f"{name}/{s.name}" for s in report.sections
                if s.status is SectionStatus.NOT_AVAILABLE
            ]
        self._logger.info(
            "reports generated", reports=len(built), files=len(written),
            unavailable=len(unavailable),
        )
        return ok({
            "reports": built,
            "files_written": sorted(written),
            "sections_unavailable": unavailable,
            "derivation": (
                "every figure is a query result over the corpus; none is composed "
                "by a model (FR-RPT-05). A section that could not be computed is "
                "named with the stage that would supply it."
            ),
        })

    @staticmethod
    def _section(spec: Section, uow: Any) -> ReportSection:
        available, reason = spec.precondition(uow)
        if not available:
            # P-U6-03's third use: render what can be computed, say plainly what
            # cannot. A report that fails whole because one section is empty is
            # useless during the period it would be most useful.
            return ReportSection(
                name=spec.name, title=spec.title,
                status=SectionStatus.NOT_AVAILABLE,
                columns=spec.columns, derivation=spec.derivation,
                unavailable_reason=reason, producing_stage=spec.producing_stage,
            )
        return ReportSection(
            name=spec.name, title=spec.title, status=SectionStatus.COMPUTED,
            columns=spec.columns, rows=spec.query(uow), derivation=spec.derivation,
            producing_stage=spec.producing_stage,
        )
