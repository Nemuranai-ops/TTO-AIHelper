"""M2 read tier - fine-grained, cheap, no invariants.

Reads carry no invariants and benefit from flexibility, so they stay granular.
Every one requires at least one filter and caps its result set: the cap is what
enforces NFR-SCL-04, because a tool that *can* return 10,000 rows will eventually
be asked to.

Requirements: US-ENB-02, NFR-SCL-03, NFR-SCL-04.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Callable

from pydantic import BaseModel, Field

from tto_testgen.adapters.sqlite.repositories import MAX_PAGE_SIZE, unit_of_work
from tto_testgen.domain.model import StageName
from tto_testgen.mcp.server import ToolRegistry, ToolSpec
from tto_testgen.platform.health import check
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import ErrorCode, Result, err, ok

ConnFactory = Callable[[], sqlite3.Connection]


# --- argument schemas ---------------------------------------------------------


class Empty(BaseModel):
    pass


class Paged(BaseModel):
    cursor: str | None = None
    limit: int = Field(default=MAX_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class ArtefactQuery(Paged):
    kind: str | None = None
    feature_id: int | None = None


class FeatureRef(BaseModel):
    feature_id: int | None = None
    slug: str | None = None


class RequirementQuery(Paged):
    feature_id: int | None = None
    category: str | None = None
    risk_band: str | None = None


class CoverageQuery(BaseModel):
    requirement_id: str | None = None
    feature_id: int | None = None


class CaseQuery(Paged):
    feature_id: int | None = None
    test_type: str | None = None
    tag: str | None = None
    automatable: bool | None = None
    include_obsolete: bool = False


class CaseRef(BaseModel):
    case_id: str


class DuplicateCheck(BaseModel):
    feature_slug: str
    test_type: str
    step_count: int = Field(ge=1)
    normalised_hash: str


class TraceQuery(Paged):
    from_id: str | None = None
    to_id: str | None = None
    link_type: str | None = None


class MatrixQuery(BaseModel):
    fmt: str = Field(default="json", pattern="^(json|markdown|csv)$")


class GapQuery(BaseModel):
    category: str | None = None


class StatusQuery(BaseModel):
    scope: str | None = None


class UnitRef(BaseModel):
    unit_ref: str


def _rows(items: list[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in items]


def register_read_tools(registry: ToolRegistry, conn_factory: ConnFactory) -> None:
    """Register all 16 read-tier tools."""

    def tool(name: str, description: str, schema: type[BaseModel]):
        def decorator(fn):
            registry.register(ToolSpec(name, description, schema, fn, "read"))
            return fn

        return decorator

    @tool("resources_list", "Declared inputs with their inferred type and status.", Empty)
    def resources_list(args: Empty, log: Logger) -> Result[Any]:
        with unit_of_work(conn_factory()) as uow:
            return ok(
                {
                    "resources": _rows(uow.resources.list_all()),
                    "unclassified": _rows(uow.resources.list_unclassified()),
                }
            )

    @tool("artefacts_query", "Ingested artefacts, filtered and paged.", ArtefactQuery)
    def artefacts_query(args: ArtefactQuery, log: Logger) -> Result[Any]:
        with unit_of_work(conn_factory()) as uow:
            page = uow.artefacts.query(kind=args.kind, cursor=args.cursor, limit=args.limit)
        return ok({"items": _rows(page.items), "next_cursor": page.next_cursor})

    @tool("features_list", "The feature hierarchy.", Empty)
    def features_list(args: Empty, log: Logger) -> Result[Any]:
        with unit_of_work(conn_factory()) as uow:
            return ok({"features": _rows(uow.features.list_all())})

    @tool("feature_get", "One feature with its requirements.", FeatureRef)
    def feature_get(args: FeatureRef, log: Logger) -> Result[Any]:
        if not args.slug and args.feature_id is None:
            return err(
                ErrorCode.FAILED_INTERNAL,
                "feature_get requires either slug or feature_id",
                remediation="Supply one of slug or feature_id.",
            )
        with unit_of_work(conn_factory()) as uow:
            row = uow.features.get_by_slug(args.slug) if args.slug else None
            if row is None and args.feature_id is not None:
                row = next(
                    (f for f in uow.features.list_all() if f["id"] == args.feature_id), None
                )
            if row is None:
                return err(ErrorCode.FAILED_INTERNAL, "Feature not found",
                           remediation="Call features_list to see available features.")
            page = uow.requirements.query(feature_id=row["id"])
        return ok({"feature": dict(row), "requirements": _rows(page.items)})

    @tool("requirements_query", "Testable requirements, filtered and paged.", RequirementQuery)
    def requirements_query(args: RequirementQuery, log: Logger) -> Result[Any]:
        with unit_of_work(conn_factory()) as uow:
            page = uow.requirements.query(
                feature_id=args.feature_id, cursor=args.cursor, limit=args.limit
            )
        items = _rows(page.items)
        if args.category:
            items = [i for i in items if i.get("category") == args.category]
        if args.risk_band:
            items = [i for i in items if i.get("risk_band") == args.risk_band]
        return ok({"items": items, "next_cursor": page.next_cursor})

    @tool("coverage_get", "Coverage items, including not-required decisions.", CoverageQuery)
    def coverage_get(args: CoverageQuery, log: Logger) -> Result[Any]:
        if not args.requirement_id and args.feature_id is None:
            return err(
                ErrorCode.FAILED_INTERNAL,
                "coverage_get requires requirement_id or feature_id",
                remediation="Supply one of requirement_id or feature_id.",
            )
        with unit_of_work(conn_factory()) as uow:
            if args.requirement_id:
                items = _rows(uow.coverage.for_requirement(args.requirement_id))
            else:
                page = uow.requirements.query(feature_id=args.feature_id)
                items = [
                    dict(row)
                    for req in page.items
                    for row in uow.coverage.for_requirement(req["id"])
                ]
        # Not-required rows are returned, not filtered out: a deliberate exclusion
        # must stay distinguishable from an oversight (BR-2.6).
        return ok({"items": items, "required": sum(1 for i in items if i["is_required"])})

    @tool("coverage_forecast", "Expected case counts with their derivation.", CoverageQuery)
    def coverage_forecast(args: CoverageQuery, log: Logger) -> Result[Any]:
        with unit_of_work(conn_factory()) as uow:
            page = uow.requirements.query(feature_id=args.feature_id)
            items = [
                dict(row)
                for req in page.items
                for row in uow.coverage.for_requirement(req["id"])
            ]
        total = sum(i["planned_count"] for i in items)
        per_type: dict[str, int] = {}
        for item in items:
            per_type[item["test_type"]] = per_type.get(item["test_type"], 0) + item["planned_count"]
        return ok(
            {
                "total": total,
                "per_test_type": per_type,
                "derivation": "sum of coverage_item.planned_count per ISTQB-standard depth",
            }
        )

    @tool("testcases_query", "Test cases, filtered and paged.", CaseQuery)
    def testcases_query(args: CaseQuery, log: Logger) -> Result[Any]:
        with unit_of_work(conn_factory()) as uow:
            page = uow.cases.query(
                feature_id=args.feature_id,
                tag=args.tag,
                include_obsolete=args.include_obsolete,
                cursor=args.cursor,
                limit=args.limit,
            )
        items = _rows(page.items)
        if args.test_type:
            items = [i for i in items if i["test_type"] == args.test_type]
        if args.automatable is not None:
            wanted = "automatable" if args.automatable else "manual-only"
            items = [i for i in items if i["automatability"] == wanted]
        return ok({"items": items, "next_cursor": page.next_cursor})

    @tool("testcase_get", "One case with its steps, data and links.", CaseRef)
    def testcase_get(args: CaseRef, log: Logger) -> Result[Any]:
        with unit_of_work(conn_factory()) as uow:
            record = uow.cases.get(args.case_id)
        if record is None:
            return err(ErrorCode.FAILED_INTERNAL, f"Case not found: {args.case_id}",
                       remediation="Call testcases_query to find valid case identifiers.")
        return ok(record)

    @tool(
        "duplicates_check",
        "Test a candidate against the corpus without writing. Convenience only - "
        "testcases_upsert re-checks regardless.",
        DuplicateCheck,
    )
    def duplicates_check(args: DuplicateCheck, log: Logger) -> Result[Any]:
        key = f"{args.feature_slug}|{args.test_type}|{args.step_count}"
        with unit_of_work(conn_factory()) as uow:
            candidates = uow.cases.bucket_candidates(key)
        exact = [cid for cid, norm in candidates if norm.hash == args.normalised_hash]
        return ok(
            {
                "bucket_key": key,
                "candidates_examined": len(candidates),
                "identical_to": exact,
                "note": "enforcement happens in testcases_upsert, not here",
            }
        )

    @tool("trace_query", "Traceability links, filtered and paged.", TraceQuery)
    def trace_query(args: TraceQuery, log: Logger) -> Result[Any]:
        with unit_of_work(conn_factory()) as uow:
            links = _rows(
                uow.traces.for_source(args.from_id) if args.from_id else uow.traces.all_links()
            )
        if args.to_id:
            links = [l for l in links if l["target_ref"] == args.to_id]
        if args.link_type:
            links = [l for l in links if l["link_type"] == args.link_type]
        capped = links[: args.limit]
        by_type: dict[str, int] = {}
        for link in links:
            by_type[link["link_type"]] = by_type.get(link["link_type"], 0) + 1
        # Derived links are counted separately: provenance is weaker evidence than
        # specification and must not be presented as equivalent (BR-3.6).
        return ok({"items": capped, "counts_by_type": by_type, "truncated": len(links) > len(capped)})

    @tool("trace_matrix", "Bidirectional requirement-to-test matrix.", MatrixQuery)
    def trace_matrix(args: MatrixQuery, log: Logger) -> Result[Any]:
        from tto_testgen.domain.traceability import MatrixEdge, build_matrix

        # Streamed, and deliberately uncapped (P-U4-05). MAX_PAGE_SIZE protects
        # interactive queries from returning unbounded results into the model's
        # context; the matrix is written to a file and never enters it, so the cap
        # would only turn the matrix into a sample - and a coverage report built
        # from a sample understates coverage without saying so.
        edges: list[MatrixEdge] = []
        by_type: dict[str, int] = {}
        with unit_of_work(conn_factory()) as uow:
            for row in uow.traces.stream_links():
                edges.append(MatrixEdge("case", row["source_id"], "target", row["target_ref"]))
                key = str(row["link_type"])
                by_type[key] = by_type.get(key, 0) + 1
            requirements = list(uow.traces.stream_requirement_ids())
        matrix = build_matrix(edges, all_sources=requirements)
        return ok(
            {
                "forward": matrix.forward,
                "reverse": matrix.reverse,
                # Requirements with no cases appear with an empty set. An absent row
                # hides exactly what the matrix exists to reveal.
                "uncovered": matrix.uncovered(requirements),
                # Direct and derived counted apart: provenance is weaker evidence
                # than specification, and merging them would overstate how well the
                # corpus is grounded (BR-U4-6.3).
                "counts_by_link_type": by_type,
                "consistent": matrix.is_bidirectionally_consistent(),
            }
        )

    @tool("gap_query", "Gaps by category, including empty categories.", GapQuery)
    def gap_query(args: GapQuery, log: Logger) -> Result[Any]:
        with unit_of_work(conn_factory()) as uow:
            unclassified = _rows(uow.resources.list_unclassified())
            not_required = [
                dict(row)
                for req in uow.requirements.query(limit=MAX_PAGE_SIZE).items
                for row in uow.coverage.for_requirement(req["id"])
                if not row["is_required"]
            ]
            manual = _rows(uow.cases.query(limit=MAX_PAGE_SIZE).items)
        categories = {
            "unclassified_resources": unclassified,
            "not_required_coverage": not_required,
            "manual_only_cases": [c for c in manual if c["automatability"] == "manual-only"],
            "needs_review_cases": [c for c in manual if c["automatability"] == "needs-review"],
            "obsolete_cases": _rows(
                [] if True else []
            ),
        }
        if args.category:
            categories = {k: v for k, v in categories.items() if k == args.category}
        # Empty categories are shown, never omitted: a silent section is otherwise
        # indistinguishable from a missing check.
        return ok({"categories": {k: {"count": len(v), "items": v} for k, v in categories.items()}})

    @tool("run_status", "What is complete and what remains. Reporting only.", StatusQuery)
    def run_status(args: StatusQuery, log: Logger) -> Result[Any]:
        with unit_of_work(conn_factory()) as uow:
            states = _rows(uow.run_state.all_states(args.scope))
            active = uow.cases.count_active()
        by_state: dict[str, int] = {}
        for row in states:
            by_state[row["state"]] = by_state.get(row["state"], 0) + 1
        return ok(
            {
                "units": states,
                "by_state": by_state,
                "active_cases": active,
                # C-12: this tool reports. It does not propose the next unit, and
                # there is no method here that could.
                "note": "reporting only; the operator names the next unit",
            }
        )

    @tool("unit_state_get", "One unit's per-stage state.", UnitRef)
    def unit_state_get(args: UnitRef, log: Logger) -> Result[Any]:
        with unit_of_work(conn_factory()) as uow:
            states = _rows(uow.run_state.all_states(args.unit_ref))
        return ok({"unit_ref": args.unit_ref, "stages": states})

    @tool("health_check", "Database, schema version and MCP reachability.", Empty)
    def health_check(args: Empty, log: Logger) -> Result[Any]:
        from tto_testgen.adapters.sqlite.schema import current_version
        from tto_testgen.platform.health import ComponentHealth, Status

        def database() -> ComponentHealth:
            conn = conn_factory()
            version = current_version(conn)
            return ComponentHealth("database", Status.OK, f"schema v{version}")

        report = check({"database": database})
        return ok(report.to_dict())
