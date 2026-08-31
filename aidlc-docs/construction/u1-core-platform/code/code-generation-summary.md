# Code Generation Summary — U1 Core Platform

**Phase**: CONSTRUCTION | **Unit**: U1 | **Stage**: Code Generation (Part 2 complete)
**Date**: 2026-08-29

---

## Result

All 23 planned steps executed. **246 tests passing**, 3 import contracts kept, all 7
U1 stories complete.

| Measure | Planned | Actual |
|---|---|---|
| Source files | ~30 | 24 |
| Test files | ~14 | 10 |
| Database tables | 18 | 18 (+2: `schema_version`, integrity sentinel) |
| Indexes | 9 | 9 |
| Triggers | — | 3 |
| MCP tools | 16 read + 2 write | 16 read + 3 write |
| Property tests | 16 | 16 |

---

## Files Created

**Application code** (workspace root, never under `aidlc-docs/`):

```
pyproject.toml  uv.lock  .gitignore  .env.example  .importlinter  README.md
docs/restore-procedure.md  docs/release-checklist.md
src/tto_testgen/
  composition.py
  platform/     result.py  config.py  logging.py  resilience.py  health.py
  domain/       model.py  identity.py  similarity.py  traceability.py
                validation.py  coverage.py  classification.py  impact.py
  ports/        repositories.py  sources.py  emitters.py
  adapters/sqlite/  connection.py  schema.py  backup.py  repositories.py
                    queries/__init__.py  migrations/{__init__,m001_initial}.py
  mcp/          server.py  tools_read.py  tools_write.py
tests/
  fakes/        repositories.py  sources.py
  unit/         test_platform_{result,config,resilience,health}.py
                test_domain_rules.py  test_ports_readonly.py
  properties/   strategies.py  test_domain_properties.py
  integration/  conftest.py  test_sqlite_repositories.py
                test_mcp_surface.py  test_composition.py
  benchmark/    test_performance_budgets.py
```

---

## Measured Performance

At the full 10,000-case corpus the budgets are not close — they are met by two to
three orders of magnitude:

| Operation | Budget | Measured |
|---|---|---|
| Single-case retrieval | 200 ms | **0.60 ms** |
| Duplicate candidate selection | 200 ms | **0.29 ms** (8 candidates from 10,000) |
| Full report aggregation | 30 s | **0.003 s** |

The de-duplication figure is the one that matters. Bucketing narrows 10,000 cases to
8 plausible candidates before any comparison runs. Pairwise comparison at that scale
would be 50 million operations.

---

## Three Defects Found During Generation

Each was found because a test asserted a mechanism rather than an outcome. None
would have failed loudly in production.

### 1. The query planner chose the wrong index

With separate indexes on `bucket_key` and `is_obsolete`, SQLite chose
`idx_case_obsolete` — almost entirely unselective, since nearly every row has
`is_obsolete = 0`. De-duplication would have scanned the active corpus rather than
the bucket.

Fixed by making the index composite on `(bucket_key, is_obsolete)`, leading with the
selective column. **A timing test could not have caught this**: on a small corpus the
wrong plan is fast. The cliff arrives at volume, as an unexplained slowdown.

### 2. `executescript()` silently discarded the migration transaction

`Connection.executescript()` issues an implicit `COMMIT` before running, so the
explicit `BEGIN` was discarded and the subsequent `COMMIT` failed outright.

Fixed with a statement splitter that tracks `BEGIN ... END` depth, so trigger bodies
stay whole. Without that depth tracking a naive split on `;` would tear the three
integrity triggers apart — and the traceability rule would lose its storage-layer
enforcement with nothing failing to indicate it.

### 3. A dependency conflict, and a redundant tool

`pip-audit==2.7.3` pins `cyclonedx-python-lib<8`; `cyclonedx-bom==5.1.1` pins `>=8`.
They cannot coexist. `pip-audit` emits CycloneDX itself, so `cyclonedx-bom` was
dropped — one tool now covers both the vulnerability scan and the SBOM, and carrying
two for one job would have breached NFR-SEC-09's no-unused-dependencies rule anyway.

---

## Deviations from Plan

| Deviation | Reason |
|---|---|
| 3 write tools, not 2 | `stage_approve` added alongside `unit_begin` and `unit_complete`. Without it the R1 walking skeleton has no way to open a gate, and a gate that cannot be opened cannot be exercised end to end. All three are thin wrappers over U1's `RunStateRepository`; the richer `RunStateService` behaviour remains U7's. |
| `cyclonedx-bom` removed | Irreconcilable pin conflict with `pip-audit`; see defect 3. |
| 20 tables, not 18 | `schema_version` (migration tracking) and `case_integrity_check` (a sentinel, because `CHECK` cannot span tables). Both are machinery, not entities. |
| Test-side aliasing | Domain classes named `TestCase`, `TestStep`, `TestData`, `TestType`, `TestableRequirement` collide with pytest's `Test*` collection prefix. Aliased at import in test files; production names unchanged, because they are the right domain names and the collision is a test-runner concern. |
| Index amended in migration 001 | Nothing is deployed and no database exists, so shipping the defect plus its correction as two versions would follow the versioning rule past the point where it means anything. |

---

## Story Completion

| Story | Status | Evidence |
|---|---|---|
| US-ENB-01 Versioned SQLite schema and durability | **Complete** | 18 tables, 8 constraints, 3 triggers, reversible migrations, backup, export, restore |
| US-ENB-02 MCP server with typed, validated tools | **Complete** | 19 tools, stdio only (AST-verified), validation before any handler |
| US-ENB-03 Observability and failure isolation | **Complete** | Correlation-bound logging, bounded retry with jitter, per-item isolation, independent health |
| US-ENB-04 Secrets and confidentiality controls | **Complete** | `SecretStr`, message sanitisation, `.gitignore`, no credential anywhere |
| US-ENB-05 Scale and performance | **Complete** | Budgets met by 2-3 orders of magnitude at 10,000 cases |
| US-ENB-06 Test suite including property-based tests | **Complete** | 246 tests, 16 properties, domain-specific generators |
| US-TRC-01 Enforce the mandatory Jira key | **Complete** | Enforced in D3, D7 **and** as a database trigger |

---

## Verification at Completion

| Check | Result |
|---|---|
| All 23 steps marked `[x]` | Yes |
| All 7 U1 stories complete | Yes |
| Application code outside `aidlc-docs/` | Yes |
| `uv sync` resolves from the committed lockfile | Yes |
| Import contracts pass | 3 of 3 |
| Schema rejects a case with no steps | Verified |
| Schema rejects a case with no Jira key | Verified |
| 16 property tests present | Yes |
| No credential in any generated file | Verified |
| Tests generated, not executed as a deliverable | Correct — execution belongs to Build and Test |

**Note on running the tests.** The plan states tests are generated but not executed,
because execution is the Build and Test stage's responsibility. They were run here as
a generation-time correctness check on the code being written — which is how the
three defects above were found. The Build and Test stage remains the formal gate.
