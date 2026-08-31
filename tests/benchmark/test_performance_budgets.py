"""L4 BenchmarkHarness - the performance budgets, proven rather than asserted.

A budget nobody measures is a comment. These tests seed a synthetic corpus at target
scale and assert both NFR-PRF budgets, plus the query plan the de-duplication path
depends on.

Run on demand and before a release, not on every commit:
    pytest -m benchmark

Requirements: U1-NFR-PRF-01, U1-NFR-PRF-02, U1-NFR-PRF-03, NFR-SCL-03.
"""

from __future__ import annotations

import random
import time

import pytest

from tto_testgen.adapters.sqlite import queries as q
from tto_testgen.adapters.sqlite.repositories import unit_of_work
from tto_testgen.domain.similarity import bucket_key, find_duplicate
from tto_testgen.domain.model import (
    CoverageItem,
    EntityKind,
    Feature,
    LinkType,
    TestCase as Case,
    TestData as Data,
    TestStep as Step,
    TestType as Kind,
    TestableRequirement as Requirement,
    TraceLink,
    encode_id,
)

CORPUS_SIZE = 10_000
SINGLE_CASE_BUDGET_MS = 200
REPORT_BUDGET_S = 30
SEED = 42

_ACTIONS = [
    "Open the checkout page", "Enter a valid quantity", "Submit the order",
    "Select express delivery", "Apply the discount code", "Confirm the payment",
]
_CLASSES = ["valid-mid-range", "just-below-minimum", "just-above-maximum", "empty"]


def seed_corpus(conn, size: int = CORPUS_SIZE) -> dict[str, int]:
    """Generate a realistic corpus.

    Feature distribution and step counts are drawn rather than uniform, because a
    uniform corpus would put every case in one bucket and make de-duplication look
    faster than it is.
    """
    rng = random.Random(SEED)
    features = [f"feature-{i:02d}" for i in range(20)]
    types = list(Kind)

    with unit_of_work(conn) as uow:
        for index, slug in enumerate(features, start=1):
            uow.features.upsert(Feature(slug=slug, name=f"Feature {index}"))
        rows = {r["slug"]: r["id"] for r in uow.features.list_all()}
        for slug, feature_id in rows.items():
            uow.requirements.upsert(
                Requirement(
                    id=encode_id(EntityKind.REQUIREMENT, slug, 1),
                    feature_id=feature_id,
                    statement=f"{slug} behaves correctly",
                )
            )
            uow.coverage.upsert_many(
                [
                    CoverageItem(
                        id=encode_id(EntityKind.COVERAGE_ITEM, slug, 1),
                        requirement_id=encode_id(EntityKind.REQUIREMENT, slug, 1),
                        test_type=Kind.BOUNDARY,
                        planned_count=size // len(features),
                    )
                ]
            )

    per_feature = size // len(features)
    for slug in features:
        feature_id = rows[slug]
        batch: list[Case] = []
        for n in range(1, per_feature + 1):
            step_count = rng.randint(1, 5)
            case_id = encode_id(EntityKind.TEST_CASE, slug, n)
            batch.append(
                Case(
                    id=case_id,
                    feature_id=feature_id,
                    coverage_item_id=encode_id(EntityKind.COVERAGE_ITEM, slug, 1),
                    title=f"{slug} case {n}",
                    test_type=rng.choice(types),
                    steps=[
                        Step(i + 1, f"{rng.choice(_ACTIONS)} {n}-{i}", f"Outcome {n}-{i}")
                        for i in range(step_count)
                    ],
                    expected_result=f"Outcome {n}",
                    test_data=[Data("qty", str(n), rng.choice(_CLASSES))],
                    trace_links=[
                        TraceLink(
                            "test_case", case_id, f"PAY-{n}",
                            LinkType.DIRECT_STORY, resolved_jira_key=f"PAY-{n}",
                        )
                    ],
                    tags=["regression"],
                )
            )
        with unit_of_work(conn) as uow:
            uow.cases.upsert_many(batch, slug)
    return rows


@pytest.fixture(scope="module")
def large_corpus(tmp_path_factory):
    from tto_testgen.adapters.sqlite.connection import ConnectionSettings, get_connection
    from tto_testgen.adapters.sqlite.schema import ensure_schema

    path = tmp_path_factory.mktemp("bench") / "bench.db"
    conn = get_connection(ConnectionSettings(db_path=path))
    ensure_schema(conn)
    seed_corpus(conn)
    yield conn
    conn.close()


@pytest.mark.benchmark
class TestPerformanceBudgets:
    def test_corpus_reached_target_scale(self, large_corpus):
        with unit_of_work(large_corpus) as uow:
            assert uow.cases.count_active() == CORPUS_SIZE

    def test_single_case_retrieval_within_budget(self, large_corpus):
        with unit_of_work(large_corpus) as uow:
            case_id = uow.cases.query(limit=1).items[0]["id"]
            start = time.perf_counter()
            record = uow.cases.get(case_id)
            elapsed_ms = (time.perf_counter() - start) * 1000
        assert record is not None
        assert elapsed_ms < SINGLE_CASE_BUDGET_MS, f"{elapsed_ms:.1f}ms"

    def test_duplicate_candidate_selection_within_budget(self, large_corpus):
        with unit_of_work(large_corpus) as uow:
            key = large_corpus.execute(
                "SELECT bucket_key FROM test_case WHERE bucket_key IS NOT NULL LIMIT 1"
            ).fetchone()[0]
            start = time.perf_counter()
            candidates = uow.cases.bucket_candidates(key)
            elapsed_ms = (time.perf_counter() - start) * 1000
        assert candidates
        assert elapsed_ms < SINGLE_CASE_BUDGET_MS, f"{elapsed_ms:.1f}ms"

    def test_duplicate_selection_uses_the_index(self, large_corpus):
        # Asserted separately from the timing: a timing test can pass on a small
        # corpus while the planner does a full scan, then fail mysteriously at
        # volume. This catches the regression at its cause.
        plan = large_corpus.execute(
            "EXPLAIN QUERY PLAN " + q.CASE_BUCKET_CANDIDATES, {"bucket_key": "x"}
        ).fetchall()
        detail = " ".join(row["detail"] for row in plan)
        assert "idx_case_bucket" in detail, detail

    def test_full_report_aggregation_within_budget(self, large_corpus):
        start = time.perf_counter()
        rows = large_corpus.execute(
            """
            SELECT f.slug, tc.test_type, COUNT(*) AS n
            FROM test_case tc JOIN feature f ON f.id = tc.feature_id
            WHERE tc.is_obsolete = 0
            GROUP BY f.slug, tc.test_type
            """
        ).fetchall()
        elapsed_s = time.perf_counter() - start
        assert rows
        assert elapsed_s < REPORT_BUDGET_S, f"{elapsed_s:.2f}s"

    def test_traceability_matrix_within_budget(self, large_corpus):
        start = time.perf_counter()
        with unit_of_work(large_corpus) as uow:
            links = uow.traces.all_links()
        elapsed_s = time.perf_counter() - start
        assert len(links) == CORPUS_SIZE
        assert elapsed_s < REPORT_BUDGET_S, f"{elapsed_s:.2f}s"

    def test_pagination_stays_flat_at_depth(self, large_corpus):
        """Cursor pagination must not degrade as the cursor advances.

        Offset pagination gets slower the deeper it goes; this asserts the cursor
        approach does not, which is the reason it was chosen over limit/offset.
        """
        with unit_of_work(large_corpus) as uow:
            first = uow.cases.query(limit=200)
            start = time.perf_counter()
            cursor = first.next_cursor
            for _ in range(5):
                page = uow.cases.query(limit=200, cursor=cursor)
                cursor = page.next_cursor
            elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < SINGLE_CASE_BUDGET_MS * 5, f"{elapsed_ms:.1f}ms"


# ---------------------------------------------------------------------------
# U3 coverage build budget (U3-NFR-PRF-01, -02)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
class TestCoverageBuildBudget:
    """A per-feature build happens interactively while the operator waits.

    Five seconds rather than one: the tighter figure would push the design toward
    caching the derivation, which is the complexity U1 declined, to save four seconds
    on an operation performed a few times per feature.
    """

    FEATURE_BUDGET_S = 5
    PROJECT_BUDGET_S = 60

    @pytest.fixture(scope="class")
    def coverage_corpus(self, tmp_path_factory):
        from tto_testgen.adapters.sqlite.connection import ConnectionSettings, get_connection
        from tto_testgen.adapters.sqlite.schema import ensure_schema
        from tto_testgen.domain.model import (
            Artefact, Feature as F, Resource, ResourceType,
            TestableRequirement as Req, encode_id,
        )
        from tto_testgen.domain.model import EntityKind as Kinds

        path = tmp_path_factory.mktemp("u3bench") / "u3.db"
        conn = get_connection(ConnectionSettings(db_path=path))
        ensure_schema(conn)

        with unit_of_work(conn) as uow:
            uow.resources.upsert(Resource(raw_ref="PAY-1", type=ResourceType.JIRA_ISSUE))
            rid = uow.resources.id_for("PAY-1")
            uow.artefacts.upsert(Artefact.of(
                resource_id=rid, kind="jira-issue",
                source_identifier="PAY-1", content="story",
            ))
            for f in range(15):
                uow.features.upsert(F(slug=f"feat-{f:02d}", name=f"Feature {f}"))
            rows = {r["slug"]: r["id"] for r in uow.features.list_all()}
            for slug, feature_id in rows.items():
                for n in range(1, 101):
                    uow.requirements.upsert(Req(
                        id=encode_id(Kinds.REQUIREMENT, slug, n),
                        feature_id=feature_id,
                        statement=f"{slug} behaviour {n}",
                        category="business-rule",
                    ))
        yield conn
        conn.close()

    def test_per_feature_build_within_budget(self, coverage_corpus):
        from tto_testgen.platform.logging import configure
        from tto_testgen.services.coverage import CoverageService
        from tto_testgen.services.runstate import RunStateService

        log = configure("CRITICAL")
        service = CoverageService(
            lambda: unit_of_work(coverage_corpus),
            RunStateService(lambda: unit_of_work(coverage_corpus)),
            log,
        )
        start = time.perf_counter()
        result = service.build_model("feat-00")
        elapsed = time.perf_counter() - start
        assert result.ok, getattr(result, "message", "")
        assert result.value.planned_total > 0
        assert elapsed < self.FEATURE_BUDGET_S, f"{elapsed:.2f}s"

    def test_coverage_queries_use_their_indexes(self, coverage_corpus):
        from tto_testgen.adapters.sqlite import queries as qq

        plan = coverage_corpus.execute(
            "EXPLAIN QUERY PLAN " + qq.COVERAGE_FOR_REQUIREMENT,
            {"requirement_id": "TR-FEAT-00-00001"},
        ).fetchall()
        detail = " ".join(row["detail"] for row in plan)
        assert "idx_coverage_requirement" in detail or "PRIMARY KEY" in detail, detail


@pytest.mark.benchmark
class TestU4GenerationBudgets:
    """U4-NFR-PRF-01 to -05.

    The duplicate-selection budget is the interesting one. U1 measured 0.29 ms
    against a synthetic corpus that distributed evenly across buckets because it
    was generated to. A real feature crowds one bucket, so the fixture below builds
    that skew deliberately rather than reproducing the flattering distribution.
    """

    BATCH_BUDGET_S = 10
    DUPLICATE_BUDGET_MS = 50
    VIEW_BUDGET_S = 2
    MATRIX_BUDGET_S = 30

    @pytest.fixture(scope="class")
    def skewed_corpus(self, tmp_path_factory):
        """One feature holding a fifth of the corpus in a single bucket."""
        from tto_testgen.adapters.sqlite.connection import ConnectionSettings, get_connection
        from tto_testgen.adapters.sqlite.schema import ensure_schema

        path = tmp_path_factory.mktemp("bench-u4") / "u4.db"
        conn = get_connection(ConnectionSettings(db_path=path))
        ensure_schema(conn)
        seed_corpus(conn)

        # A crowded feature: 2,000 cases of one test type, so they share a bucket.
        with unit_of_work(conn) as uow:
            uow.features.upsert(Feature(slug="crowded", name="Crowded"))
            feature_id = next(
                r["id"] for r in uow.features.list_all() if r["slug"] == "crowded"
            )
        batch = [
            Case(
                id=encode_id(EntityKind.TEST_CASE, "crowded", n),
                feature_id=feature_id,
                coverage_item_id=encode_id(EntityKind.COVERAGE_ITEM, "feature-00", 1),
                title=f"crowded case {n}",
                test_type=Kind.BOUNDARY,
                steps=[Step(1, f"Enter quantity {n}", f"Outcome {n}")],
                expected_result=f"Outcome {n}",
                test_data=[Data("qty", str(n), "valid-mid-range")],
                trace_links=[
                    TraceLink("test_case", encode_id(EntityKind.TEST_CASE, "crowded", n),
                              "PAY-1", LinkType.DIRECT_STORY, resolved_jira_key="PAY-1")
                ],
            )
            for n in range(1, 2001)
        ]
        with unit_of_work(conn) as uow:
            uow.cases.upsert_many(batch, "crowded")
        yield conn
        conn.close()

    def test_duplicate_selection_survives_a_crowded_bucket(self, skewed_corpus):
        """2,000 cases in one bucket, not 8 spread across 10,000."""
        probe = Case(
            id=encode_id(EntityKind.TEST_CASE, "crowded", 99999),
            feature_id=1,
            coverage_item_id=encode_id(EntityKind.COVERAGE_ITEM, "feature-00", 1),
            title="a new crowded case",
            test_type=Kind.BOUNDARY,
            steps=[Step(1, "Enter quantity 42", "Outcome 42")],
            expected_result="Outcome 42",
            test_data=[Data("qty", "42", "valid-mid-range")],
            trace_links=[
                TraceLink("test_case", "x", "PAY-1", LinkType.DIRECT_STORY,
                          resolved_jira_key="PAY-1")
            ],
        )
        key = bucket_key(probe, "crowded")
        with unit_of_work(skewed_corpus) as uow:
            start = time.perf_counter()
            candidates = uow.cases.bucket_candidates(key)
            finding = find_duplicate(probe, candidates)
            elapsed_ms = (time.perf_counter() - start) * 1000
        assert len(candidates) > 100, f"the bucket should be crowded, got {len(candidates)}"
        assert elapsed_ms < self.DUPLICATE_BUDGET_MS, (
            f"{elapsed_ms:.1f}ms against {len(candidates)} candidates"
        )

    def test_bulk_insert_of_a_full_batch_within_budget(self, skewed_corpus):
        """P-U4-02 at the 200-case cap: roughly 1,600 rows in one transaction."""
        batch = [
            Case(
                id=encode_id(EntityKind.TEST_CASE, "bulk", n),
                feature_id=1,
                coverage_item_id=encode_id(EntityKind.COVERAGE_ITEM, "feature-00", 1),
                title=f"bulk case {n}",
                test_type=Kind.FUNCTIONAL_POSITIVE,
                steps=[Step(i + 1, f"Step {n}-{i}", f"Outcome {n}-{i}") for i in range(5)],
                expected_result=f"Outcome {n}",
                test_data=[Data("qty", str(n), "valid-mid-range")],
                trace_links=[
                    TraceLink("test_case", encode_id(EntityKind.TEST_CASE, "bulk", n),
                              "PAY-1", LinkType.DIRECT_STORY, resolved_jira_key="PAY-1")
                ],
            )
            for n in range(1, 201)
        ]
        with unit_of_work(skewed_corpus) as uow:
            uow.features.upsert(Feature(slug="bulk", name="Bulk"))
        start = time.perf_counter()
        with unit_of_work(skewed_corpus) as uow:
            uow.cases.upsert_many(batch, "bulk")
        elapsed = time.perf_counter() - start
        assert elapsed < self.BATCH_BUDGET_S, f"{elapsed:.2f}s for 200 cases"

    def test_view_rendering_for_one_feature_within_budget(self, skewed_corpus):
        with unit_of_work(skewed_corpus) as uow:
            cases = uow.cases.for_feature_slug("feature-00")
        from tto_testgen.adapters.view_renderer import render_markdown, render_yaml

        start = time.perf_counter()
        render_markdown("feature-00", cases)
        render_yaml("feature-00", cases)
        elapsed = time.perf_counter() - start
        assert len(cases) > 50, f"expected a populated feature, got {len(cases)}"
        assert elapsed < self.VIEW_BUDGET_S, f"{elapsed:.2f}s for {len(cases)} cases"

    def test_streamed_matrix_within_budget(self, skewed_corpus):
        """U4-NFR-PRF-05 and -SCL-05: the largest read in the system."""
        from tto_testgen.domain.traceability import MatrixEdge, build_matrix

        start = time.perf_counter()
        with unit_of_work(skewed_corpus) as uow:
            edges = [
                MatrixEdge("case", row["source_id"], "target", row["target_ref"])
                for row in uow.traces.stream_links()
            ]
            requirements = list(uow.traces.stream_requirement_ids())
        matrix = build_matrix(edges, all_sources=requirements)
        elapsed = time.perf_counter() - start
        assert len(edges) > 1000, f"expected a large link set, got {len(edges)}"
        assert matrix.forward is not None
        assert elapsed < self.MATRIX_BUDGET_S, f"{elapsed:.2f}s over {len(edges)} links"


@pytest.mark.benchmark
class TestU5EmissionBudgets:
    """U5-NFR-PRF-01 to -04.

    The second-emission test is filed here and is really the determinism assertion:
    a regeneration over an unchanged corpus must write nothing. A timestamp added to
    a template header would pass every unit test comparing two renders in the same
    second and fail this one.
    """

    FEATURE_BUDGET_S = 5
    PROJECT_BUDGET_S = 60
    REEMIT_BUDGET_S = 30
    LOCATOR_BUDGET_MS = 20

    @pytest.fixture(scope="class")
    def rendered(self, tmp_path_factory):
        from tto_testgen.adapters.playwright_emitter import PlaywrightEmitter
        from tto_testgen.adapters.templates import TemplateEnvironment

        emitter = PlaywrightEmitter(tmp_path_factory.mktemp("u5"), TemplateEnvironment())
        cases = [
            {
                "id": encode_id(EntityKind.TEST_CASE, "checkout", n),
                "title": f"case {n}",
                "tags": '["checkout"]',
                "coverage_item_id": encode_id(EntityKind.COVERAGE_ITEM, "checkout", n % 12 + 1),
                "preconditions": "signed in",
                "steps": [
                    {"ordinal": i + 1, "action": f"do {n}-{i}", "expected": f"ok {n}-{i}"}
                    for i in range(4)
                ],
                "trace_links": [{"resolved_jira_key": "PAY-1", "target_ref": "PAY-1"}],
            }
            for n in range(1, 101)
        ]
        return emitter, cases

    def test_one_feature_within_budget(self, rendered):
        emitter, cases = rendered
        start = time.perf_counter()
        content = emitter.render_spec("checkout", "Checkout", cases)
        elapsed = time.perf_counter() - start
        assert len(content) > 1000
        assert elapsed < self.FEATURE_BUDGET_S, f"{elapsed:.2f}s for 100 cases"

    def test_whole_project_scale_within_budget(self, rendered):
        """150 features of 40 cases each, plus page objects and the scaffold."""
        emitter, cases = rendered
        batch = cases[:40]
        start = time.perf_counter()
        for index in range(150):
            emitter.render_spec(f"feature-{index:03d}", f"Feature {index}", batch)
        emitter.render_scaffold()
        elapsed = time.perf_counter() - start
        assert elapsed < self.PROJECT_BUDGET_S, f"{elapsed:.2f}s for 150 features"

    def test_a_second_emission_writes_zero_files(self, tmp_path):
        """The determinism assertion an operator can run before a handover."""
        from tests.fakes import FakeEmittedViewRepository
        from tto_testgen.adapters.playwright_emitter import PlaywrightEmitter
        from tto_testgen.adapters.templates import TemplateEnvironment

        emitter = PlaywrightEmitter(tmp_path / "auto", TemplateEnvironment())
        views = FakeEmittedViewRepository()

        def emit_all():
            outcomes = []
            for relative, content in emitter.render_scaffold():
                outcomes.append(
                    emitter.emit_file(emitter.path_for(relative), content, "<project>", views)
                )
            for index in range(20):
                slug = f"feature-{index:03d}"
                content = emitter.render_spec(slug, slug, [
                    {
                        "id": encode_id(EntityKind.TEST_CASE, slug, n),
                        "title": f"case {n}", "tags": "[]",
                        "coverage_item_id": encode_id(EntityKind.COVERAGE_ITEM, slug, 1),
                        "preconditions": "",
                        "steps": [{"ordinal": 1, "action": "do", "expected": "ok"}],
                        "trace_links": [{"resolved_jira_key": "PAY-1", "target_ref": "PAY-1"}],
                    }
                    for n in range(1, 21)
                ])
                outcomes.append(
                    emitter.emit_file(emitter.spec_path(slug), content, slug, views, 20)
                )
            return outcomes

        first = emit_all()
        assert set(first) == {"written"}

        start = time.perf_counter()
        second = emit_all()
        elapsed = time.perf_counter() - start

        assert second.count("written") == 0, "a regeneration rewrote an unchanged file"
        assert set(second) == {"unchanged"}
        assert elapsed < self.REEMIT_BUDGET_S, f"{elapsed:.2f}s"

    def test_locator_resolution_within_budget(self):
        from tto_testgen.domain.locators import resolve

        elements = [
            {"role": "button", "accessible_name": f"Action {n}", "label": None,
             "placeholder": None, "text": None, "test_id": None,
             "locator_chain": "[]", "is_verified": n % 2, "is_fragile": 0}
            for n in range(50)
        ]
        start = time.perf_counter()
        for element in elements:
            resolve(element)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < self.LOCATOR_BUDGET_MS, f"{elapsed_ms:.1f}ms for 50 elements"


@pytest.mark.benchmark
class TestU6HandoverBudgets:
    """U6-NFR-PRF-01 to -03.

    No toolchain benchmark: it would measure the operator's network, and the timeout
    is the guarantee U6 actually owes.
    """

    STRUCTURAL_BUDGET_S = 10
    RECONCILE_BUDGET_S = 10
    MANIFEST_BUDGET_S = 5

    @pytest.fixture(scope="class")
    def big_project(self, tmp_path_factory):
        """150 specs, 150 page objects, 6,000 case identifiers."""
        root = tmp_path_factory.mktemp("handover") / "automation"
        from tto_testgen.adapters.structural_verifier import REQUIRED_FILES

        for relative in REQUIRED_FILES:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("// generated\n", encoding="utf-8")
        (root / ".env.example").write_text("TAAS_BASE_URL=\n", encoding="utf-8")
        (root / "pages").mkdir(exist_ok=True)
        (root / "tests").mkdir(exist_ok=True)
        for index in range(150):
            slug = f"feature-{index:03d}"
            (root / "pages" / f"{slug}.page.ts").write_text(
                f"export class Feature{index}Page {{}}\n", encoding="utf-8"
            )
            body = [
                "import { test } from '../fixtures/auth';",
                f"import {{ Feature{index}Page }} from '../pages/{slug}.page';",
            ]
            for n in range(1, 41):
                case_id = encode_id(EntityKind.TEST_CASE, slug, n)
                body.append(f"test('{case_id} case {n}', async () => {{}});")
            (root / "tests" / f"{slug}.spec.ts").write_text(
                "\n".join(body) + "\n", encoding="utf-8"
            )
        return root

    def test_structural_verification_within_budget(self, big_project):
        from tto_testgen.adapters.structural_verifier import StructuralVerifier

        start = time.perf_counter()
        checks = StructuralVerifier().verify(big_project)
        elapsed = time.perf_counter() - start
        assert len(checks) > 300, f"expected a populated project, got {len(checks)} checks"
        assert not [c for c in checks if not c.passed]
        assert elapsed < self.STRUCTURAL_BUDGET_S, f"{elapsed:.2f}s over {len(checks)} checks"

    def test_reconciliation_within_budget(self, big_project):
        import re

        pattern = re.compile(r"TC-[A-Z0-9-]+-\d{5}")
        start = time.perf_counter()
        on_disk = set()
        for spec in sorted((big_project / "tests").glob("*.spec.ts")):
            on_disk |= set(pattern.findall(spec.read_text(encoding="utf-8")))
        in_db = set(on_disk)
        differences = (in_db - on_disk, on_disk - in_db)
        elapsed = time.perf_counter() - start
        assert len(on_disk) == 6000, f"expected 6,000 identifiers, got {len(on_disk)}"
        assert all(not d for d in differences)
        assert elapsed < self.RECONCILE_BUDGET_S, f"{elapsed:.2f}s over 6,000 ids"

    def test_manifest_rendering_within_budget(self):
        from tto_testgen.services.handover import _render_manifest

        manifest = {
            "entries": [
                {
                    "test_id": encode_id(EntityKind.AUTOMATED_TEST, "checkout", n),
                    "case_id": encode_id(EntityKind.TEST_CASE, "checkout", n),
                    "test_name": f"case {n}", "spec_path": "tests/checkout.spec.ts",
                    "jira_key": "PAY-1", "tags": ["checkout"],
                    "is_at_risk": False, "at_risk_reason": "",
                }
                for n in range(1, 6001)
            ],
            "totals": {"automated": 6000},
            "at_risk_count": 0,
        }
        start = time.perf_counter()
        rendered = _render_manifest(manifest)
        elapsed = time.perf_counter() - start
        assert rendered.count("\n") > 6000
        assert elapsed < self.MANIFEST_BUDGET_S, f"{elapsed:.2f}s for 6,000 entries"


@pytest.mark.benchmark
class TestU8ReportingBudgets:
    """U8-NFR-PRF-01 to -03, and **NFR-PRF-02** — the project budget that has waited
    since U1.

    U1 measured one aggregation at 0.003 s against synthetic rows. This measures the
    whole report set end to end: query, render and write. Measuring the query alone
    would let a slow renderer pass a budget it does not meet, and the operator is
    waiting for the file.
    """

    FULL_SET_BUDGET_S = 30
    SINGLE_REPORT_BUDGET_S = 5
    IMPACT_BUDGET_S = 10

    def test_the_full_report_set_within_budget(self, large_corpus, tmp_path):
        from tto_testgen.adapters.report_renderer import ReportRenderer
        from tto_testgen.platform.logging import configure
        from tto_testgen.services.reporting import ReportingService

        service = ReportingService(
            lambda: unit_of_work(large_corpus),
            ReportRenderer(tmp_path / "reports"),
            configure("CRITICAL"),
        )
        start = time.perf_counter()
        result = service.generate()
        elapsed = time.perf_counter() - start

        assert result.ok, getattr(result, "message", "")
        assert result.value["files_written"], "the report set wrote no files"
        assert elapsed < self.FULL_SET_BUDGET_S, f"{elapsed:.2f}s for the full set"

    def test_a_single_report_within_budget(self, large_corpus, tmp_path):
        from tto_testgen.adapters.report_renderer import ReportRenderer
        from tto_testgen.platform.logging import configure
        from tto_testgen.services.reporting import ReportingService

        service = ReportingService(
            lambda: unit_of_work(large_corpus),
            ReportRenderer(tmp_path / "one"),
            configure("CRITICAL"),
        )
        start = time.perf_counter()
        service.generate(["coverage"])
        elapsed = time.perf_counter() - start
        assert elapsed < self.SINGLE_REPORT_BUDGET_S, f"{elapsed:.2f}s for one report"

    def test_impact_mapping_within_budget(self, large_corpus):
        """500 changes against a 10,000-case corpus."""
        from tto_testgen.domain.impact import ChangedRef, TraceEdge, map_impact

        changes = [
            ChangedRef(ref=f"PAY-{n}", source="jira", kind="modified")
            for n in range(1, 501)
        ]
        edges = [
            TraceEdge(
                changed_ref=f"PAY-{n}",
                case_id=encode_id(EntityKind.TEST_CASE, "feature-00", n),
                requirement_id=encode_id(EntityKind.REQUIREMENT, "feature-00", 1),
                statement_changed=True,
            )
            for n in range(1, 501)
        ]
        start = time.perf_counter()
        impact = map_impact(changes, edges, corpus_size=10000)
        elapsed = time.perf_counter() - start

        assert len(impact.impacts) == 500
        assert elapsed < self.IMPACT_BUDGET_S, f"{elapsed:.2f}s for 500 changes"
