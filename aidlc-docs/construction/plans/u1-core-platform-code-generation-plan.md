# Code Generation Plan — U1 Core Platform

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U1 | **Stage**: Code Generation (Part 1: Planning)
**Created**: 2026-08-29T11:01:00Z
**Status**: COMPLETE 2026-08-29 - all 23 steps executed

**This plan is the single source of truth for U1 Code Generation.** Part 2 executes exactly these
steps in order, marking each `[x]` in the interaction that completes it.

---

## 1. Unit Context

### Stories implemented by U1 (7)

| Story | Title | Release |
|---|---|---|
| US-ENB-01 | Versioned SQLite schema and durability | R1/R2 |
| US-ENB-02 | MCP server with typed, validated tools | R1 |
| US-ENB-03 | Observability and failure isolation | R1 |
| US-ENB-04 | Secrets and confidentiality controls | R1 |
| US-ENB-05 | Scale and performance | R2 |
| US-ENB-06 | Test suite including property-based tests | R2 |
| US-TRC-01 | Enforce the mandatory Jira key | R1 |

### Dependencies on other units

**None.** U1 is the foundation. Every other unit depends on it.

### Interfaces U1 exposes

| Consumer | Contract |
|---|---|
| All units | Domain types (D1), port protocols (P1-P3), `Result` (X1), tool registration (M2) |
| U2-U8 services | `unit_of_work()` context manager yielding bound repositories |
| All unit tests | Shared in-memory fakes satisfying every port |

### Database entities owned

All 18. U1 defines the complete schema; other units read and write through repositories.

### Release depth for this pass

**R1 depth.** Per the Q4 walking-skeleton decision, U1 is built to R1 first: schema, MCP server,
platform, domain kernel. R2 items — the benchmark harness and the full property suite — are marked
in the plan and deferred to pass 2, except where they are cheap to include now.

**Exception taken deliberately**: the property test suite (US-ENB-06, R2) is included in this pass.
The properties verify invariants the entire corpus depends on, and writing them alongside the domain
is far cheaper than retrofitting them after seven other units have been built against unverified
behaviour.

---

## 2. Code Location

**Workspace root**: `/Users/supun/Documents/Supun_WF/aidlc/aidlc-test-analysit`

Application code goes to the workspace root. Documentation goes to
`aidlc-docs/construction/u1-core-platform/code/` as markdown summaries only.

### Structure

Following the repository layout approved at Units Generation (Q7 = A, single installable package).

**Note on the deviation**: `code-generation.md` suggests `src/{unit-name}/` for a greenfield
multi-unit monolith. That pattern assumes units map to feature directories. Here, Units Generation
explicitly decided a single installable package whose units map to *architectural concerns* —
because the hexagonal dependency rule runs across units, and a per-unit directory tree would put
`domain/` in eight places. Unit ownership is recorded per file instead.

```
<workspace-root>/
  pyproject.toml
  uv.lock
  .gitignore
  .env.example
  .importlinter
  README.md
  src/tto_testgen/
    __init__.py
    composition.py
    platform/     result.py logging.py config.py resilience.py health.py
    domain/       model.py coverage.py traceability.py similarity.py
                  identity.py classification.py validation.py impact.py
    ports/        repositories.py sources.py emitters.py
    adapters/sqlite/
                  connection.py schema.py migrations/ repositories.py queries/ backup.py
    mcp/          server.py tools_read.py tools_write.py
  tests/
    fakes/        in-memory port implementations, shared across all units
    unit/         example-based
    properties/   Hypothesis, targets domain/ only
    integration/  adapters against a temp SQLite file
    benchmark/    L4 harness
```

---

## 3. Generation Steps

23 steps. Each is marked `[x]` in the interaction that completes it.

### Phase A — Foundation

- [x] **Step 1**: Project structure setup — `pyproject.toml` with exact pins, `.gitignore`
      (excluding `.taas/` and `generated/`), `.env.example`, `.importlinter` contracts, package
      directories with `__init__.py`
      *Serves*: US-ENB-02, NFR-SEC-09, NFR-SEC-12, NFR-MNT-01

- [x] **Step 2**: Platform layer — X1 `result.py` (Result type, 16 error codes, `sanitise`),
      X3 `config.py` (frozen config, `SecretStr`, fail-fast), X2 `logging.py` (structured,
      correlation binding, redaction), X4 `resilience.py` (bounded retry with jitter, isolation),
      X5 `health.py` (independent per-component reporting)
      *Serves*: US-ENB-03, US-ENB-04

- [x] **Step 3**: Platform unit tests — Result semantics, sanitisation, redaction, retry policy
      including never-retry-4xx, isolation, health independence
      *Serves*: US-ENB-03, US-ENB-04

### Phase B — Business Logic (Domain)

- [x] **Step 4**: D1 `model.py` — 18 entities, 11 value objects, 9 enumerations, construction
      invariants, `to_dict`/`from_dict`
      *Serves*: US-ENB-01, US-TRC-01

- [x] **Step 5**: D5 `identity.py` and D4 `similarity.py` — identifier allocation with stability,
      normalisation, shingles, Jaccard, bucket keys, BR-1.4 equivalence-class override
      *Serves*: US-ENB-05

- [x] **Step 6**: D3 `traceability.py` and D7 `validation.py` — Jira key enforcement, commit
      derivation with 180-day window and selection basis, link typing, matrix construction;
      the ten-check validation pipeline in its specified order
      *Serves*: US-TRC-01

- [x] **Step 7**: D2 `coverage.py`, D6 `classification.py`, D8 `impact.py` — ISTQB depth rules,
      yield computation, reduction; weighted risk with partial-rating handling; the ten-rule
      automatability decision list; impact classification
      *Serves*: US-ENB-01

- [x] **Step 8**: Domain unit tests — example-based coverage of every documented rule in
      `business-rules.md` (BR-1 to BR-9)
      *Serves*: US-ENB-06

- [x] **Step 9**: Domain property tests — all 16 properties from `business-logic-model.md` §7,
      with domain-specific Hypothesis strategies
      *Serves*: US-ENB-06

- [x] **Step 10**: Business logic summary → `aidlc-docs/construction/u1-core-platform/code/business-logic-summary.md`

### Phase C — Repository Layer

- [x] **Step 11**: P1-P3 `ports/` — repository, source and emitter protocols. Source protocols
      declare no write method (P-SEC-04 capability absence)
      *Serves*: US-ENB-02, NFR-SEC-14

- [x] **Step 12**: Database schema and migrations — A1 `schema.py` with all 18 tables, the §10.3
      integrity constraints as triggers and CHECKs, the 9 indexes; L2 `migrations/` runner with
      forward and reverse and a `schema_version` table
      *Serves*: US-ENB-01, US-TRC-01

- [x] **Step 13**: L1 `connection.py` and L3 `backup.py` — PRAGMA application with read-back
      assertion; backup via the online backup API, export, prune, restore
      *Serves*: US-ENB-01

- [x] **Step 14**: A2 `repositories.py` and `queries/` — 9 repositories over parameterised SQL,
      `unit_of_work()` context manager, cursor pagination with the 200-record cap, soft delete
      *Serves*: US-ENB-01, US-ENB-05

- [x] **Step 15**: `tests/fakes/` — shared in-memory implementations of every port, satisfying the
      contract-first integration approach for U2-U8
      *Serves*: US-ENB-06, Q5 of Units Generation

- [x] **Step 16**: Repository layer tests — schema constraints actually reject (no steps, no Jira
      key), migration up and down, PRAGMA assertion, backup and restore round-trip, pagination,
      soft delete
      *Serves*: US-ENB-01, US-ENB-06

- [x] **Step 17**: Repository layer summary → `.../code/repository-layer-summary.md`

### Phase D — API Layer (MCP Surface)

- [x] **Step 18**: M1 `server.py` and M2 `tools_read.py` — stdio server, Pydantic-validated tool
      registration, Result-to-response conversion, global handler, and the 16 read-tier tools
      *Serves*: US-ENB-02

- [x] **Step 19**: M2 `tools_write.py` — write-tier tool registration and the two U1-owned write
      tools (`unit_begin`, `unit_complete`). The remaining 18 write tools are registered by the
      units that own their services
      *Serves*: US-ENB-02

- [x] **Step 20**: MCP layer tests — schema validation rejects malformed input before any handler
      runs, no exception crosses the boundary, messages are sanitised, stdio only
      *Serves*: US-ENB-02, US-ENB-04

- [x] **Step 21**: API layer summary → `.../code/api-layer-summary.md`

### Phase E — Assembly and Documentation

- [x] **Step 22**: `composition.py` and L4 benchmark harness — the only module binding protocols to
      adapters; seeded 10,000-case corpus asserting both budgets and the query plan
      *Serves*: US-ENB-05

- [x] **Step 23**: Documentation and release artifacts — `README.md` (install, configure, run,
      rollback), restore procedure and rehearsal scenario (OD-03), release checklist with
      `pip-audit` and SBOM, and the code generation summary
      *Serves*: US-ENB-04, OD-02, OD-03, NFR-SEC-09

---

## 4. Not In This Unit

| Item | Reason |
|---|---|
| Frontend components | U1 has no UI. The system's only interface is the VS Code Copilot surface, which is configuration in U7 |
| Deployment artifacts (containers, IaC, pipelines) | NFR-POR-02 requires local operation; OD-02 chose git plus `uv sync`. The release checklist replaces deployment artifacts |
| Services S1-S10 | Owned by U2-U8. U1 provides the `unit_of_work` and port contracts they build on |
| External MCP client adapters (A3-A6) | Owned by U2 |
| Emitters (A7-A9) | Owned by U4, U5, U8 |

---

## 5. Scope

| Measure | Estimate |
|---|---|
| Source files | ~30 |
| Test files | ~14 |
| Configuration and docs | ~8 |
| Database tables | 18 |
| Constraints and triggers | 8 |
| Indexes | 9 |
| MCP tools registered | 16 read + 2 write |
| Property tests | 16 |

**This is the largest single code generation in the project.** U1 holds 20 of the system's 37
components plus 4 logical components, and every other unit is built against what it establishes.
Generation proceeds step by step through the 23 steps above, and I will report progress as phases
complete rather than only at the end.

---

## 6. Story Traceability

| Story | Steps |
|---|---|
| US-ENB-01 Schema and durability | 4, 7, 12, 13, 14, 16 |
| US-ENB-02 MCP server with typed tools | 1, 11, 18, 19, 20 |
| US-ENB-03 Observability and failure isolation | 2, 3 |
| US-ENB-04 Secrets and confidentiality | 2, 3, 20, 23 |
| US-ENB-05 Scale and performance | 5, 14, 22 |
| US-ENB-06 Test suite including PBT | 8, 9, 15, 16 |
| US-TRC-01 Mandatory Jira key | 4, 6, 12 |

Every U1 story is served by at least two steps. Stories are marked `[x]` when their functionality is
complete.

---

## 7. Verification at Completion

- [x] All 23 steps marked `[x]`
- [x] All 7 U1 stories marked `[x]`
- [x] No application code written under `aidlc-docs/`
- [x] `uv sync` resolves from the committed lockfile
- [x] Import-linter contracts pass — domain imports nothing outside stdlib and domain
- [x] Schema constraints demonstrably reject a case with no steps and a case with no Jira key
- [x] All 16 property tests present
- [x] No credential present in any generated file
- [x] Tests are generated but **not executed** — execution belongs to the Build and Test stage
