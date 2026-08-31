"""S5 GenerationService - the batch, its views, and the traceability matrix.

The only place in the system where six domain components run inside one
transaction. Every algorithm it needs already exists: D1 constructs cases, D3
resolves keys and builds matrices, D4 finds duplicates, D5 allocates identifiers,
D6 classifies automatability, D7 validates. **This service owns the order they run
in, and what must be true when they do** - and holds no copy of any of them
(U4-NFR-MNT-03).

Two patterns carry the weight:

  - **P-U4-01 Deferred Allocation.** Everything that mutates sequence state runs
    after everything that can reject. A transaction would undo the rows; it would
    not undo the identifier counter, and neither restoring nor advancing it is
    acceptable - one reissues TC-0142 to a different case, the other leaves a
    permanent hole.
  - **P-U4-02 Ordered Bulk Insert.** One transaction, executemany per table in
    foreign-key order, integrity sentinel last.

Requirements: FR-TCG-01 to FR-TCG-10, FR-TRC-05, FR-TRC-06.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable

from tto_testgen.domain.classification import CaseSignals, classify_automatability
from tto_testgen.domain.identity import SequenceState, allocate, stable_id_for
from tto_testgen.domain.model import (
    EntityKind,
    encode_id,
    LinkType,
    StageName,
    TestCase,
    TestData,
    TestStep,
    TestType,
    TraceLink,
)
from tto_testgen.domain.similarity import bucket_key, find_duplicate, normalise
from tto_testgen.domain.traceability import MatrixEdge, build_matrix, link_counts_by_type
from tto_testgen.domain.validation import Rejection, validate_case
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import REMEDIATION, ErrorCode, Result, err, ok

#: BR-U4-3.1. Configurable, but a default the operator can hold in their head.
MAX_BATCH = 200

#: The placeholder every constructed case carries until stage F. Never written: an
#: accepted case is renumbered before `upsert_many`, and a rejected one is discarded.
PROVISIONAL_SEQUENCE = 1


@dataclass(slots=True)
class CaseBatchReport:
    feature_slug: str
    accepted: list[str] = field(default_factory=list)
    rejections: list[dict[str, Any]] = field(default_factory=list)
    gaps_recorded: int = 0
    automatability: dict[str, int] = field(default_factory=dict)
    planned_vs_generated: list[dict[str, Any]] = field(default_factory=list)
    view_manifest: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature_slug,
            "accepted": sorted(self.accepted),
            "accepted_count": len(self.accepted),
            "rejections": self.rejections,
            "gaps_recorded": self.gaps_recorded,
            "automatability": self.automatability,
            "planned_vs_generated": self.planned_vs_generated,
            "view_manifest": self.view_manifest,
            # BR-U4-7.3: a shortfall is reported, never closed by padding. Stating
            # the derivation is what makes "no padding" checkable rather than
            # asserted - "40 cases from 12 coverage items" can be verified against
            # the model; "40 cases" cannot.
            "derivation": (
                "one row per coverage item the batch touched, planned_count from "
                "the approved model against non-obsolete cases. A shortfall is "
                "reported, never filled."
            ),
        }


def _as_rejection_dict(ref: str, rejection: Rejection) -> dict[str, Any]:
    return {
        "case_ref": ref,
        "code": rejection.code.value,
        "detail": rejection.detail,
        # Held in one place rather than restated at each call site, so the guidance
        # for a code cannot drift between the services that raise it.
        "remediation": REMEDIATION.get(rejection.code, ""),
    }


def _coerce_test_type(value: Any) -> TestType | None:
    try:
        return TestType(value)
    except ValueError:
        return None


class GenerationService:
    """Batches, views and the matrix. Transactions are owned here, not below."""

    def __init__(
        self,
        uow_factory: Callable[[], Any],
        run_state: Any,
        renderer: Any,
        logger: Logger,
        *,
        max_batch: int = MAX_BATCH,
        privacy_options: dict | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._run_state = run_state
        self._renderer = renderer
        self._logger = logger
        self._max_batch = max_batch
        self._privacy_options = privacy_options or {}

    # --- stage A -------------------------------------------------------------

    def _stage_a(self, feature_slug: str, payloads: list[dict]) -> Result[Any] | None:
        """Gate and cap. The only checks that stop the batch rather than collect.

        A closed gate or an oversized batch makes every case in it moot, so there
        is nothing to collect. Every other fault leaves its neighbours valid.
        """
        gate = self._run_state.is_gate_open(feature_slug, StageName.CASES)
        if not gate.is_open:
            return err(
                ErrorCode.REJECTED_GATE_CLOSED, gate.detail, remediation=gate.remediation
            )
        if len(payloads) > self._max_batch:
            return err(
                ErrorCode.REJECTED_INVALID_STEPS,
                f"{len(payloads)} cases exceeds the {self._max_batch} cap",
                remediation=f"Split the batch into groups of {self._max_batch} or fewer.",
            )
        return None

    # --- stage B: construction ------------------------------------------------

    def _construct(
        self, payload: dict, feature_id: int, feature_slug: str
    ) -> tuple[TestCase | None, str]:
        """D1 construction. Returns the case, or None and the reason.

        `CasePayload` carries no identifier field, so a caller cannot supply one by
        accident; D7's REJECTED_SELF_SUPPLIED_ID catches the deliberate case.

        **The provisional identifier.** `TestCase` validates its id at construction,
        so a case cannot be built without one - but P-U4-01 requires that no real
        identifier is issued until the whole batch is known to be storable. The
        placeholder below satisfies the invariant and is overwritten for every
        accepted case at stage F, before anything is written. Nothing reads it in
        between: validation checks the id's *shape*, and duplicate detection
        compares normalised content.

        Numbering the accepted set only at stage F is what keeps it gapless. If
        identifiers were issued during construction, a batch of five with two
        rejections would store TC-1, TC-3 and TC-5, and the holes would be
        permanent.
        """
        try:
            steps = [
                TestStep(int(s["ordinal"]), str(s["action"]), str(s["expected"]))
                for s in payload.get("steps", [])
            ]
            data = [
                TestData(
                    field_name=str(d["field"]),
                    value=str(d.get("value", "")),
                    equivalence_class=str(d.get("equivalence_class", "")),
                    step_ordinal=d.get("step_ordinal"),
                    boundary_relation=d.get("boundary_relation"),
                )
                for d in payload.get("test_data", [])
            ]
            links = []
            for l in payload.get("trace_links", []):
                link_type = LinkType(l.get("type", "direct-story"))
                target = str(l.get("jira_key") or l.get("target_ref", ""))
                links.append(
                    TraceLink(
                        source_kind="test_case",
                        source_id="",
                        target_ref=target,
                        link_type=link_type,
                        evidence=str(l.get("evidence", "")),
                        selection_basis=l.get("selection_basis"),
                        # The claim, not the verdict. D7 checks it against the
                        # ingested set, which is what separates "this case cites
                        # PAY-12" from "PAY-12 exists" - and the second is the one
                        # an invented key fails.
                        resolved_jira_key=(
                            target if link_type.resolves_jira_key else
                            l.get("resolved_jira_key")
                        ),
                    )
                )
            test_type = _coerce_test_type(payload.get("test_type"))
            if test_type is None:
                return None, f"unknown test type {payload.get('test_type')!r}"
            case = TestCase(
                id=encode_id(EntityKind.TEST_CASE, feature_slug, PROVISIONAL_SEQUENCE),
                feature_id=feature_id,
                coverage_item_id=str(payload.get("coverage_item_id", "")),
                title=str(payload.get("title", "")),
                test_type=test_type,
                priority=str(payload.get("priority", "medium")),
                preconditions=str(payload.get("preconditions", "")),
                steps=steps,
                expected_result=steps[-1].expected if steps else "",
                test_data=data,
                tags=[str(t) for t in payload.get("tags", [])],
                trace_links=links,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return None, str(exc)
        return case, ""

    # --- stage E: signals -----------------------------------------------------

    def _signals(self, payload: dict, case: TestCase, uow: Any) -> CaseSignals:
        """Derived from the models, plus four booleans the agent supplies.

        The four supplied ones default to false, which can only move a case toward
        automatable - so a forgetful agent produces an optimistic classification
        that review catches, not a pessimistic one that quietly shrinks the suite.
        """
        elements: list[Any] = []
        for screen_id in payload.get("referenced_screen_ids", []):
            elements.extend(uow.features.elements_for_screen(int(screen_id)))

        locators = [dict(e) for e in elements]
        return CaseSignals(
            requires_visual_judgement=bool(payload.get("requires_visual_judgement", False)),
            requires_external_step=bool(payload.get("requires_external_step", False)),
            requires_unprovisionable_data=bool(
                payload.get("requires_unprovisionable_data", False)
            ),
            is_exploratory=bool(payload.get("is_exploratory", False)),
            is_api_case=case.test_type == TestType.API_CONTRACT,
            api_shape_source=str(payload.get("api_shape_source", "inferred")),
            is_ui_case=case.test_type == TestType.UI_BEHAVIOUR,
            all_elements_have_locators=bool(locators)
            and all(e.get("locator_chain") for e in locators),
            all_locators_verified=bool(locators) and all(e.get("is_verified") for e in locators),
            has_fragile_locator_without_alternative=any(
                e.get("is_fragile") and not e.get("alternative_locator") for e in locators
            ),
        )

    # --- the batch ------------------------------------------------------------

    def upsert_cases(
        self, feature_slug: str, payloads: list[dict], run_id: int | None = None
    ) -> Result[CaseBatchReport]:
        stopped = self._stage_a(feature_slug, payloads)
        if stopped is not None:
            return stopped

        with self._uow_factory() as uow:
            feature = uow.features.get_by_slug(feature_slug)
            if feature is None:
                return err(ErrorCode.FAILED_INTERNAL, f"Unknown feature: {feature_slug}")
            feature_id = feature["id"]
            known_keys = uow.artefacts.known_jira_keys()

            accepted: list[tuple[dict, TestCase]] = []
            rejections: list[dict[str, Any]] = []
            seen_in_batch: dict[str, list[tuple[str, Any]]] = {}

            for index, payload in enumerate(payloads):
                ref = str(payload.get("title") or f"payload[{index}]")
                failures: list[dict[str, Any]] = []

                # B: the coverage item must exist and agree about the test type.
                item = uow.coverage.get(str(payload.get("coverage_item_id", "")))
                if item is None:
                    failures.append({
                        "case_ref": ref, "code": ErrorCode.REJECTED_INVALID_STEPS.value,
                        "detail": f"unknown coverage item "
                                  f"{payload.get('coverage_item_id')!r}",
                        "remediation": "Build and approve the coverage model first.",
                    })
                elif str(dict(item)["test_type"]) != str(payload.get("test_type")):
                    # Without this, generated-vs-planned is meaningless: five cases
                    # could satisfy one item while another went uncovered and the
                    # totals would still balance.
                    failures.append({
                        "case_ref": ref, "code": ErrorCode.REJECTED_INVALID_STEPS.value,
                        "detail": f"test type {payload.get('test_type')!r} does not "
                                  f"match coverage item {dict(item)['test_type']!r}",
                        "remediation": "Generate the test type the coverage item plans for.",
                    })

                case, construction_error = self._construct(
                    payload, feature_id, feature_slug
                )
                if case is None:
                    failures.append({
                        "case_ref": ref, "code": ErrorCode.REJECTED_NO_STEPS.value,
                        "detail": construction_error,
                        "remediation": "Supply ordered steps, each with an expected result.",
                    })
                else:
                    # B and C: structure, personal data, traceability.
                    for rejection in validate_case(
                        case, known_keys, privacy_options=self._privacy_options
                    ):
                        failures.append(_as_rejection_dict(ref, rejection))

                    # D: duplicates, against the corpus bucket and the batch.
                    key = bucket_key(case, feature_slug)
                    candidates = list(uow.cases.bucket_candidates(key))
                    # BR-U4-4.2: intra-batch as well as corpus. Two identical cases
                    # in one batch are still duplicates, and neither is in the
                    # database yet for the bucket query to find.
                    candidates += seen_in_batch.get(key, [])
                    finding = find_duplicate(case, candidates)
                    if finding is not None:
                        failures.append({
                            "case_ref": ref, "code": ErrorCode.REJECTED_DUPLICATE.value,
                            "detail": f"{finding.verdict.value} of "
                                      f"{finding.existing_case_id} "
                                      f"(similarity {finding.score:.2f})",
                            "matched_case_id": finding.existing_case_id,
                            "score": round(finding.score, 4),
                            "remediation": "Vary the case or drop it; the corpus already covers this.",
                        })

                if failures:
                    rejections.extend(failures)
                elif case is not None:
                    accepted.append((payload, case))
                    seen_in_batch.setdefault(bucket_key(case, feature_slug), []).append(
                        (f"<batch:{ref}>", normalise(case))
                    )

            if rejections:
                # Nothing stored, nothing allocated. P-U4-01.
                self._logger.info(
                    "batch rejected", feature=feature_slug, faults=len(rejections)
                )
                return ok(
                    CaseBatchReport(feature_slug=feature_slug, rejections=rejections)
                )

            # E and F: only now, because both mutate sequence state.
            #
            # Seeded from every identifier ever issued, not from the active ones:
            # obsolete cases are retained and their numbers must never be reissued
            # (BR-6.2), so the high-water mark has to include them.
            state = SequenceState.from_existing(list(uow.cases.existing_identifiers()))
            existing = [
                (str(r["id"]), str(r["coverage_item_id"]), str(r["title"]),
                 bool(r["is_obsolete"]))
                for r in uow.cases.query(feature_id=feature_id, limit=self._max_batch,
                                         include_obsolete=True).items
            ]

            # TestCase is frozen, so stage F builds the finished case rather than
            # mutating the provisional one. That suits P-U4-01: the object that
            # survives validation and the object that gets stored are visibly
            # different values, and nothing can accidentally write the first.
            counts: dict[str, int] = {}
            cases: list[TestCase] = []
            for payload, case in accepted:
                verdict = classify_automatability(self._signals(payload, case, uow))
                counts[verdict.verdict.value] = counts.get(verdict.verdict.value, 0) + 1

                stable = stable_id_for(case.coverage_item_id, case.title, existing)
                if stable is not None:
                    case_id = stable          # a regeneration keeps its number
                else:
                    case_id, state = allocate(EntityKind.TEST_CASE, feature_slug, state)

                cases.append(
                    replace(
                        case,
                        id=case_id,
                        automatability=verdict.verdict,
                        automatability_reason=verdict.reason,
                        trace_links=[
                            replace(link, source_id=case_id) for link in case.trace_links
                        ],
                    )
                )
            uow.cases.upsert_many(cases, feature_slug)

            # No `rejected-duplicate` gap is written here, and there is nothing to
            # write: a duplicate finding always adds a rejection, and a rejected
            # batch returns above without storing anything. Recording a gap for a
            # batch that was refused wholesale would claim the corpus knows about a
            # case it never accepted. The rejection report carries the duplicate,
            # naming the case it matched.
            gaps = 0
            for case in cases:
                if case.automatability.value == "manual-only":
                    uow.gaps.add({
                        "category": "manual-only",
                        "subject": case.id,
                        "feature_slug": feature_slug,
                        "detail": case.automatability_reason,
                    })
                    gaps += 1

            volume = self._volume_rows(uow, feature_id)
            manifest = self._emit(uow, feature_slug)

        self._logger.info(
            "batch accepted", feature=feature_slug, cases=len(cases), gaps=gaps
        )
        return ok(
            CaseBatchReport(
                feature_slug=feature_slug,
                accepted=[c.id for c in cases],
                gaps_recorded=gaps,
                automatability=counts,
                planned_vs_generated=volume,
                view_manifest=manifest,
            )
        )

    # --- views -----------------------------------------------------------------

    def _emit(self, uow: Any, feature_slug: str) -> dict[str, list[str]]:
        cases = uow.cases.for_feature_slug(feature_slug)
        return self._renderer.emit(feature_slug, cases, uow.views).as_dict()

    def emit_views(self, feature_slug: str) -> Result[dict[str, Any]]:
        """Re-emit one feature's views without generating anything.

        Only the features a batch touched are re-emitted (U4-NFR-PRF-06). Doing all
        150 after every batch would dominate the batch time, rewrite 148 files that
        did not change, and defeat hand-edit detection by touching files the
        operator never asked about.
        """
        with self._uow_factory() as uow:
            if uow.features.get_by_slug(feature_slug) is None:
                return err(ErrorCode.FAILED_INTERNAL, f"Unknown feature: {feature_slug}")
            return ok({"feature": feature_slug, "view_manifest": self._emit(uow, feature_slug)})

    # --- volume ------------------------------------------------------------------

    def _volume_rows(self, uow: Any, feature_id: int) -> list[dict[str, Any]]:
        rows = []
        for row in uow.coverage.volume_for_feature(feature_id):
            record = dict(row)
            planned = int(record.get("planned") or 0)
            generated = int(record.get("generated") or 0)
            rows.append({
                "coverage_item_id": record.get("coverage_item_id"),
                "requirement_id": record.get("requirement_id"),
                "test_type": record.get("test_type"),
                "technique": record.get("technique"),
                "planned": planned,
                "generated": generated,
                "variance": generated - planned,
            })
        return rows

    def volume_report(self, feature_slug: str | None = None) -> Result[dict[str, Any]]:
        with self._uow_factory() as uow:
            per_feature = [dict(r) for r in uow.cases.volume_by_feature()]
            detail: list[dict[str, Any]] = []
            if feature_slug is not None:
                feature = uow.features.get_by_slug(feature_slug)
                if feature is None:
                    return err(ErrorCode.FAILED_INTERNAL, f"Unknown feature: {feature_slug}")
                detail = self._volume_rows(uow, feature["id"])

        shortfalls = [r for r in detail if r["variance"] < 0]
        return ok({
            "per_feature": per_feature,
            "per_coverage_item": detail,
            "shortfalls": shortfalls,
            "derivation": (
                "planned_count from the approved coverage model against "
                "non-obsolete cases. A shortfall is reported, never padded "
                "(BR-U4-7.3)."
            ),
        })

    # --- the matrix ---------------------------------------------------------------

    def trace_matrix(self, fmt: str = "markdown") -> Result[dict[str, Any]]:
        """Built on demand from `trace_link`, never stored.

        A stored matrix is a second copy of the truth and the first thing to go
        stale - and its most valuable output is the *uncovered* list, where a stale
        cache reports a requirement as covered after the case covering it was
        retired. Silent false confidence is the exact thing this system exists to
        remove.

        Streamed rather than materialised (P-U4-05): this is the largest read in
        the system and the one an operator runs when the corpus is at its biggest.
        """
        with self._uow_factory() as uow:
            edges: list[MatrixEdge] = []
            links: list[Any] = []
            for row in uow.traces.stream_links():
                record = dict(row)
                edges.append(
                    MatrixEdge("case", record["source_id"], "target", record["target_ref"])
                )
                links.append(record)
            requirements = list(uow.traces.stream_requirement_ids())

        matrix = build_matrix(edges, all_sources=requirements)
        # Direct and derived counted apart: provenance is weaker evidence than
        # specification, and merging them would overstate how well the corpus is
        # grounded (BR-U4-6.3).
        by_type: dict[str, int] = {}
        for record in links:
            key = str(record.get("link_type"))
            by_type[key] = by_type.get(key, 0) + 1

        return ok({
            "forward": matrix.forward,
            "reverse": matrix.reverse,
            "uncovered": matrix.uncovered(requirements),
            "counts_by_link_type": by_type,
            "consistent": matrix.is_bidirectionally_consistent(),
            "format": fmt,
        })
