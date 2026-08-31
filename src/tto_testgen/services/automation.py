"""S6 AutomationService - the emission, its refusals, and the automation report.

S6 makes no judgement about whether a case can be automated: D6 decided that in U4,
and this service reads the verdict. What it owns is the order - gate, partition,
refuse, render, emit, record - and what must be true at each point.

Requirements: FR-AUT-01 to FR-AUT-11.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from tto_testgen.domain.identity import SequenceState, allocate
from tto_testgen.domain.locators import resolve
from tto_testgen.domain.model import AutomatedTest, EntityKind, StageName
from tto_testgen.domain.secrets import scan_case
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import ErrorCode, Result, err, ok

AUTOMATABLE = "automatable"


@dataclass(slots=True)
class NotAutomated:
    case_id: str
    classification: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "classification": self.classification,
            "reason": self.reason,
        }


@dataclass(slots=True)
class EmissionReport:
    feature_slug: str
    tests_emitted: list[str] = field(default_factory=list)
    not_automated: list[NotAutomated] = field(default_factory=list)
    refusals: list[dict[str, Any]] = field(default_factory=list)
    at_risk: list[str] = field(default_factory=list)
    manifest: dict[str, list[str]] = field(default_factory=dict)
    oversized_specs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        by_class: dict[str, int] = {}
        for entry in self.not_automated:
            by_class[entry.classification] = by_class.get(entry.classification, 0) + 1
        return {
            "feature": self.feature_slug,
            "tests_emitted": sorted(self.tests_emitted),
            "tests_emitted_count": len(self.tests_emitted),
            # Reported apart: manual-only is a decision, needs-review is the absence
            # of one, and the second is the actionable half (FR-AUT-10).
            "not_automated": [n.to_dict() for n in self.not_automated],
            "not_automated_by_class": by_class,
            "refusals": self.refusals,
            "at_risk": sorted(self.at_risk),
            "at_risk_count": len(self.at_risk),
            "manifest": self.manifest,
            "oversized_specs": self.oversized_specs,
            "derivation": (
                "one test per automatable case. needs-review and manual-only cases "
                "produce no test and are listed with the classifier's own reason."
            ),
        }


class AutomationService:
    """Emission and the automation report. Transactions are owned here."""

    def __init__(
        self,
        uow_factory: Callable[[], Any],
        run_state: Any,
        emitter: Any,
        logger: Logger,
        *,
        max_spec_lines: int = 5000,
        extra_credential_fields: frozenset[str] = frozenset(),
    ) -> None:
        self._uow_factory = uow_factory
        self._run_state = run_state
        self._emitter = emitter
        self._logger = logger
        self._max_spec_lines = max_spec_lines
        self._extra_credential_fields = extra_credential_fields

    # --- the emission ---------------------------------------------------------

    def emit(
        self, feature_slug: str, *, include_scaffold: bool = True,
        run_id: int | None = None,
    ) -> Result[EmissionReport]:
        gate = self._run_state.is_gate_open(feature_slug, StageName.AUTOMATION)
        if not gate.is_open:
            return err(
                ErrorCode.REJECTED_GATE_CLOSED, gate.detail, remediation=gate.remediation
            )

        report = EmissionReport(feature_slug=feature_slug)

        with self._uow_factory() as uow:
            feature = uow.features.get_by_slug(feature_slug)
            if feature is None:
                return err(ErrorCode.FAILED_INTERNAL, f"Unknown feature: {feature_slug}")
            feature_id, feature_name = feature["id"], feature["name"]

            cases = uow.cases.for_feature_slug(feature_slug)
            renderable, refusals = [], []
            for case in cases:
                classification = str(case.get("automatability", ""))
                if classification != AUTOMATABLE:
                    report.not_automated.append(
                        NotAutomated(
                            case_id=str(case["id"]),
                            classification=classification,
                            # D6's own words, carried through unchanged. Rewording
                            # would put a second explanation of one decision into
                            # circulation, and the two would eventually disagree.
                            reason=str(case.get("automatability_reason", "")),
                        )
                    )
                    continue

                findings = scan_case(
                    _CaseView(case),
                    extra_credential_fields=self._extra_credential_fields,
                )
                if findings:
                    refusals += [
                        {
                            "case_id": str(case["id"]),
                            "code": ErrorCode.REJECTED_PERSONAL_DATA.value,
                            "detail": finding.message(),
                        }
                        for finding in findings
                    ]
                    continue
                renderable.append(case)

            if refusals:
                # Nothing written. A partial project is worse than none: it runs,
                # and the missing tests look like passes.
                report.refusals = refusals
                self._logger.info(
                    "emission refused", feature=feature_slug, faults=len(refusals)
                )
                return ok(report)

            elements = uow.features.elements_for_feature(feature_id)
            manifest = self._render_and_emit(
                uow, feature_slug, feature_name, renderable, elements, include_scaffold
            )
            report.manifest = manifest
            report.oversized_specs = list(getattr(self, "_oversized", []))

            state = SequenceState.from_existing(
                [str(r["id"]) for r in uow.automation.for_feature_slug(feature_slug)]
                + [str(r["id"]) for r in uow.automation.list_at_risk()]
            )
            uow.automation.clear_for_feature(feature_slug)

            spec_path = str(self._emitter.spec_path(feature_slug))
            for case in sorted(renderable, key=lambda c: str(c["id"])):
                at_risk, reason = self._risk_of(case, elements)
                test_id, state = allocate(
                    EntityKind.AUTOMATED_TEST, feature_slug, state
                )
                uow.automation.upsert(
                    AutomatedTest(
                        id=test_id,
                        case_id=str(case["id"]),
                        spec_path=spec_path,
                        test_name=f"{case['id']} {case['title']}",
                        input_hash=self._input_hash(case),
                        is_at_risk=at_risk,
                        at_risk_reason=reason if at_risk else None,
                    )
                )
                report.tests_emitted.append(test_id)
                if at_risk:
                    report.at_risk.append(test_id)

            # No gap rows are written here. U4 already recorded a `manual-only` gap
            # for every case D6 declined, and re-recording it would double-count in
            # U8's gap report - which reads the table, not this report. The
            # needs-review/manual-only distinction lives in `not_automated`, where
            # the Automation Engineer is actually looking.

        self._logger.info(
            "automation emitted", feature=feature_slug,
            tests=len(report.tests_emitted), at_risk=len(report.at_risk),
        )
        return ok(report)

    # --- rendering -------------------------------------------------------------

    def _render_and_emit(
        self, uow: Any, feature_slug: str, feature_name: str,
        cases: list[Any], elements: list[Any], include_scaffold: bool,
    ) -> dict[str, list[str]]:
        outcomes: dict[str, list[str]] = {"written": [], "unchanged": [], "hand_edited": []}
        self._oversized: list[str] = []

        def record(path, content, slug, count=0):
            outcomes[self._emitter.emit_file(path, content, slug, uow.views, count)].append(
                str(path)
            )

        by_screen: dict[str, list[Any]] = {}
        for element in elements:
            by_screen.setdefault(str(element["screen_name"]), []).append(element)

        page_imports = []
        for screen_name in sorted(by_screen):
            slug = _slug(screen_name)
            path = self._emitter.page_path(slug)
            content = self._emitter.render_page_object(
                {"screen_name": screen_name,
                 "screen_route": by_screen[screen_name][0]["screen_route"]},
                by_screen[screen_name],
            )
            record(path, content, feature_slug)
            page_imports.append(
                f"import {{ {_class(slug)} }} from '../pages/{slug}.page';"
            )

        ui_cases = [c for c in cases if str(c["test_type"]) != "api-contract"]
        api_cases = [c for c in cases if str(c["test_type"]) == "api-contract"]

        if ui_cases:
            content = self._emitter.render_spec(
                feature_slug, feature_name, ui_cases, page_imports=page_imports
            )
            path = self._emitter.spec_path(feature_slug)
            record(path, content, feature_slug, len(ui_cases))
            self._check_spec_size(path, content)
        if api_cases:
            content = self._emitter.render_spec(
                feature_slug, feature_name, api_cases, api=True
            )
            path = self._emitter.spec_path(feature_slug, api=True)
            record(path, content, feature_slug, len(api_cases))
            self._check_spec_size(path, content)

        if include_scaffold:
            from tto_testgen.adapters.playwright_emitter import PROJECT_SLUG

            for relative, content in self._emitter.render_scaffold():
                record(self._emitter.path_for(relative), content, PROJECT_SLUG)

        return {key: sorted(value) for key, value in outcomes.items()}

    def _check_spec_size(self, path: Any, content: str) -> None:
        """U5-NFR-SCL-04. Per-feature scoping is right for 40 cases and questionable
        for 400, and the threshold makes that visible rather than letting one
        enormous file appear unremarked at handover."""
        lines = content.count("\n") + 1
        if lines > self._max_spec_lines:
            self._oversized.append(f"{path} ({lines} lines)")
            self._logger.warning(
                "spec file exceeds the line threshold",
                path=str(path), lines=lines, threshold=self._max_spec_lines,
            )

    # --- helpers ------------------------------------------------------------------

    def _risk_of(self, case: Any, elements: list[Any]) -> tuple[bool, str]:
        """A test resting wholly on unverified locators is unconfirmed, not wrong.

        The distinction is the point of `is_verified`, and the report needs it so it
        can state how much of the suite rests on underived evidence without anyone
        reading the generated code to find out.
        """
        resolved = [resolve(e) for e in elements]
        usable = [r for r in resolved if r is not None]
        if not usable:
            return False, ""
        if all(not r.is_verified for r in usable):
            return True, "every locator this test uses is unverified"
        if any(r.is_fragile for r in usable):
            return True, "at least one locator is fragile with no alternative recorded"
        return False, ""

    @staticmethod
    def _input_hash(case: Any) -> str:
        """What the test was generated from.

        Two runs producing the same input hash and different output hashes means the
        generator is non-deterministic - a fault no amount of reading the output
        would reveal (FR-AUT-11).
        """
        import hashlib
        import json

        payload = json.dumps(
            {
                "id": str(case["id"]),
                "title": str(case["title"]),
                "steps": [
                    {"o": s["ordinal"], "a": s["action"], "e": s["expected"]}
                    for s in case.get("steps", [])
                ],
                "data": [
                    {"f": d["field_name"], "v": d["value"]}
                    for d in case.get("test_data", [])
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    # --- the report --------------------------------------------------------------------

    def automation_report(self, feature_slug: str | None = None) -> Result[dict[str, Any]]:
        with self._uow_factory() as uow:
            counts = dict(uow.automation.counts())
            at_risk = [dict(r) for r in uow.automation.list_at_risk()]
            rows = (
                [dict(r) for r in uow.automation.for_feature_slug(feature_slug)]
                if feature_slug
                else []
            )
        return ok({
            "total_tests": counts.get("total") or 0,
            "at_risk_total": counts.get("at_risk") or 0,
            "at_risk": at_risk,
            "feature": feature_slug,
            "tests": rows,
            "derivation": (
                "one automated_test row per automatable case. at_risk marks a test "
                "whose locators are unverified or fragile - unconfirmed, not wrong."
            ),
        })


class _CaseView:
    """Adapts a row to the attribute access L13 expects, without copying it."""

    __slots__ = ("_row",)

    def __init__(self, row: Any) -> None:
        self._row = row

    @property
    def preconditions(self) -> str:
        return str(self._row.get("preconditions", ""))

    @property
    def steps(self) -> list[Any]:
        return [_Attr(s) for s in self._row.get("steps", [])]

    @property
    def test_data(self) -> list[Any]:
        return [_Attr(d) for d in self._row.get("test_data", [])]


class _Attr:
    __slots__ = ("_row",)

    def __init__(self, row: Any) -> None:
        self._row = row

    def __getattr__(self, name: str) -> Any:
        return self._row.get(name)


def _slug(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "screen"


def _class(slug: str) -> str:
    import re

    parts = [p for p in re.split(r"[^A-Za-z0-9]+", slug) if p]
    return "".join(p[:1].upper() + p[1:] for p in parts) + "Page"
