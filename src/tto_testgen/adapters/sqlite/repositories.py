"""A2 SqliteRepositories and the Unit of Work.

Repositories never open a transaction. They are reachable only through a
`unit_of_work()`, which commits on clean exit and rolls back on any exception. That
makes "services own transaction boundaries" a structural fact: a repository obtained
outside a unit of work has no connection to write through.

Requirements: NFR-SEC-04, NFR-PRF-01 to -03, NFR-REL-01, FR-DLT-05.
Patterns: P-RES-01, P-SCL-01, P-PRF-01.
"""

from __future__ import annotations

import base64
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

from tto_testgen.adapters.sqlite import queries as q
from tto_testgen.domain.model import (
    Artefact,
    AutomatedTest,
    ChangeEvent,
    CoverageItem,
    Feature,
    LinkType,
    Resource,
    Run,
    StageName,
    TestCase,
    TestData,
    TestStep,
    TestType,
    TestableRequirement,
    TraceLink,
    UnitState,
    UnitStateRecord,
    utc_now,
)
from tto_testgen.domain.similarity import NormalisedCase
from tto_testgen.ports.repositories import Page

#: P-SCL-01. The cap is the enforcement of NFR-SCL-04, not the filter: a tool that
#: can return 10,000 rows will eventually be asked to.
MAX_PAGE_SIZE = 200


def _encode_cursor(last_id: Any) -> str:
    return base64.urlsafe_b64encode(str(last_id).encode()).decode()


def _decode_cursor(cursor: str | None, default: Any) -> Any:
    if not cursor:
        return default
    try:
        return base64.urlsafe_b64decode(cursor.encode()).decode()
    except Exception:
        return default


def _json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _unjson(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class _Base:
    def __init__(self, conn: sqlite3.Connection, run_id: int | None = None,
                 actor: str = "toolchain") -> None:
        self._conn = conn
        self._run_id = run_id
        self._actor = actor

    def _page(self, sql: str, params: dict, limit: int, key: str = "id") -> Page:
        capped = min(max(1, limit), MAX_PAGE_SIZE)
        rows = self._conn.execute(sql, {**params, "limit": capped + 1}).fetchall()
        has_more = len(rows) > capped
        rows = rows[:capped]
        cursor = _encode_cursor(rows[-1][key]) if has_more and rows else None
        return Page(items=rows, next_cursor=cursor)


class SqliteResourceRepository(_Base):
    def upsert(self, resource: Resource) -> Resource:
        self._conn.execute(
            q.RESOURCE_UPSERT,
            {
                "raw_ref": resource.raw_ref,
                "type": resource.type.value,
                "inferred_from": resource.inferred_from,
                "status": resource.status,
                "failure_reason": resource.failure_reason,
                "first_seen_at": resource.first_seen_at,
            },
        )
        return resource

    def list_all(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.RESOURCE_ALL).fetchall()

    def list_unclassified(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.RESOURCE_UNCLASSIFIED).fetchall()

    def id_for(self, raw_ref: str) -> int | None:
        """The surrogate id after an upsert.

        `upsert` returns the domain object it was given, which carries no id -
        SQLite assigns that. Artefacts reference the resource by id, so the caller
        needs a way to read it back.
        """
        row = self._conn.execute(q.RESOURCE_ID_FOR_REF, {"raw_ref": raw_ref}).fetchone()
        return int(row["id"]) if row else None


class SqliteArtefactRepository(_Base):
    def upsert(self, artefact: Artefact) -> Artefact:
        self._conn.execute(
            q.ARTEFACT_UPSERT,
            {
                "resource_id": artefact.resource_id,
                "kind": artefact.kind,
                "source_identifier": artefact.source_identifier,
                "content": artefact.content,
                "content_hash": artefact.content_hash,
                "metadata": _json(artefact.metadata),
                "detail_level": artefact.detail_level,
                "ingested_at": artefact.ingested_at,
                "run_id": artefact.run_id or self._run_id,
            },
        )
        return artefact

    def get_by_hash(self, content_hash: str) -> sqlite3.Row | None:
        return self._conn.execute(q.ARTEFACT_BY_HASH, {"content_hash": content_hash}).fetchone()

    def query(self, *, kind: str | None = None, cursor: str | None = None,
              limit: int = MAX_PAGE_SIZE) -> Page:
        return self._page(
            q.ARTEFACT_PAGE, {"kind": kind, "after": int(_decode_cursor(cursor, 0))}, limit
        )

    def known_jira_keys(self) -> frozenset[str]:
        """The set an invented key cannot join. US-TRC-01 AC4 depends on this."""
        return frozenset(
            row[0] for row in self._conn.execute(q.KNOWN_JIRA_KEYS).fetchall()
        )


class SqliteFeatureRepository(_Base):
    def upsert(self, feature: Feature) -> Feature:
        self._conn.execute(
            q.FEATURE_UPSERT,
            {
                "slug": feature.slug,
                "name": feature.name,
                "parent_id": feature.parent_id,
                "description": feature.description,
                "risk_band": feature.risk_band.value if feature.risk_band else None,
            },
        )
        return feature

    def get_by_slug(self, slug: str) -> sqlite3.Row | None:
        return self._conn.execute(q.FEATURE_BY_SLUG, {"slug": slug}).fetchone()

    def list_all(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.FEATURE_ALL).fetchall()

    # --- the rest of the application model ------------------------------
    # U1 created these tables and left them without a write path, because no U1
    # story needed one. U2 is the first unit that populates them.

    def add_journey(self, name: str, steps: list[dict[str, Any]]) -> None:
        self._conn.execute(q.JOURNEY_INSERT, {"name": name, "steps": _json(steps)})

    def list_journeys(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.JOURNEY_ALL).fetchall()

    def add_business_rule(
        self, feature_id: int, rule_kind: str, condition: str, effect: str,
        *, is_documented: bool = True, contradicts_id: int | None = None,
    ) -> int:
        cursor = self._conn.execute(q.RULE_INSERT, {
            "feature_id": feature_id, "rule_kind": rule_kind, "condition": condition,
            "effect": effect, "is_documented": int(is_documented),
            "contradicts_id": contradicts_id,
        })
        return int(cursor.lastrowid)

    def rules_for_feature(self, feature_id: int) -> list[sqlite3.Row]:
        return self._conn.execute(q.RULE_FOR_FEATURE, {"feature_id": feature_id}).fetchall()

    def list_rules(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.RULE_ALL).fetchall()

    def add_endpoint(self, endpoint: dict[str, Any]) -> None:
        self._conn.execute(q.ENDPOINT_UPSERT, {
            "feature_id": endpoint.get("feature_id"),
            "method": endpoint["method"], "route": endpoint["route"],
            "file_path": endpoint["file_path"], "line": endpoint["line"],
            "symbol": endpoint.get("symbol", ""),
            "request_shape": _json(endpoint.get("request_shape")),
            "response_shapes": _json(endpoint.get("response_shapes")),
            "status_codes": _json(list(endpoint.get("status_codes", []))),
            "auth_requirement": endpoint.get("auth_requirement", "unknown"),
            "shape_source": endpoint.get("shape_source", "inferred"),
        })

    def list_endpoints(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.ENDPOINT_ALL).fetchall()

    def add_screen(self, screen: dict[str, Any]) -> int:
        cursor = self._conn.execute(q.SCREEN_INSERT, {
            "feature_id": screen.get("feature_id"), "name": screen["name"],
            "state": screen.get("state", "default"), "route": screen.get("route"),
            "source": screen.get("source", "figma"),
            "discrepancy_id": screen.get("discrepancy_id"),
        })
        return int(cursor.lastrowid)

    def list_screens(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.SCREEN_ALL).fetchall()

    def add_element(self, screen_id: int, element: dict[str, Any]) -> None:
        self._conn.execute(q.ELEMENT_INSERT, {
            "screen_id": screen_id, "role": element.get("role"),
            "accessible_name": element.get("accessible_name"),
            "test_id": element.get("test_id"),
            "locator_chain": _json(element.get("locator_chain", [])),
            "is_fragile": int(element.get("is_fragile", False)),
            # is_verified is true only for locators confirmed against the running
            # application. Unreachable environment means unverified, never assumed.
            "is_verified": int(element.get("is_verified", False)),
        })

    def elements_for_feature(self, feature_id: int) -> list[sqlite3.Row]:
        return self._conn.execute(
            q.ELEMENTS_FOR_FEATURE, {"feature_id": feature_id}
        ).fetchall()

    def elements_for_screen(self, screen_id: int) -> list[sqlite3.Row]:
        return self._conn.execute(q.ELEMENT_FOR_SCREEN, {"screen_id": screen_id}).fetchall()


class SqliteDiscrepancyRepository(_Base):
    """New in U2. Symmetric by construction: both claims, both sources, no verdict."""

    def add(self, discrepancy: dict[str, Any], run_id: int | None = None) -> None:
        self._conn.execute(q.DISCREPANCY_INSERT, {**discrepancy, "run_id": run_id})

    def list_all(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.DISCREPANCY_ALL).fetchall()

    def by_kind(self, kind: str) -> list[sqlite3.Row]:
        return self._conn.execute(q.DISCREPANCY_BY_KIND, {"kind": kind}).fetchall()


class SqliteGapRepository(_Base):
    """New in U3.

    A gap is persisted rather than reported, because a gap held only in a run report
    is lost when the run ends - and the operator's question, "what is still
    untraceable?", arrives weeks later.
    """

    def add(self, gap: dict[str, Any], run_id: int | None = None) -> int:
        cursor = self._conn.execute(q.GAP_INSERT, {
            "category": gap["category"], "subject": gap["subject"],
            "source_ref": gap.get("source_ref", ""),
            "attempted": _json(gap.get("attempted", [])),
            "feature_slug": gap.get("feature_slug"),
            "detail": gap.get("detail", ""),
            "detected_at": gap.get("detected_at") or utc_now(),
            "run_id": run_id,
        })
        return int(cursor.lastrowid)

    def add_unless_open(self, gap: dict[str, Any], run_id: int | None = None) -> int | None:
        """Idempotent within a category and subject.

        A re-run that finds the same behaviour untraceable should not accumulate a
        duplicate gap per run - the report would then measure how often the pipeline
        ran rather than how much is untraceable.
        """
        existing = self._conn.execute(
            q.GAP_FIND, {"category": gap["category"], "subject": gap["subject"]}
        ).fetchone()
        return None if existing else self.add(gap, run_id)

    def open_gaps(self, category: str | None = None,
                  feature_slug: str | None = None) -> list[sqlite3.Row]:
        return self._conn.execute(
            q.GAP_OPEN, {"category": category, "feature_slug": feature_slug}
        ).fetchall()

    def counts_by_category(self) -> dict[str, int]:
        return {r["category"]: r["n"] for r in self._conn.execute(q.GAP_BY_CATEGORY).fetchall()}

    def close(self, gap_id: int, closed_by: str) -> None:
        self._conn.execute(
            q.GAP_CLOSE, {"id": gap_id, "closed_at": utc_now(), "closed_by": closed_by}
        )


class SqliteReductionRepository(_Base):
    def add(self, reduction: dict[str, Any]) -> int:
        cursor = self._conn.execute(q.REDUCTION_INSERT, {
            **reduction,
            "decided_at": reduction.get("decided_at") or utc_now(),
            "was_override": int(reduction.get("was_override", False)),
        })
        return int(cursor.lastrowid)

    def for_feature(self, feature_id: int) -> list[sqlite3.Row]:
        return self._conn.execute(
            q.REDUCTION_FOR_FEATURE, {"feature_id": feature_id}
        ).fetchall()

    def list_all(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.REDUCTION_ALL).fetchall()


class SqliteRequirementRepository(_Base):
    def upsert(self, requirement: TestableRequirement) -> TestableRequirement:
        self._conn.execute(
            q.REQUIREMENT_UPSERT,
            {
                "id": requirement.id,
                "feature_id": requirement.feature_id,
                "statement": requirement.statement,
                "classification": requirement.classification,
                "category": requirement.category,
                "risk_score": requirement.risk_score,
                "risk_band": requirement.risk_band.value if requirement.risk_band else None,
                "risk_factors": _json(requirement.risk_factors),
                "risk_is_partial": int(requirement.risk_is_partial),
                "source_artefact_ids": _json(requirement.source_artefact_ids),
            },
        )
        return requirement

    def get(self, requirement_id: str) -> sqlite3.Row | None:
        return self._conn.execute(q.REQUIREMENT_GET, {"id": requirement_id}).fetchone()

    def query(self, *, feature_id: int | None = None, cursor: str | None = None,
              limit: int = MAX_PAGE_SIZE) -> Page:
        return self._page(
            q.REQUIREMENT_PAGE,
            {"feature_id": feature_id, "after": _decode_cursor(cursor, "")},
            limit,
        )


class SqliteCoverageRepository(_Base):
    def upsert_many(self, items: list[CoverageItem]) -> int:
        for item in items:
            self._conn.execute(
                q.COVERAGE_UPSERT,
                {
                    "id": item.id,
                    "requirement_id": item.requirement_id,
                    "test_type": item.test_type.value,
                    "technique": item.technique.value,
                    "planned_count": item.planned_count,
                    "rationale": item.rationale,
                    "is_required": int(item.is_required),
                    "reduction_applied": item.reduction_applied,
                    "model_version": item.model_version,
                },
            )
        return len(items)

    def for_requirement(self, requirement_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            q.COVERAGE_FOR_REQUIREMENT, {"requirement_id": requirement_id}
        ).fetchall()

    def get(self, coverage_item_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM coverage_item WHERE id = :id", {"id": coverage_item_id}
        ).fetchone()

    def volume_for_feature(self, feature_id: int) -> list[sqlite3.Row]:
        """Planned against generated, in one pass.

        Aggregated in SQL rather than by counting in Python: at 6,000 cases the
        Python form reads the whole corpus to produce 150 rows (U4-NFR-PRF-05).
        """
        return self._conn.execute(
            q.VOLUME_BY_COVERAGE_ITEM, {"feature_id": feature_id}
        ).fetchall()

    def model_version(self, feature_id: int) -> str | None:
        row = self._conn.execute(q.COVERAGE_MODEL_VERSION, {"feature_id": feature_id}).fetchone()
        return row[0] if row else None

    def latest_version(self, feature_id: int) -> tuple[int, str | None] | None:
        """The current model version and the hash the approval binds to."""
        row = self._conn.execute(
            q.COVERAGE_LATEST_VERSION, {"feature_id": feature_id}
        ).fetchone()
        return (int(row["version"]), row["content_hash"]) if row else None

    def for_feature(self, feature_id: int) -> list[sqlite3.Row]:
        return self._conn.execute(q.COVERAGE_FOR_FEATURE, {"feature_id": feature_id}).fetchall()

    def set_version(self, item_ids: list[str], version: int, content_hash: str) -> None:
        for item_id in item_ids:
            self._conn.execute(
                q.COVERAGE_SET_VERSION,
                {"id": item_id, "version": version, "content_hash": content_hash},
            )

    def content_hash_for(self, feature_id: int) -> str | None:
        """Hash the approved coverage content.

        Approval binds to this. Modify the model and the hash changes, so a prior
        approval no longer applies (US-COV-04 AC3).
        """
        from tto_testgen.domain.model import content_hash

        rows = self._conn.execute(
            q.COVERAGE_CONTENT_FOR_FEATURE, {"feature_id": feature_id}
        ).fetchall()
        if not rows:
            return None
        payload = _json([tuple(row) for row in rows])
        return content_hash(payload)


class SqliteTestCaseRepository(_Base):
    def upsert_many(self, cases: list[TestCase], feature_slug: str) -> int:
        """P-U4-02. One transaction, executemany per table, sentinel last.

        A 200-case batch is roughly 1,600 rows. Per-row `execute` pays Python call
        overhead 1,600 times and re-prepares each statement; `executemany` prepares
        once and binds inside SQLite.

        **The table order is load-bearing, not stylistic.** L1 sets
        `foreign_keys = ON` and does not defer them, so a step inserted before its
        case fails outright. The order below is the topological order of the four
        foreign keys, and changing it breaks the insert rather than merely slowing
        it.

        The integrity sentinel goes last because the triggers it fires check for
        the presence of steps and links. Written first it would assert a state that
        does not yet exist.
        """
        from tto_testgen.domain.similarity import bucket_key, normalise

        now = utc_now()
        case_rows, step_rows, data_rows, link_rows, sentinels = [], [], [], [], []

        for case in cases:
            normalised = normalise(case)
            case_rows.append({
                "id": case.id,
                "feature_id": case.feature_id,
                "coverage_item_id": case.coverage_item_id,
                "title": case.title,
                "test_type": case.test_type.value,
                "priority": case.priority,
                "preconditions": case.preconditions,
                "expected_result": case.expected_result,
                "automatability": case.automatability.value,
                "automatability_reason": case.automatability_reason,
                "automatability_overridden_by": case.automatability_overridden_by,
                "tags": _json(case.tags),
                "normalised_hash": normalised.hash,
                "bucket_key": bucket_key(case, feature_slug),
                "run_id": self._run_id,
                "now": now,
                "actor": self._actor,
            })
            step_rows += [
                {"case_id": case.id, "ordinal": s.ordinal, "action": s.action,
                 "expected": s.expected}
                for s in case.steps
            ]
            data_rows += [
                {"case_id": case.id, "step_ordinal": d.step_ordinal,
                 "field_name": d.field_name, "value": d.value,
                 "equivalence_class": d.equivalence_class,
                 "boundary_relation": d.boundary_relation}
                for d in case.test_data
            ]
            link_rows += [
                {"source_kind": "test_case", "source_id": case.id,
                 "target_ref": l.target_ref, "link_type": l.link_type.value,
                 "evidence": l.evidence, "selection_basis": l.selection_basis,
                 "alternatives": _json(l.alternatives),
                 "resolved_jira_key": l.resolved_jira_key}
                for l in case.trace_links
            ]
            sentinels.append({"case_id": case.id})

        if case_rows:
            self._conn.executemany(q.CASE_INSERT, case_rows)
        if step_rows:
            self._conn.executemany(q.STEP_INSERT, step_rows)
        if data_rows:
            self._conn.executemany(q.DATA_INSERT, data_rows)
        if link_rows:
            self._conn.executemany(q.TRACE_INSERT, link_rows)
        if sentinels:
            self._conn.executemany(q.INTEGRITY_CHECK, sentinels)
            self._conn.executemany(q.INTEGRITY_CLEAR, sentinels)
        return len(cases)

    def get(self, case_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(q.CASE_GET, {"id": case_id}).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["steps"] = [dict(r) for r in
                           self._conn.execute(q.STEPS_FOR_CASE, {"case_id": case_id}).fetchall()]
        record["test_data"] = [dict(r) for r in
                               self._conn.execute(q.DATA_FOR_CASE, {"case_id": case_id}).fetchall()]
        record["trace_links"] = [dict(r) for r in
                                 self._conn.execute(q.TRACE_FOR_SOURCE,
                                                    {"source_id": case_id}).fetchall()]
        return record

    def query(self, *, feature_id: int | None = None, tag: str | None = None,
              include_obsolete: bool = False, cursor: str | None = None,
              limit: int = MAX_PAGE_SIZE) -> Page:
        return self._page(
            q.CASE_PAGE,
            {
                "feature_id": feature_id,
                "include_obsolete": int(include_obsolete),
                "tag": tag,
                "tag_pattern": f'%"{tag}"%' if tag else None,
                "after": _decode_cursor(cursor, ""),
            },
            limit,
        )

    def bucket_candidates(self, bucket_key: str) -> list[tuple[str, NormalisedCase]]:
        """Indexed candidate selection. Never a full scan (NFR-PRF-03)."""
        rows = self._conn.execute(q.CASE_BUCKET_CANDIDATES, {"bucket_key": bucket_key}).fetchall()
        classes: dict[str, set[str]] = {}
        for row in self._conn.execute(q.CASE_CLASSES, {"bucket_key": bucket_key}).fetchall():
            classes.setdefault(row["case_id"], set()).add(row["equivalence_class"])
        out: list[tuple[str, NormalisedCase]] = []
        for row in rows:
            out.append(
                (
                    row["id"],
                    NormalisedCase(
                        text="",
                        hash=row["normalised_hash"] or "",
                        classes=frozenset(classes.get(row["id"], set())),
                    ),
                )
            )
        return out

    def for_feature_slug(self, feature_slug: str) -> list[dict[str, Any]]:
        """Whole cases for one feature, assembled for rendering."""
        rows = self._conn.execute(
            q.CASES_FOR_FEATURE_SLUG, {"feature_slug": feature_slug}
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            case_id = record["id"]
            record["steps"] = [
                dict(r) for r in
                self._conn.execute(q.STEPS_FOR_CASE, {"case_id": case_id}).fetchall()
            ]
            record["test_data"] = [
                dict(r) for r in
                self._conn.execute(q.DATA_FOR_CASE, {"case_id": case_id}).fetchall()
            ]
            record["trace_links"] = [
                dict(r) for r in
                self._conn.execute(q.TRACE_FOR_SOURCE, {"source_id": case_id}).fetchall()
            ]
            out.append(record)
        return out

    def volume_by_feature(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.VOLUME_BY_FEATURE).fetchall()

    def existing_identifiers(self) -> list[str]:
        return [row[0] for row in self._conn.execute(q.CASE_IDENTIFIERS).fetchall()]

    def mark_obsolete(self, case_id: str, reason: str, change_event_id: int) -> None:
        """Soft delete. Nothing is ever hard-deleted (FR-DLT-05)."""
        self._conn.execute(
            q.CASE_MARK_OBSOLETE,
            {
                "id": case_id,
                "reason": reason,
                "change_event_id": change_event_id,
                "now": utc_now(),
                "actor": self._actor,
            },
        )

    def count_active(self) -> int:
        return int(self._conn.execute(q.CASE_COUNT_ACTIVE).fetchone()[0])


class SqliteTraceRepository(_Base):
    def add_many(self, links: list[TraceLink]) -> int:
        for link in links:
            self._conn.execute(
                q.TRACE_INSERT,
                {
                    "source_kind": link.source_kind,
                    "source_id": link.source_id,
                    "target_ref": link.target_ref,
                    "link_type": link.link_type.value,
                    "evidence": link.evidence,
                    "selection_basis": link.selection_basis,
                    "alternatives": _json(link.alternatives),
                    "resolved_jira_key": link.resolved_jira_key,
                },
            )
        return len(links)

    def for_source(self, source_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(q.TRACE_FOR_SOURCE, {"source_id": source_id}).fetchall()

    def for_target(self, target_ref: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            q.TRACE_FOR_TARGET, {"target_ref": target_ref}
        ).fetchall()

    def all_links(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.TRACE_ALL).fetchall()

    def stream_links(self) -> Iterator[sqlite3.Row]:
        """Yield from the cursor rather than materialising the result set.

        P-U4-05. At 6,000 cases the matrix draws on roughly 9,000 links; holding
        them is survivable and makes memory a function of corpus size, which is the
        property U4-NFR-SCL-05 exists to prevent.
        """
        cursor = self._conn.execute(q.TRACE_STREAM)
        while True:
            batch = cursor.fetchmany(500)
            if not batch:
                return
            yield from batch

    def stream_requirement_ids(self) -> Iterator[str]:
        cursor = self._conn.execute(q.REQUIREMENT_IDS_STREAM)
        while True:
            batch = cursor.fetchmany(500)
            if not batch:
                return
            for row in batch:
                yield row["id"]


class SqliteEmittedViewRepository(_Base):
    """The record of what was emitted, keyed by path."""

    def get(self, path: str) -> sqlite3.Row | None:
        return self._conn.execute(q.VIEW_GET, {"path": path}).fetchone()

    def upsert(self, path: str, feature_slug: str, content_hash: str,
               case_count: int, kind: str = "view") -> None:
        self._conn.execute(
            q.VIEW_UPSERT,
            {
                "path": path,
                "feature_slug": feature_slug,
                "content_hash": content_hash,
                "emitted_at": utc_now(),
                "case_count": case_count,
                "kind": kind,
            },
        )

    def for_feature(self, feature_slug: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            q.VIEW_FOR_FEATURE, {"feature_slug": feature_slug}
        ).fetchall()


class SqliteAutomationRepository(_Base):
    def upsert(self, test: AutomatedTest) -> AutomatedTest:
        self._conn.execute(
            q.AUTOMATION_UPSERT,
            {
                "id": test.id,
                "case_id": test.case_id,
                "spec_path": test.spec_path,
                "test_name": test.test_name,
                "page_object_refs": _json(test.page_object_refs),
                "input_hash": test.input_hash,
                "output_hash": test.output_hash,
                "is_at_risk": int(test.is_at_risk),
                "at_risk_reason": test.at_risk_reason,
            },
        )
        return test

    def for_case(self, case_id: str) -> sqlite3.Row | None:
        return self._conn.execute(q.AUTOMATION_FOR_CASE, {"case_id": case_id}).fetchone()

    def for_feature_slug(self, feature_slug: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            q.AUTOMATION_FOR_FEATURE, {"feature_slug": feature_slug}
        ).fetchall()

    def clear_for_feature(self, feature_slug: str) -> int:
        """Remove a feature's rows before re-recording them.

        An emission is authoritative for the feature it covers: a case that stopped
        being automatable must stop having an automated_test row, or the automation
        report would keep counting a spec nobody generates any more.
        """
        cursor = self._conn.execute(
            q.AUTOMATION_DELETE_FOR_FEATURE, {"feature_slug": feature_slug}
        )
        return cursor.rowcount

    def list_all(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.AUTOMATION_ALL).fetchall()

    def counts(self) -> sqlite3.Row:
        return self._conn.execute(q.AUTOMATION_COUNTS).fetchone()

    def list_at_risk(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.AUTOMATION_AT_RISK).fetchall()


class SqliteRunStateRepository(_Base):
    def start_run(self, run: Run) -> int:
        cursor = self._conn.execute(
            q.RUN_INSERT,
            {
                "correlation_id": run.correlation_id,
                "kind": run.kind,
                "operator": run.operator,
                "started_at": run.started_at,
                "business_rules": _json(run.business_rules),
            },
        )
        return int(cursor.lastrowid)

    def get_state(self, unit_ref: str, stage: StageName) -> sqlite3.Row | None:
        return self._conn.execute(
            q.STATE_GET, {"unit_ref": unit_ref, "stage": stage.value}
        ).fetchone()

    def set_state(self, record: UnitStateRecord) -> UnitStateRecord:
        self._conn.execute(
            q.STATE_UPSERT,
            {
                "unit_ref": record.unit_ref,
                "stage": record.stage.value,
                "state": record.state.value,
                "lease_id": record.lease_id,
                "approved_by": record.approved_by,
                "approved_at": record.approved_at,
                "approved_content_hash": record.approved_content_hash,
                "failure_reason": record.failure_reason,
                "metrics": _json(record.metrics),
            },
        )
        return record

    def current_run_id(self) -> int:
        row = self._conn.execute("SELECT id FROM run ORDER BY id DESC LIMIT 1").fetchone()
        return int(row["id"]) if row else 0

    def last_completed_run(self) -> sqlite3.Row | None:
        """The baseline is the last run that actually finished.

        A run that failed partway leaves `ended_at` null and is not eligible, so the
        next delta compares against the last head the system can vouch for having
        fully ingested (BR-U8-4.4).
        """
        return self._conn.execute(q.RUN_LAST_COMPLETED).fetchone()

    def record_baseline(self, run_id: int, head_commits: dict[str, str],
                        jira_watermark: str | None) -> None:
        self._conn.execute(q.RUN_RECORD_BASELINE, {
            "id": run_id,
            "head_commits": _json(head_commits),
            "jira_watermark": jira_watermark,
        })

    def complete_run(self, run_id: int) -> None:
        self._conn.execute(q.RUN_COMPLETE, {"id": run_id, "ended_at": utc_now()})

    def all_states(self, unit_ref: str | None = None) -> list[sqlite3.Row]:
        return self._conn.execute(q.STATE_ALL, {"unit_ref": unit_ref}).fetchall()


class SqliteReportRepository(_Base):
    """Read-only aggregations for U8. Every figure here is a query result: the model
    composes no number (FR-RPT-05)."""

    def coverage_by_feature(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.REPORT_COVERAGE_BY_FEATURE).fetchall()

    def coverage_by_test_type(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.REPORT_COVERAGE_BY_TEST_TYPE).fetchall()

    def open_gaps(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.REPORT_GAPS).fetchall()

    def automation(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.REPORT_AUTOMATION).fetchall()

    def deferred(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.REPORT_DEFERRED).fetchall()

    def retired(self) -> list[sqlite3.Row]:
        return self._conn.execute(q.REPORT_RETIRED).fetchall()


class SqliteChangeEventRepository(_Base):
    def add(self, event: ChangeEvent) -> int:
        cursor = self._conn.execute(
            q.CHANGE_INSERT,
            {
                "run_id": event.run_id,
                "source": event.source,
                "ref_from": event.ref_from,
                "ref_to": event.ref_to,
                "changed_refs": _json(event.changed_refs),
                "jira_keys": _json(event.jira_keys),
                "is_unmapped": int(event.is_unmapped),
                "impact_scale": event.impact_scale,
            },
        )
        return int(cursor.lastrowid)

    def latest_for(self, source: str) -> sqlite3.Row | None:
        return self._conn.execute(q.CHANGE_LATEST, {"source": source}).fetchone()


@dataclass(slots=True)
class SqliteUnitOfWork:
    """The transaction boundary. P-RES-01."""

    conn: sqlite3.Connection
    run_id: int | None = None
    actor: str = "toolchain"
    resources: SqliteResourceRepository = None  # type: ignore[assignment]
    artefacts: SqliteArtefactRepository = None  # type: ignore[assignment]
    features: SqliteFeatureRepository = None  # type: ignore[assignment]
    requirements: SqliteRequirementRepository = None  # type: ignore[assignment]
    coverage: SqliteCoverageRepository = None  # type: ignore[assignment]
    cases: SqliteTestCaseRepository = None  # type: ignore[assignment]
    traces: SqliteTraceRepository = None  # type: ignore[assignment]
    views: SqliteEmittedViewRepository = None  # type: ignore[assignment]
    automation: SqliteAutomationRepository = None  # type: ignore[assignment]
    run_state: SqliteRunStateRepository = None  # type: ignore[assignment]
    changes: SqliteChangeEventRepository = None  # type: ignore[assignment]
    discrepancies: SqliteDiscrepancyRepository = None  # type: ignore[assignment]
    gaps: SqliteGapRepository = None  # type: ignore[assignment]
    reductions: SqliteReductionRepository = None  # type: ignore[assignment]
    reports: SqliteReportRepository = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        args = (self.conn, self.run_id, self.actor)
        self.resources = SqliteResourceRepository(*args)
        self.artefacts = SqliteArtefactRepository(*args)
        self.features = SqliteFeatureRepository(*args)
        self.requirements = SqliteRequirementRepository(*args)
        self.coverage = SqliteCoverageRepository(*args)
        self.cases = SqliteTestCaseRepository(*args)
        self.traces = SqliteTraceRepository(*args)
        self.views = SqliteEmittedViewRepository(*args)
        self.automation = SqliteAutomationRepository(*args)
        self.run_state = SqliteRunStateRepository(*args)
        self.changes = SqliteChangeEventRepository(*args)
        self.discrepancies = SqliteDiscrepancyRepository(*args)
        self.gaps = SqliteGapRepository(*args)
        self.reductions = SqliteReductionRepository(*args)
        self.reports = SqliteReportRepository(*args)


@contextmanager
def unit_of_work(
    conn: sqlite3.Connection, *, run_id: int | None = None, actor: str = "toolchain"
) -> Iterator[SqliteUnitOfWork]:
    """Open a transaction, yield bound repositories, commit or roll back.

    A nested call joins the outer transaction rather than opening a savepoint.
    Services never call other services (except the read-only gate check), so
    nesting should not arise - but if it ever does, joining keeps the atomicity
    guarantee intact rather than allowing a partial inner commit.
    """
    already_open = bool(conn.in_transaction)
    if not already_open:
        conn.execute("BEGIN")
    uow = SqliteUnitOfWork(conn=conn, run_id=run_id, actor=actor)
    try:
        yield uow
    except Exception:
        if not already_open:
            conn.execute("ROLLBACK")
        raise
    else:
        if not already_open:
            conn.execute("COMMIT")
