# NFR Design Plan — U1 Core Platform

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U1 | **Stage**: NFR Design
**Created**: 2026-08-29T10:26:00Z
**Status**: APPROVED 2026-08-29T10:40:00Z - all recommendations accepted

---

## Context

NFR Requirements produced 45 unit-level requirements with measurement points. This stage decides
**which patterns and logical components deliver them**.

The stack is fixed: Python 3.11+, `uv`, official `mcp` SDK, Pydantic v2, stdlib `sqlite3`, Jinja2,
pytest plus Hypothesis, import-linter.

**What is genuinely open here** is narrower than at earlier stages, because Application Design
already chose the hexagonal structure and Functional Design already specified the algorithms. What
remains is how transactions, retries, pagination, caching and secrets are *shaped* in code — seven
decisions, below.

**A note on proportion.** Several standard resilience patterns — circuit breakers, bulkheads,
connection pools, rate limiters — exist for systems under concurrent load from many callers. U1 is
a single-operator local process. Where a pattern would add machinery without addressing a real
failure mode here, I have said so and offered the simpler option, rather than including it because
it appears on a list.

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis. Tell me when done.

---

## Question 1 — Resilience: transaction shape

Services own transaction boundaries (Application Design Q5). How should that be expressed?

A) **Unit-of-Work context manager.** `with unit_of_work() as uow:` yields bound repositories and
commits on clean exit, rolls back on any exception. Repositories are unusable outside one.
**(Recommended — it makes "repositories never open their own transaction" structurally true rather
than a convention, and rollback-on-error needs no discipline from the caller)**

B) **Explicit begin/commit/rollback** in each service method. Maximum visibility, and every method
must remember the error path.

C) **Decorator** — `@transactional` on service methods. Terse, but the boundary becomes invisible at
the call site and nested calls get ambiguous.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 2 — Resilience: failure containment

Beyond bounded retry (3 attempts, 1s/2s/4s with jitter), what containment does U1 need?

A) **Retry plus per-resource error isolation, no circuit breaker.** Each ingestion resource is
wrapped so its failure is recorded and the next resource proceeds. **(Recommended — a circuit
breaker protects a shared downstream from a stampede of concurrent callers. There is one operator,
one process, and sequential requests; the failure mode it guards against cannot occur here)**

B) **Retry plus a circuit breaker** per external MCP server — opens after N consecutive failures,
half-opens after a cooldown.

C) **Retry plus bulkhead** — separate concurrency budgets per external server.

D) **Retry only** — no isolation wrapper; a failing resource stops the ingestion run.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 3 — Scalability: bounding read results

NFR-SCL-04 forbids any operation requiring the whole corpus in a context window. How do read tools
enforce that?

A) **Mandatory filter plus cursor pagination with a hard cap.** Every read tool requires at least
one filter, returns at most 200 records, and supplies an opaque cursor when more exist.
**(Recommended — the hard cap is what actually enforces NFR-SCL-04; a tool that can return 10,000
rows will eventually be asked to)**

B) **Limit/offset pagination** — simpler, but drifts when rows are inserted between pages.

C) **Cap with no pagination** — return the first N and a truncation flag. Simple, and the remainder
is unreachable.

D) **No cap; rely on filters** — smallest machinery, and the constraint becomes advisory.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 4 — Performance: caching

NFR-PRF-04 requires skip-if-unchanged by content hash.

A) **Database-resident only.** The hash lives on `artefact`; skip-if-unchanged is an indexed lookup.
No in-memory cache. **(Recommended — an indexed SQLite lookup is already sub-millisecond, and an
in-memory layer would add an invalidation problem in exchange for a saving nothing needs)**

B) **Database plus an in-memory LRU** for hot lookups within a run.

C) **Database plus a persistent on-disk cache** of fetched external content, separate from the
artefact table.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 5 — Performance: report generation

NFR-PRF-02 sets 30 seconds for full report generation at 10,000 cases.

A) **Aggregate in SQL; stream rows to the emitter.** The query does the arithmetic; the renderer
never materialises the full result set. **(Recommended — it keeps memory flat regardless of corpus
size, and the aggregation is what SQLite is good at)**

B) **Materialise into Python, aggregate in code.** Easier to unit-test the arithmetic, at the cost
of holding the corpus in memory.

C) **Pre-computed summary tables** maintained on write. Fastest reads, and it introduces a
consistency obligation on every write path.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 6 — Security: credential handling

A) **Environment variables as the primary source, OS credential store as an optional override,
resolved once at startup into an immutable config object; `SecretStr` wrappers so a value cannot be
logged or serialised by accident.** **(Recommended — the `SecretStr` wrapper is what makes
NFR-SEC-06 hold under a future careless log line, rather than depending on nobody writing one)**

B) **Environment variables only** — simplest, and matches the `.env.example` already planned.

C) **OS credential store only** — better at rest, harder in CI and on first setup.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 7 — Security: validation placement

NFR-SEC-03 requires typed validation before any logic runs.

A) **Validate at the MCP boundary, and re-assert invariants in the domain.** Pydantic validates
shape and type at the edge; D1 constructors and D7 re-check the business invariants.
**(Recommended — the two checks answer different questions. The boundary asks "is this
well-formed?", the domain asks "is this valid?", and a well-formed test case with no Jira key passes
the first and must fail the second)**

B) **Boundary only** — trust the domain to receive valid input. Less code, and the domain becomes
unsafe to call from anywhere else, including tests.

C) **Every layer** — validate at boundary, service, domain and repository. Thorough, and mostly
repetition.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 8 — Logical Components

Which supporting components should U1 provide beyond the 20 already defined?

A) **Four: a connection factory (applying WAL, `foreign_keys=ON`, `busy_timeout` and asserting
them), a migration runner (forward and reverse, versioned), a backup manager (pre-operation backup,
post-unit export, 10-file retention), and a benchmark harness (synthetic 10,000-case corpus,
asserts both budgets).** **(Recommended — each maps to a specific NFR that is otherwise unowned:
the foreign-key assertion, U1-NFR-DIST-04's reverse migrations, OD-01's recovery point, and the
Question 12 verification decision)**

B) **Three** — the same without the benchmark harness; measure manually at Build and Test.

C) **Five** — add a rate limiter for external MCP calls.

D) **Two** — connection factory and migration runner; treat backup and benchmarking as operational
scripts outside the component model.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

# Execution Checklist

## Phase 1: Pattern Selection

- [x] 1.1 Specify the resilience patterns: transaction shape, retry, error isolation
- [x] 1.2 Specify the scalability patterns: result bounding, pagination, work scoping
- [x] 1.3 Specify the performance patterns: indexing, bucketing, caching, streaming aggregation
- [x] 1.4 Specify the security patterns: validation placement, secret handling, sanitisation, read-only enforcement
- [x] 1.5 Specify the observability patterns: correlation propagation, metric capture, health probing
- [x] 1.6 Specify the maintainability patterns: dependency inversion, import contracts, test seams
- [x] 1.7 Record patterns deliberately NOT used, with reasons
- [x] 1.8 Map every pattern to the NFR it delivers
- [x] 1.9 Write `nfr-design-patterns.md`

## Phase 2: Logical Components

- [x] 2.1 Define the supporting components chosen in Question 8
- [x] 2.2 Define each component's responsibility and interface
- [x] 2.3 Place each within the hexagonal rings
- [x] 2.4 Define their interaction with the 20 existing components
- [x] 2.5 Define configuration surface and defaults
- [x] 2.6 Verify no new component violates the dependency rule
- [x] 2.7 Write `logical-components.md`

## Phase 3: Validation

- [x] 3.1 Verify all 45 U1 NFR requirements have a delivering pattern or component
- [x] 3.2 Verify the design introduces no cloud or hosted dependency (NFR-POR-02)
- [x] 3.3 Verify Security Baseline compliance at design level
- [x] 3.4 Verify Resiliency Baseline compliance at design level
- [x] 3.5 Verify PBT partial-mode compliance is unaffected by the patterns chosen
- [x] 3.6 Validate content per `common/content-validation.md`
- [x] 3.7 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `aidlc-docs/construction/u1-core-platform/nfr-design/nfr-design-patterns.md`
- [x] `aidlc-docs/construction/u1-core-platform/nfr-design/logical-components.md`
