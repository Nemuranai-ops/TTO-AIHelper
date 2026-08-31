"""In-memory repositories satisfying P1.

These are the contract U2-U8 develop against before real adapters exist. They
enforce the same invariants the SQLite constraints do - a case with no steps or no
Jira key is refused here too - because a fake that accepts what production rejects
teaches the wrong lesson and hides the bug until integration.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from tto_testgen.domain.model import (
    Artefact,
    AutomatedTest,
    ChangeEvent,
    CoverageItem,
    Feature,
    Resource,
    Run,
    StageName,
    TestCase,
    TestableRequirement,
    TraceLink,
    UnitStateRecord,
)
from tto_testgen.domain.similarity import NormalisedCase, bucket_key, normalise
from tto_testgen.ports.repositories import Page

MAX_PAGE_SIZE = 200


def _page(items: list[Any], cursor: str | None, limit: int, key) -> Page:
    capped = min(max(1, limit), MAX_PAGE_SIZE)
    start = 0
    if cursor:
        after = base64.urlsafe_b64decode(cursor.encode()).decode()
        start = next((i + 1 for i, item in enumerate(items) if str(key(item)) == after), 0)
    window = items[start : start + capped]
    has_more = start + capped < len(items)
    next_cursor = (
        base64.urlsafe_b64encode(str(key(window[-1])).encode()).decode()
        if has_more and window
        else None
    )
    return Page(items=window, next_cursor=next_cursor)


@dataclass(slots=True)
class FakeResourceRepository:
    store: dict[str, Resource] = field(default_factory=dict)

    def upsert(self, resource: Resource) -> Resource:
        self.store[resource.raw_ref] = resource
        return resource

    def list_all(self) -> list[Resource]:
        return list(self.store.values())

    def list_unclassified(self) -> list[Resource]:
        return [r for r in self.store.values() if r.type.value == "unclassified"]

    def id_for(self, raw_ref: str) -> int | None:
        if raw_ref not in self.store:
            return None
        return list(self.store).index(raw_ref) + 1


@dataclass(slots=True)
class FakeArtefactRepository:
    store: list[Artefact] = field(default_factory=list)

    def upsert(self, artefact: Artefact) -> Artefact:
        if not any(
            a.resource_id == artefact.resource_id
            and a.source_identifier == artefact.source_identifier
            and a.content_hash == artefact.content_hash
            for a in self.store
        ):
            self.store.append(artefact)
        return artefact

    def get_by_hash(self, content_hash: str) -> Artefact | None:
        return next((a for a in self.store if a.content_hash == content_hash), None)

    def query(self, *, kind: str | None = None, cursor: str | None = None,
              limit: int = MAX_PAGE_SIZE) -> Page:
        items = [a for a in self.store if kind is None or a.kind == kind]
        return _page(items, cursor, limit, key=lambda a: a.source_identifier)

    def known_jira_keys(self) -> frozenset[str]:
        return frozenset(
            a.source_identifier for a in self.store if a.kind == "jira-issue"
        )


@dataclass(slots=True)
class FakeFeatureRepository:
    store: dict[str, Feature] = field(default_factory=dict)

    def upsert(self, feature: Feature) -> Feature:
        self.store[feature.slug] = feature
        return feature

    def get_by_slug(self, slug: str) -> Feature | None:
        return self.store.get(slug)

    def list_all(self) -> list[Feature]:
        return list(self.store.values())


@dataclass(slots=True)
class FakeRequirementRepository:
    store: dict[str, TestableRequirement] = field(default_factory=dict)

    def upsert(self, requirement: TestableRequirement) -> TestableRequirement:
        self.store[requirement.id] = requirement
        return requirement

    def get(self, requirement_id: str) -> TestableRequirement | None:
        return self.store.get(requirement_id)

    def query(self, *, feature_id: int | None = None, cursor: str | None = None,
              limit: int = MAX_PAGE_SIZE) -> Page:
        items = sorted(
            (r for r in self.store.values() if feature_id is None or r.feature_id == feature_id),
            key=lambda r: r.id,
        )
        return _page(items, cursor, limit, key=lambda r: r.id)


@dataclass(slots=True)
class FakeCoverageRepository:
    store: dict[str, CoverageItem] = field(default_factory=dict)
    approved_hash: dict[int, str] = field(default_factory=dict)

    def upsert_many(self, items: list[CoverageItem]) -> int:
        for item in items:
            self.store[item.id] = item
        return len(items)

    def for_requirement(self, requirement_id: str) -> list[CoverageItem]:
        return [i for i in self.store.values() if i.requirement_id == requirement_id]

    def model_version(self, feature_id: int) -> str | None:
        versions = {i.model_version for i in self.store.values()}
        return max(versions) if versions else None

    def content_hash_for(self, feature_id: int) -> str | None:
        from tto_testgen.domain.model import content_hash

        if not self.store:
            return None
        payload = "|".join(
            f"{i.id}:{i.test_type.value}:{i.planned_count}:{int(i.is_required)}"
            for i in sorted(self.store.values(), key=lambda i: i.id)
        )
        return content_hash(payload)


class FakeIntegrityError(RuntimeError):
    """Raised for the same violations the SQLite triggers abort on."""


@dataclass(slots=True)
class FakeTestCaseRepository:
    store: dict[str, TestCase] = field(default_factory=dict)
    buckets: dict[str, list[str]] = field(default_factory=dict)

    def upsert_many(self, cases: list[TestCase], feature_slug: str) -> int:
        for case in cases:
            # Mirror the production triggers. A fake that accepts what production
            # rejects hides the bug until integration.
            if not case.steps:
                raise FakeIntegrityError(f"REJECTED_NO_STEPS: {case.id}")
            if not case.jira_keys:
                raise FakeIntegrityError(f"REJECTED_NO_JIRA_KEY: {case.id}")
            self.store[case.id] = case
            self.buckets.setdefault(bucket_key(case, feature_slug), []).append(case.id)
        return len(cases)

    def get(self, case_id: str) -> TestCase | None:
        return self.store.get(case_id)

    def query(self, *, feature_id: int | None = None, tag: str | None = None,
              include_obsolete: bool = False, cursor: str | None = None,
              limit: int = MAX_PAGE_SIZE) -> Page:
        items = sorted(
            (
                c
                for c in self.store.values()
                if (feature_id is None or c.feature_id == feature_id)
                and (include_obsolete or not c.is_obsolete)
                and (tag is None or tag in c.tags)
            ),
            key=lambda c: c.id,
        )
        return _page(items, cursor, limit, key=lambda c: c.id)

    def bucket_candidates(self, key: str) -> list[tuple[str, NormalisedCase]]:
        return [
            (case_id, normalise(self.store[case_id]))
            for case_id in self.buckets.get(key, [])
            if case_id in self.store and not self.store[case_id].is_obsolete
        ]

    def existing_identifiers(self) -> list[str]:
        return list(self.store)

    def mark_obsolete(self, case_id: str, reason: str, change_event_id: int) -> None:
        from dataclasses import replace

        if not reason.strip():
            raise FakeIntegrityError("obsolete requires a reason")
        case = self.store[case_id]
        self.store[case_id] = replace(
            case, is_obsolete=True, obsolete_reason=reason,
            obsoleted_by_change_id=change_event_id,
        )

    def count_active(self) -> int:
        return sum(1 for c in self.store.values() if not c.is_obsolete)


@dataclass(slots=True)
class FakeTraceRepository:
    store: list[TraceLink] = field(default_factory=list)

    def add_many(self, links: list[TraceLink]) -> int:
        self.store.extend(links)
        return len(links)

    def for_source(self, source_id: str) -> list[TraceLink]:
        return [l for l in self.store if l.source_id == source_id]

    def all_links(self) -> list[TraceLink]:
        return list(self.store)

    def stream_links(self) -> Iterator[TraceLink]:
        return iter(list(self.store))

    def stream_requirement_ids(self) -> Iterator[str]:
        return iter([])


@dataclass(slots=True)
class FakeEmittedViewRepository:
    """Path -> (feature_slug, content_hash, case_count).

    Deliberately a plain dict rather than a recording spy: the hand-edit rule turns
    on what was stored, not on how many times it was asked, and a spy would let a
    test pass while storing the wrong hash.
    """

    store: dict[str, dict[str, object]] = field(default_factory=dict)

    def get(self, path: str) -> dict[str, object] | None:
        return self.store.get(path)

    def upsert(self, path: str, feature_slug: str, content_hash: str,
               case_count: int, kind: str = "view") -> None:
        self.store[path] = {
            "path": path,
            "feature_slug": feature_slug,
            "content_hash": content_hash,
            "case_count": case_count,
            "kind": kind,
        }

    def for_feature(self, feature_slug: str) -> list[dict[str, object]]:
        return [v for v in self.store.values() if v["feature_slug"] == feature_slug]


@dataclass(slots=True)
class FakeGapRepository:
    store: list[dict[str, object]] = field(default_factory=list)

    def add(self, gap: dict[str, object], run_id: int | None = None) -> int:
        """Mirrors SqliteGapRepository.add exactly.

        An earlier version of this fake took (category, subject, **fields), matching
        a caller rather than the port - so a service calling it the wrong way passed
        against the fake and raised TypeError against SQLite. A fake written to fit
        its caller is not a stand-in for anything.
        """
        self.store.append({**gap, "run_id": run_id})
        return len(self.store)

    def add_unless_open(self, gap: dict[str, object],
                        run_id: int | None = None) -> int | None:
        for existing in self.store:
            if (existing["category"], existing["subject"]) == (
                gap["category"], gap["subject"]
            ):
                return None
        return self.add(gap, run_id)

    def open_gaps(self, category: str | None = None,
                  feature_slug: str | None = None) -> list[dict[str, object]]:
        return [
            g for g in self.store
            if (category is None or g["category"] == category)
            and (feature_slug is None or g["feature_slug"] == feature_slug)
        ]


@dataclass(slots=True)
class FakeAutomationRepository:
    store: dict[str, AutomatedTest] = field(default_factory=dict)

    def upsert(self, test: AutomatedTest) -> AutomatedTest:
        self.store[test.id] = test
        return test

    def for_case(self, case_id: str) -> AutomatedTest | None:
        return next((t for t in self.store.values() if t.case_id == case_id), None)

    def list_at_risk(self) -> list[AutomatedTest]:
        return [t for t in self.store.values() if t.is_at_risk]


@dataclass(slots=True)
class FakeRunStateRepository:
    runs: list[Run] = field(default_factory=list)
    states: dict[tuple[str, str], UnitStateRecord] = field(default_factory=dict)

    def start_run(self, run: Run) -> int:
        self.runs.append(run)
        return len(self.runs)

    def get_state(self, unit_ref: str, stage: StageName) -> UnitStateRecord | None:
        return self.states.get((unit_ref, stage.value))

    def set_state(self, record: UnitStateRecord) -> UnitStateRecord:
        self.states[(record.unit_ref, record.stage.value)] = record
        return record

    def all_states(self, unit_ref: str | None = None) -> list[UnitStateRecord]:
        return [
            s for s in self.states.values() if unit_ref is None or s.unit_ref == unit_ref
        ]


@dataclass(slots=True)
class FakeChangeEventRepository:
    store: list[ChangeEvent] = field(default_factory=list)

    def add(self, event: ChangeEvent) -> int:
        self.store.append(event)
        return len(self.store)

    def latest_for(self, source: str) -> ChangeEvent | None:
        matching = [e for e in self.store if e.source == source]
        return matching[-1] if matching else None


@dataclass(slots=True)
class FakeUnitOfWork:
    resources: FakeResourceRepository = field(default_factory=FakeResourceRepository)
    artefacts: FakeArtefactRepository = field(default_factory=FakeArtefactRepository)
    features: FakeFeatureRepository = field(default_factory=FakeFeatureRepository)
    requirements: FakeRequirementRepository = field(default_factory=FakeRequirementRepository)
    coverage: FakeCoverageRepository = field(default_factory=FakeCoverageRepository)
    cases: FakeTestCaseRepository = field(default_factory=FakeTestCaseRepository)
    traces: FakeTraceRepository = field(default_factory=FakeTraceRepository)
    views: FakeEmittedViewRepository = field(default_factory=FakeEmittedViewRepository)
    gaps: FakeGapRepository = field(default_factory=FakeGapRepository)
    automation: FakeAutomationRepository = field(default_factory=FakeAutomationRepository)
    run_state: FakeRunStateRepository = field(default_factory=FakeRunStateRepository)
    changes: FakeChangeEventRepository = field(default_factory=FakeChangeEventRepository)
    committed: bool = False
    rolled_back: bool = False


@contextmanager
def fake_unit_of_work(uow: FakeUnitOfWork | None = None) -> Iterator[FakeUnitOfWork]:
    """Mirrors the production context manager, including rollback on exception."""
    work = uow or FakeUnitOfWork()
    try:
        yield work
    except Exception:
        work.rolled_back = True
        raise
    else:
        work.committed = True
