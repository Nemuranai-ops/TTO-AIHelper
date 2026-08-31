# Performance Test Instructions

**Project**: TTO Test Analyst Agent System (TAAS)
**Version**: 1.0 | **Date**: 2026-08-31

---

## Purpose

Validate every stated budget against a corpus at target scale. **23 benchmarks**, all
asserting a measured figure against a number written down before the code was.

---

## Run Them

```bash
uv run pytest tests/benchmark -m benchmark
```

**Expected**: `23 passed` in about 1.5 seconds.

They are marked so they can be excluded from the fast loop:

```bash
uv run pytest tests/ -m "not benchmark"     # 928 passed, 23 deselected
```

---

## No Load Generator, and Why

There is no JMeter script, no k6 run, and no concurrent-user target — because **TAAS
has no server and no concurrent users.**

| Typical performance testing assumes | TAAS |
|---|---|
| Requests per second | One operator, one tool call at a time |
| Concurrent users | One, by design — U1's single-writer lease |
| p95 response time under load | There is no load |
| Horizontal scaling | The corpus is one SQLite file on one workstation |

What matters instead is **whether an operation stays inside its budget as the corpus
grows**, which is what these benchmarks measure. Running a load generator against a
stdio MCP server would produce a number that describes nothing real.

---

## The Corpus They Run Against

`seed_corpus` builds **10,000 cases across 20 features**, with drawn rather than uniform
step counts and test types.

**The distribution is the point.** A uniform corpus puts every case in one bucket and
makes de-duplication look faster than it is; U4's benchmark goes further and crowds
2,000 cases into a single bucket deliberately, because that is what a busy feature
actually looks like.

---

## The Budgets, and What Was Measured

| Budget | Target | Measured | Headroom |
|---|---|---|---|
| Single-case retrieval | 200 ms | 0.60 ms | 330× |
| Duplicate selection, **crowded bucket** | 50 ms | **3.7 ms** | 13× |
| 200-case batch commit | 10 s | 0.04 s | 250× |
| One feature's views, 100 cases | 2 s | 0.18 s | 11× |
| Coverage build, per feature | 5 s | < 0.1 s | 50× |
| Playwright emission, one feature | 5 s | 0.003 s | 1,600× |
| Playwright emission, 150 features | 60 s | 0.07 s | 850× |
| Second emission writes zero files | 30 s | zero written | — |
| Structural verification, ~300 files | 10 s | 0.05 s | 200× |
| Reconciliation, 6,000 identifiers | 10 s | < 0.01 s | — |
| **Full report set, end to end** | **30 s** | **0.23 s** | **130×** |
| Single report | 5 s | 0.06 s | 80× |
| Traceability matrix, 12,000 links | 30 s | < 0.01 s | — |

**The duplicate-selection figure is the one to read carefully.** U1 reported 0.29 ms
against a synthetic corpus that spread evenly across buckets *because it was generated
to*. The 3.7 ms figure is against 2,000 candidates in one bucket, is 13× slower, and is
the honest one.

**The full report set is NFR-PRF-02**, provisioned at U1 and unexercised for seven
units. Measured end to end — query, render and write — at 10,000 cases.

---

## Two Benchmarks That Are Not About Speed

### `test_a_second_emission_writes_zero_files`

Filed under performance, and it is the **determinism assertion**. A regeneration over an
unchanged corpus must write nothing. A timestamp added to a template header would pass
every unit test comparing two renders in the same second and fail this one.

### `test_duplicate_selection_uses_the_index`

Asserts `EXPLAIN QUERY PLAN`, not a duration. **A timing test could not have caught the
defect it exists for**: SQLite chose an unselective index over the bucket index, and the
wrong plan is fast on a small corpus. The fix was a composite index; the guard is the
plan assertion.

---

## When a Benchmark Fails

The margins are wide — the tightest is 11×. A failure means something changed
structurally rather than gradually.

**Check the query plan first.** Two budget regressions in this project were the
optimiser choosing a different index after a schema change, not code becoming slower:

```bash
uv run python -c "
import sqlite3
from tto_testgen.adapters.sqlite import queries as q
conn = sqlite3.connect('.taas/taas.db'); conn.row_factory = sqlite3.Row
for row in conn.execute('EXPLAIN QUERY PLAN ' + q.CASE_BUCKET_CANDIDATES, {'bucket_key': 'x'}):
    print(dict(row))"
```

Then check whether an aggregation moved from SQL into Python. That is the single change
most likely to break a report budget, and it is why `U8-NFR-SCL-03` exists.

---

## Scaling Beyond the Target

The stated scale is medium: 3–10 repositories, 100–500 stories, 30–150 screens, ~6,000
cases. Benchmarks run at **10,000** to leave headroom.

If the corpus grows substantially past that, the first things to check are:

1. **`bucket_candidates`** — the only query whose cost depends on how cases cluster
   rather than on how many there are.
2. **The traceability matrix** — the largest read, deliberately uncapped, streamed.
3. **`existing_identifiers`** — a full scan of `test_case.id`, called once per batch.

None is close to its budget today. They are listed because they are the three whose
cost is a function of corpus size rather than of batch size.
