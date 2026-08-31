# Code Generation Plan — U3 Requirements and Coverage

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U3 | **Stage**: Code Generation (Part 1: Planning)
**Created**: 2026-08-30T09:46:00Z
**Status**: COMPLETE 2026-08-30 - all 15 steps executed

**This plan is the single source of truth for U3 Code Generation.**

---

## 1. Unit Context

### Stories (10)

| Story | Title | Release |
|---|---|---|
| US-TRQ-01 | Derive atomic testable requirements | R1 |
| US-TRQ-02 | Rate requirement risk | R2 |
| US-TRQ-03 | Identify edge cases and failure scenarios | R2 |
| US-COV-01 | Build the coverage model | R1 |
| US-COV-02 | Derive coverage depth from test design techniques | R2 |
| US-COV-03 | Forecast the yield before generation | R2 |
| US-COV-04 | Approve the baseline before generation | R1 |
| US-COV-05 | Apply risk-based coverage reduction | R3 |
| US-TRC-02 | Derive Jira keys from commit history | R2 |
| US-TRC-03 | Route untraceable behaviour to the gap report | R2 |

### Dependencies

U1, U7, U2 — all complete.

### Release depth

**R1 and R2 in this pass.** US-COV-05 is R3 and is **included**, because reduction
writes to `coverage_reduction`, which migration 004 creates. Deferring the code but
shipping the table would leave a table nothing writes, and returning for it later
means re-reading the whole unit's context for an afternoon's work.

That is the same judgement made for U2's Confluence and Figma adapters, and it is
worth being consistent about: R3 work is deferred when it needs something that does
not exist yet, not merely because it is labelled R3.

---

## 2. Code Location

```
src/tto_testgen/
  adapters/sqlite/migrations/m004_gaps_and_reductions.py
  adapters/commit_index.py              L8
  domain/atomicity.py                   heuristic, pure
  domain/coverage_hash.py               canonical-form hashing, pure
  services/requirements.py              S3
  services/coverage.py                  S4
  mcp/tools_u3.py                       4 tools
  adapters/sqlite/queries/__init__.py    + gap, reduction, coverage version
  adapters/sqlite/repositories.py        + GapRepository, ReductionRepository
tests/
  unit/test_domain_atomicity.py
  unit/test_coverage_hash.py
  integration/test_u3_services.py
  properties/test_u3_properties.py
```

Both new domain modules are **pure** — the atomicity heuristic and the hashing take
their input as arguments and return a value. That keeps them inside the import
contract and property-testable, which matters most for the hash: three of the ten U3
properties pin down exactly what "modifying an approved model" means, and the Test
Lead's approval rests on that definition.

---

## 3. Generation Steps

15 steps.

### Phase A — Foundation

- [x] **Step 1**: Migration 004 — `gap` and `coverage_reduction` tables, two columns
      on `coverage_item`, indexes, with a tested reverse
      *Serves*: US-TRC-03, US-COV-05

- [x] **Step 2**: Queries and repositories — `GapRepository`, `ReductionRepository`,
      coverage version lookup
      *Serves*: US-TRC-03, US-COV-01, US-COV-05

### Phase B — Pure Domain

- [x] **Step 3**: `domain/coverage_hash.py` — canonical form, pinned separators
      *Serves*: US-COV-01, US-COV-04

- [x] **Step 4**: `domain/atomicity.py` — the conservative heuristic and its
      suspected-split reporting
      *Serves*: US-TRQ-01

- [x] **Step 5**: Unit tests for both, including the three hash properties as
      examples before they become properties
      *Serves*: US-TRQ-01, US-COV-01

### Phase C — Adapter

- [x] **Step 6**: L8 `adapters/commit_index.py` — per-file caching, bounds,
      `BoundsReport` distinguishing skipped from truncated
      *Serves*: US-TRC-02

- [x] **Step 7**: L8 unit tests against a stub Bitbucket adapter
      *Serves*: US-TRC-02

### Phase D — Services

- [x] **Step 8**: S3 `services/requirements.py` — risk signal gathering, validation,
      key resolution, gap routing, all-or-nothing batches
      *Serves*: US-TRQ-01 to US-TRQ-03, US-TRC-02, US-TRC-03

- [x] **Step 9**: S4 `services/coverage.py` — build, hash, version, forecast,
      approval delegation, reduction
      *Serves*: US-COV-01 to US-COV-05

- [x] **Step 10**: 4 write tools — `requirements_upsert`, `coverage_build`,
      `coverage_approve`, `coverage_reduce`
      *Serves*: all 10 stories

- [x] **Step 11**: S3 integration tests
      *Serves*: US-TRQ-01 to -03, US-TRC-02, US-TRC-03

- [x] **Step 12**: S4 integration tests, including approval invalidation
      *Serves*: US-COV-01 to US-COV-05

- [x] **Step 13**: The 10 U3 property tests
      *Serves*: all 10 stories

### Phase E — Completion

- [x] **Step 14**: Composition wiring and a benchmark for the build budget
      *Serves*: U3-NFR-PRF-01, -02

- [x] **Step 15**: Verification and the code generation summary

---

## 4. Not In This Unit

| Item | Reason |
|---|---|
| Test case generation | U4 reads the approved model; U3 writes it |
| Gap *reporting* | U8. U3 writes gaps; U8 renders them |
| Live UI model | Deferred from U2, still agent work |

---

## 5. Scope

| Measure | Estimate |
|---|---|
| New source files | 7 |
| Modified | 3 |
| Test files | 4 |
| Property tests | 10 |
| MCP tools added | 4 |

---

## 6. Verification at Completion

- [x] All 15 steps `[x]`
- [x] All 10 U3 stories `[x]`
- [x] Migration 004 applies and reverses
- [x] Import contracts pass — no coverage arithmetic or risk formula in U3
- [x] All 10 U3 properties passing, including the three hash properties
- [x] The Test Lead restriction is delegated, not re-implemented
- [x] U7's Agent Layer check passes with 4 more tools registered
- [x] The full U1, U7 and U2 suites still pass
- [x] Coverage build meets the 5-second per-feature budget
