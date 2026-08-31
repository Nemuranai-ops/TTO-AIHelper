# NFR Design Patterns — U1 Core Platform

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U1 | **Stage**: NFR Design
**Version**: 1.0 | **Date**: 2026-08-29

Which patterns deliver the 45 U1 NFR requirements, and which were deliberately declined.

---

## 1. Resilience Patterns

### P-RES-01: Unit of Work

**Delivers**: U1-NFR-REL-01, U1-NFR-REL-05, NFR-REL-01

A context manager yields bound repositories, commits on clean exit, rolls back on any exception.
Repositories are unusable outside one.

```
with unit_of_work(db) as uow:
    uow.cases.upsert(case)
    uow.traces.add(link)
    uow.run_state.complete(lease)
# commit here, or rollback if anything raised
```

**Why this shape rather than explicit begin/commit**: it makes "repositories never open their own
transaction" a structural fact rather than a convention. A repository obtained outside a unit of
work has no connection to write through, so the rule cannot be broken by forgetting it. Rollback on
error needs no discipline from the caller — the context manager owns the error path.

**Nesting**: a nested `unit_of_work` joins the outer transaction rather than opening a savepoint.
Services never call other services (except the read-only gate check), so nesting should not arise;
joining rather than nesting means that if it ever does, the atomicity guarantee still holds.

### P-RES-02: Bounded Retry with Jittered Backoff

**Delivers**: U1-NFR-REL-02, U1-NFR-REL-03, NFR-REL-03, RESILIENCY-10

| Setting | Value |
|---|---|
| Attempts | 3 |
| Backoff | 1s, 2s, 4s |
| Jitter | Full jitter — uniform random in [0, backoff] |
| Retryable | Connection error, timeout, HTTP 429, HTTP 5xx |
| Never retried | HTTP 4xx authentication and validation failures |
| On exhaustion | Fail the unit, log the reason, continue the run |

**Full jitter rather than fixed backoff** because ingestion issues many requests in a burst.
Synchronised retries against a rate-limited Jira make the situation worse; jitter spreads them.

**Never retrying 4xx** matters as much as the retry itself. A 401 will not become a 200 on the
second attempt, and retrying it wastes the operator's time and may trip an account lockout.

### P-RES-03: Per-Resource Error Isolation

**Delivers**: U1-NFR-REL-04, NFR-REL-02, NFR-REL-04

Ingestion wraps each resource so its failure is recorded against that resource and the next one
proceeds. The run reports successes, skips and failures together.

**This is the one place the all-or-nothing transaction rule is deliberately relaxed** (see
`services.md`). At 3-10 repositories and hundreds of Jira issues, one unreachable source must not
discard an hour of successful retrieval.

### P-RES-04: Lease-Based Unit State

**Delivers**: U1-NFR-REL-05, U1-NFR-REL-06, FR-BAT-04

`unit_begin` issues a lease; `unit_complete` requires it. An uncompleted lease leaves the unit
`in-progress`, which `get_status` reports honestly on resume.

**The system does not silently resume from an unknown point.** An interrupted unit is reported as
interrupted and the operator decides whether to restart it (US-BAT-03 AC3). A stale lock is detected
and reported with recovery guidance rather than cleared automatically — clearing a lock that another
process still holds is how databases get corrupted.

---

## 2. Scalability Patterns

### P-SCL-01: Mandatory Filter with Capped Cursor Pagination

**Delivers**: U1-NFR-SCL-03, NFR-SCL-04

Every read tool requires at least one filter, returns at most **200 records**, and supplies an
opaque cursor when more exist. The cursor encodes the last-seen key and the filter set.

**The hard cap is the enforcement, not the filter.** A tool that *can* return 10,000 rows will
eventually be asked to, and NFR-SCL-04 would then be violated by a caller acting reasonably. The cap
makes the violation impossible rather than discouraged.

**Cursor rather than limit/offset** because rows are inserted during a run. Offset pagination skips
or repeats records when the underlying set grows between pages, which at 6,000 cases is a silent
correctness problem in review.

### P-SCL-02: Feature-Scoped Work

**Delivers**: NFR-SCL-04, C-12

Every write-tier operation is scoped to one feature. No tool accepts "all features". This bounds
both transaction size and the payload the agent must reason about in one turn.

---

## 3. Performance Patterns

### P-PRF-01: Bucketed Candidate Selection

**Delivers**: U1-NFR-PRF-01, U1-NFR-PRF-03, NFR-PRF-03

`bucket_key` = feature slug + test type + step count, indexed by `idx_case_bucket`. Similarity
comparison runs only against cases in the same bucket.

**This is the single pattern the performance budget depends on.** Pairwise comparison at 10,000
cases is 50 million operations. Bucketing reduces the candidate set to cases that could plausibly
match — typically tens — which is what makes the 200 ms budget reachable rather than aspirational.

Verified by `EXPLAIN QUERY PLAN` asserting index use, not by hoping the planner chooses it.

### P-PRF-02: Content-Hash Skip

**Delivers**: U1-NFR-PRF-04, NFR-PRF-04

`artefact.content_hash` is indexed. Re-ingestion compares the hash and skips unchanged content
without a network call.

**Database-resident only, no in-memory cache.** An indexed SQLite lookup on a local file is already
sub-millisecond. An in-memory layer would add an invalidation obligation in exchange for a saving
nothing needs.

### P-PRF-03: SQL Aggregation with Streamed Rendering

**Delivers**: U1-NFR-PRF-02, NFR-PRF-02

Reports aggregate in SQL; the emitter consumes a row iterator and writes incrementally. The full
result set is never materialised.

**Memory stays flat regardless of corpus size.** At 10,000 cases materialising into Python would
work; the pattern is chosen because it also works at 50,000, and because aggregation is what SQLite
is genuinely good at.

### P-PRF-04: Connection Configuration Asserted at Startup

**Delivers**: U1-NFR-PRF-01, and the referential rules generally

WAL journal mode, `foreign_keys = ON`, `busy_timeout` set — applied by the connection factory and
**asserted** immediately after.

**SQLite defaults `foreign_keys` off, and the failure is silent.** A schema whose foreign keys are
not enforced looks identical to one whose are, until inconsistent data appears months later. The
assertion converts a silent misconfiguration into a startup failure.

---

## 4. Security Patterns

### P-SEC-01: Two-Level Validation

**Delivers**: U1-NFR-SEC-03, NFR-SEC-03, SECURITY-05

| Level | Question answered | Mechanism |
|---|---|---|
| MCP boundary | Is this well-formed? | Pydantic v2 model per tool, before the handler runs |
| Domain | Is this valid? | D1 construction invariants, D7 business validation |

**The two are not redundant.** A well-formed test case with no Jira key passes Pydantic and must
fail D7. Boundary validation cannot express business rules; domain validation cannot protect against
a malformed payload reaching it. Each covers what the other cannot.

**Not validated at every layer.** Services and repositories trust their callers, because inside the
process the domain has already established validity and repeating the check would be repetition
rather than defence.

### P-SEC-02: Immutable Config with Secret Wrapping

**Delivers**: U1-NFR-SEC-01, NFR-SEC-01, SECURITY-12

Environment variables primary, OS credential store as override, resolved **once at startup** into a
frozen config object. Every credential is wrapped in `SecretStr`.

**The wrapper is the point.** `SecretStr.__repr__` and `__str__` return `**********`, so a
credential cannot reach a log line, an exception message, or a serialised payload by accident. This
makes NFR-SEC-06 hold under a future careless log statement rather than depending on nobody writing
one.

Startup fails naming any missing variable, rather than failing later as an obscure authentication
error.

### P-SEC-03: Message Sanitisation at the Boundary

**Delivers**: U1-NFR-SEC-08, NFR-SEC-08, SECURITY-09

Every `Result` message passes through `sanitise()` before crossing the MCP boundary: paths outside
the workspace are replaced, stack detail is stripped, secret patterns are redacted.

### P-SEC-04: Capability Absence

**Delivers**: U1-NFR-SEC-11, NFR-SEC-14, SECURITY-06

The P2 source protocols declare no write method. The read-only posture is enforced by there being
nothing to call.

**This is the strongest form of the pattern available.** A policy can be forgotten, a review can
miss a line, a test can be deleted. A method that does not exist cannot be invoked.

### P-SEC-05: Parameterised Queries Only

**Delivers**: U1-NFR-SEC-04, NFR-SEC-04, SECURITY-05

All SQL lives in dedicated query modules with bound parameters. No f-string or concatenation
anywhere in a query path.

---

## 5. Observability Patterns

### P-OBS-01: Correlation Propagation

**Delivers**: U1-NFR-OBS-01, NFR-OBS-01, RESILIENCY-05

A correlation id is minted per MCP tool call, bound to the logger, and carried through the unit of
work into every log line and metric.

### P-OBS-02: Independent Health Reporting

**Delivers**: U1-NFR-OBS-02, NFR-OBS-02, RESILIENCY-06

The health check reports database accessibility, schema version and each external MCP server
**separately**. One unreachable server does not read as total failure — the operator can see that
Jira is down while Bitbucket is fine, and choose to proceed with what works.

### P-OBS-03: Metrics on Unit Completion

**Delivers**: U1-NFR-OBS-03, NFR-OBS-03, RESILIENCY-07

Duration, artefacts consumed, cases produced and failures written to `unit_state.metrics` in the
same transaction as the state change, so metrics cannot disagree with the state they describe.

---

## 6. Maintainability Patterns

### P-MNT-01: Dependency Inversion via Protocols

**Delivers**: NFR-MNT-01, and the whole PBT surface

Services depend on protocols; `composition.py` binds concrete adapters at startup. One shared set of
in-memory fakes satisfies every protocol.

### P-MNT-02: Enforced Import Contracts

**Delivers**: U1-NFR-MNT-01, NFR-MNT-01

import-linter contracts fail the build when `domain` imports outside stdlib and `domain`, or when an
adapter imports a service.

**Without this the hexagonal boundary erodes quietly.** One convenient import from an adapter into
the domain, and the property tests need a database. By the time anyone notices, the invariants have
stopped being tested and nobody knows when they stopped.

### P-MNT-03: Pure Domain as Test Seam

**Delivers**: U1-NFR-MNT-03 to -05, PBT-02, PBT-03, PBT-07, PBT-08

D1-D8 need no construction, no fixtures, no database. Hypothesis runs the 16-property surface
directly against them.

---

## 7. Patterns Deliberately Not Used

Recorded so the omissions are decisions rather than oversights.

| Pattern | Why not |
|---|---|
| **Circuit breaker** | Guards a shared downstream against a stampede of concurrent callers. There is one operator, one process, sequential requests — the failure mode cannot occur. Retry plus per-resource isolation covers the failures that can |
| **Bulkhead / concurrency budgets** | Same reason: no concurrency to partition |
| **Connection pool** | One process, one operator. SQLite with WAL and a single connection per unit of work is simpler and avoids pool-exhaustion failure modes entirely |
| **Rate limiter** | The external MCP servers enforce their own limits, and P-RES-02 handles 429 correctly. A client-side limiter would need tuning against limits we do not control |
| **In-memory cache** | An indexed lookup on a local SQLite file is already sub-millisecond; a cache would add invalidation for no measurable gain |
| **Pre-computed summary tables** | Would make every write path responsible for summary consistency. SQL aggregation meets the 30-second budget without that obligation |
| **Event sourcing** | The audit trail requirement is satisfied by change records on mutation. Full event sourcing would be a substantially different data model for no additional requirement |
| **Async / concurrency** | Single-operator local process. Async would add concurrency semantics — and their bugs — for no throughput gain |
| **Retry on 4xx** | A 401 does not become a 200 on retry; retrying wastes time and can trip account lockout |

**The through-line**: most of these are correct patterns for a multi-tenant service under concurrent
load. U1 is a single-operator local process. Including them would add machinery, failure modes and
tuning surface without addressing any failure that can actually occur here.

---

## 8. Pattern-to-Requirement Coverage

| Requirement group | Delivered by |
|---|---|
| U1-NFR-REC-01 to -04 (recovery) | Backup manager component; P-RES-01 |
| U1-NFR-DIST-01 to -04 (distribution) | Migration runner component; tech stack lockfile |
| U1-NFR-REH-01 to -04 (rehearsal) | Backup manager; documented procedure |
| U1-NFR-ENC-01 to -04 (encryption) | P-SEC-02; connection factory; `.gitignore` |
| U1-NFR-SCL-01 to -04 | P-SCL-01, P-SCL-02, P-PRF-01 |
| U1-NFR-PRF-01 to -04 | P-PRF-01, P-PRF-02, P-PRF-03, P-PRF-04 |
| U1-NFR-SEC-01 to -12 | P-SEC-01 to P-SEC-05 |
| U1-NFR-REL-01 to -07 | P-RES-01 to P-RES-04; migration runner |
| U1-NFR-OBS-01 to -03 | P-OBS-01 to P-OBS-03 |
| U1-NFR-MNT-01 to -05 | P-MNT-01 to P-MNT-03 |
| U1-NFR-POR-01 to -03 | Tech stack decisions; benchmark harness CI matrix |

**All 45 U1 NFR requirements have a delivering pattern or component.**
