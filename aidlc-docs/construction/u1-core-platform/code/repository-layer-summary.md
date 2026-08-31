# Repository Layer Summary — U1 Core Platform

**Phase**: CONSTRUCTION | **Unit**: U1 | **Stage**: Code Generation (Steps 11-16)
**Date**: 2026-08-29

---

## Files Created

| Path | Component | Purpose |
|---|---|---|
| `src/tto_testgen/ports/repositories.py` | P1 | 10 repository protocols, `Page`, `UnitOfWork` |
| `src/tto_testgen/ports/sources.py` | P2 | 5 read-only source protocols |
| `src/tto_testgen/ports/emitters.py` | P3 | 3 emitter protocols |
| `src/tto_testgen/adapters/sqlite/migrations/m001_initial.py` | A1 | 18 entity tables, 8 constraints, 3 triggers, 9 indexes |
| `src/tto_testgen/adapters/sqlite/migrations/__init__.py` | L2 | Migration registry |
| `src/tto_testgen/adapters/sqlite/schema.py` | A1, L2 | Migration runner, statement splitter, reversibility check |
| `src/tto_testgen/adapters/sqlite/connection.py` | L1 | PRAGMA application with read-back assertion |
| `src/tto_testgen/adapters/sqlite/backup.py` | L3 | Online-API backup, portable export, prune, restore |
| `src/tto_testgen/adapters/sqlite/queries/__init__.py` | A2 | Parameterised SQL, no DELETE against a business entity |
| `src/tto_testgen/adapters/sqlite/repositories.py` | A2 | 10 repositories, `unit_of_work()`, cursor pagination |
| `tests/fakes/repositories.py` | — | In-memory P1 implementations, shared across all units |
| `tests/fakes/sources.py` | — | In-memory P2 implementations |
| `tests/integration/test_sqlite_repositories.py` | — | 37 integration tests |
| `tests/unit/test_ports_readonly.py` | — | Guards the read-only posture structurally |

---

## Verification

| Check | Result |
|---|---|
| Full suite | **196 passing** |
| Import contracts | 3 of 3 kept |
| Schema | 18 entity tables + `schema_version` + integrity sentinel |
| Constraints | 8 CHECK/UNIQUE, 3 triggers, all demonstrably rejecting |
| Indexes | 9, with `idx_case_bucket` confirmed in the query plan |
| Migrations | Forward and reverse round-trip verified |
| Fakes | 15 of 15 satisfy their protocol at runtime |
| Parameterised SQL | 0 string-built fragments in any query path |
| Hard deletes | 0 against business entities |

---

## Two Defects Found by the Tests

Both were found because a test asserted the mechanism rather than the outcome. Both
would have shipped otherwise, and neither would have failed loudly.

### The query planner chose the wrong index

`test_bucket_candidates_use_the_index` asserts `EXPLAIN QUERY PLAN`, not elapsed
time. It failed: with separate indexes on `bucket_key` and `is_obsolete`, SQLite
chose `idx_case_obsolete` — which is almost entirely unselective, since nearly every
row has `is_obsolete = 0`. De-duplication would have scanned the active corpus
instead of the bucket.

The index is now composite on `(bucket_key, is_obsolete)`, leading with the
selective column. The plan confirms `SEARCH test_case USING INDEX idx_case_bucket
(bucket_key=? AND is_obsolete=?)`.

**This is exactly the failure a timing test cannot catch.** On a small corpus the
wrong plan is fast, so the test passes; the cliff arrives at volume, in production,
as an unexplained slowdown.

The fix amends migration 001 rather than adding 002. Nothing has been deployed and
no database exists, so shipping the defect plus its correction as two versions would
be following the versioning rule past the point where it means anything.

### `executescript()` silently discards the transaction

The migration runner originally wrapped `conn.executescript(migration.up)` in an
explicit `BEGIN`/`COMMIT`. `executescript()` issues an implicit `COMMIT` before it
runs, so the `BEGIN` was discarded and the later `COMMIT` failed with "cannot commit
— no transaction is active".

Statements are now executed individually inside the transaction, via a splitter that
tracks `BEGIN ... END` depth so trigger bodies stay whole. Without that depth
tracking, a naive split on `;` would tear the three triggers apart — and the
traceability rule would lose its storage-layer enforcement without anything failing.

---

## Behaviours Worth Recording

**The integrity sentinel exists because CHECK cannot span tables.** "A case must
have at least one step" and "a case must carry a Jira key" are cross-table
conditions. They are enforced by triggers on a sentinel insert that the repository
performs after writing steps and links. A case violating either aborts the enclosing
transaction, so the storage layer holds the rule even if a future code path bypasses
D7 entirely.

**The fakes enforce the same invariants as production.** `FakeTestCaseRepository`
raises on a case with no steps or no Jira key. A fake that accepts what production
rejects teaches U2-U8 the wrong lesson and defers the bug to integration, which is
the failure contract-first testing exists to prevent.

**Nested units of work join rather than nest.** A savepoint would let an inner block
commit independently of a failing outer one. Joining keeps the atomicity guarantee
whole. Services do not call other services, so this should not arise — the behaviour
is defined so that if it ever does, it is safe rather than surprising.

**Cursor pagination rather than limit/offset.** Rows are inserted during a run, and
offset pagination skips or repeats records when the underlying set grows between
pages. At 6,000 cases that is a silent correctness problem during review, not a
visible error.

**The page cap is enforced, not advised.** `query(limit=10_000)` returns at most
200. NFR-SCL-04 would otherwise be violated by a caller acting entirely reasonably.

---

## Story Progress

| Story | Status |
|---|---|
| US-ENB-01 Schema and durability | **Complete** — schema, migrations, backup, export, restore |
| US-TRC-01 Mandatory Jira key | **Complete** — enforced in D3, D7 and as a database trigger |
| US-ENB-06 Test suite | **Complete** — 196 tests including 16 properties |
