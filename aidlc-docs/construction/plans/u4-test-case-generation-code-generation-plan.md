# Code Generation Plan — U4 Test Case Generation

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U4 | **Stage**: Code Generation (Part 1: Planning)
**Created**: 2026-08-30T12:44:00Z
**Status**: COMPLETE 2026-08-30 — all 18 steps executed

**This plan is the single source of truth for U4 Code Generation.**

---

## 1. Unit Context

### Stories (7)

| Story | Title | Release |
|---|---|---|
| US-TCG-01 | Generate structured test cases with mandatory steps | R1 |
| US-TCG-02 | Specify synthetic test data with equivalence classes | R1 |
| US-TCG-03 | Detect duplicate and near-duplicate cases | R2 |
| US-TCG-04 | Classify automatability | R2 |
| US-TCG-05 | Derive corpus volume without padding | R2 |
| US-TCG-06 | Publish reviewable sharded views with tags | R1 |
| US-TRC-04 | Produce the bidirectional traceability matrix | R2 |

### Dependencies

U1, U7, U2, U3 — all complete. **U4 is the first unit that consumes all four.**

### Release depth

**All seven stories in this pass.** There is no R3 work in U4, and the R1/R2 split
does not survive contact with the code: US-TCG-01 cannot be built without US-TCG-03's
duplicate check, because the duplicate check is stage D of the same validation
sequence. Splitting them would mean shipping a batch path with a hole in it and
returning to thread the hole later.

---

## 2. What Makes U4 Different

U4 is the largest unit and the one with the least new logic. Every algorithm it needs
already exists: D1 constructs cases, D3 resolves keys and builds matrices, D4 finds
duplicates, D5 allocates identifiers, D6 classifies automatability, D7 validates.

**U4 owns the order they run in, and what must be true when they do.** That makes
U4-NFR-MNT-03 the requirement most at risk during this stage — six domain components
is six opportunities for a convenience copy. The import contracts are the defence, and
they are checked at step 15 rather than trusted.

Two things are genuinely new: **L9**, which is policy nobody has written yet, and
**L10**, which is format.

---

## 3. Code Location

```
src/tto_testgen/
  adapters/sqlite/migrations/m005_emitted_view.py   NEW  migration 005
  adapters/sqlite/queries/__init__.py               MOD  + view, volume, matrix queries
  adapters/sqlite/repositories.py                   MOD  + EmittedViewRepository,
                                                         stream_links, planned_vs_generated
  ports/repositories.py                             MOD  + EmittedViewRepository protocol,
                                                         stream_links on TraceRepository
  domain/privacy.py                                 NEW  L9, pure
  domain/validation.py                              MOD  screening into stage B
  adapters/view_renderer.py                         NEW  L10
  services/generation.py                            NEW  S5
  mcp/tools_u4.py                                   NEW  3 tools
  mcp/tools_read.py                                 MOD  trace_matrix streams
  composition.py                                    MOD  wire L9, L10, S5
tests/
  unit/test_domain_privacy.py                       NEW
  unit/test_view_renderer.py                        NEW
  integration/test_u4_generation.py                 NEW
  properties/test_u4_properties.py                  NEW
  benchmark/test_performance_budgets.py             MOD  + 4 U4 budgets
  fakes/repositories.py                             MOD  + view repo, stream_links
```

`domain/privacy.py` is **pure** — it takes a value and returns a finding. That keeps it
inside `domain-is-pure` and makes the four L9 properties testable without a database,
which matters because those properties are the whole of U4-NFR-SEC-01's assurance.

---

## 4. Generation Steps

18 steps.

### Phase A — Foundation

- [x] **Step 1**: Migration 005 — `emitted_view` table, unique path, feature index,
      with a tested reverse
      *Serves*: US-TCG-06, U4-NFR-REL-07

- [x] **Step 2**: `EmittedViewRepository` port and SQLite implementation; `stream_links`
      on `TraceRepository`; the planned-vs-generated aggregation query
      *Serves*: US-TCG-05, US-TCG-06, US-TRC-04

- [x] **Step 3**: Fakes updated — view repository and `stream_links`, so the shared
      fake stays a faithful stand-in
      *Serves*: all 7

### Phase B — Pure Domain (L9)

- [x] **Step 4**: `domain/privacy.py` — five patterns, the synthetic allow-list, the
      Luhn check, `PrivacyFinding` carrying `permitted_form`
      *Serves*: U4-NFR-SEC-01, -02

- [x] **Step 5**: Screening wired into D7 validation stage B, beside the structural
      case rules
      *Serves*: U4-NFR-SEC-01

- [x] **Step 6**: L9 unit tests — each pattern, each allow-listed form, and the
      16-digit order reference that must **not** be rejected
      *Serves*: U4-NFR-SEC-01, -02

### Phase C — Adapter (L10)

- [x] **Step 7**: `adapters/view_renderer.py` — `render_markdown`, `render_yaml`,
      deterministic and I/O-free
      *Serves*: US-TCG-06, U4-NFR-MNT-01, -02, U4-NFR-SEC-03

- [x] **Step 8**: `emit` — the three-way comparison, path validation, manifest
      *Serves*: US-TCG-06, U4-NFR-REL-04, U4-NFR-PRF-06, U4-NFR-SEC-05

- [x] **Step 9**: L10 unit tests — byte-stability across two renders, hand-edit
      detected, unchanged distinguished from written, traversal refused
      *Serves*: US-TCG-06, U4-NFR-REL-04, U4-NFR-MNT-01

### Phase D — Service (S5)

- [x] **Step 10**: S5 stages A–D — gate, cap, construction, validation, traceability,
      duplicates; every failure collected
      *Serves*: US-TCG-01, US-TCG-02, US-TCG-03

- [x] **Step 11**: S5 stages E–F — classification, deferred allocation, stable
      identifier resolution
      *Serves*: US-TCG-04, U4-NFR-REL-02, -05, -06

- [x] **Step 12**: S5 commit — ordered bulk insert, sentinel last, gap recording,
      volume report
      *Serves*: US-TCG-05, U4-NFR-PRF-01, U4-NFR-REL-01

- [x] **Step 13**: Streamed matrix construction; `trace_matrix` moved to `stream_links`
      and both formats emitted
      *Serves*: US-TRC-04, U4-NFR-SCL-04, -05

### Phase E — Interface

- [x] **Step 14**: 3 MCP tools — `testcases_upsert`, `views_emit`, `volume_report`
      *Serves*: all 7

- [x] **Step 15**: Chat mode registration so no tool is unreachable, and U7's Agent
      Layer consistency check re-run
      *Serves*: FR-AGT-05

### Phase F — Verification

- [x] **Step 16**: Integration tests — the full batch path, rollback leaving no
      identifier allocated, regeneration keeping identifiers
      *Serves*: US-TCG-01 to -06

- [x] **Step 17**: The 10 U4 property tests, including the four L9 properties
      *Serves*: all 7

- [x] **Step 18**: Benchmarks, composition wiring, verification and the summary
      *Serves*: U4-NFR-PRF-01 to -06

---

## 5. The Four Benchmarks

| Budget | Target | Why it might fail |
|---|---|---|
| 200-case batch commit at 6,000 cases | < 10 s | 1,600 rows; the reason for P-U4-02 |
| Duplicate candidate selection | < 50 ms | **Real bucket skew, not synthetic** |
| One feature's views at 100 cases | < 2 s | Rendering plus two hashes |
| Matrix at 6,000 cases | < 30 s | The largest read in the system |

**The second is the one I expect to be interesting.** U1 measured 0.29 ms selecting 8
candidates from 10,000 synthetic rows, which distributed evenly across buckets because
they were generated to. A real feature will crowd one bucket, and the benchmark is
written to build that skew deliberately rather than to reproduce U1's flattering
distribution.

---

## 6. Not In This Unit

| Item | Reason |
|---|---|
| Playwright emission | U5. U4 classifies automatability; U5 acts on it |
| Gap and volume *reporting* | U8 renders; U4 records |
| The handover package | U6 |
| Live locator verification | Agent work through Playwright MCP, deferred from U2 |

---

## 7. Scope

| Measure | Estimate |
|---|---|
| New source files | 5 |
| Modified | 6 |
| Test files | 4 new, 2 modified |
| Property tests | 10 |
| MCP tools added | 3 |
| Migration | 005 |

---

## 8. Verification at Completion

- [x] All 18 steps `[x]`
- [x] All 7 U4 stories `[x]`
- [x] Migration 005 applies and reverses
- [x] Import contracts pass — **no similarity, classification or identifier logic in U4**
- [x] All 10 U4 properties passing
- [x] A rejected batch allocates nothing — asserted, not assumed
- [x] A hand-edited view survives a re-emission
- [x] Two renders of unchanged content are byte-identical
- [x] U7's Agent Layer check passes with 3 more tools registered
- [x] The full U1, U7, U2 and U3 suites still pass
- [x] All four U4 budgets met
