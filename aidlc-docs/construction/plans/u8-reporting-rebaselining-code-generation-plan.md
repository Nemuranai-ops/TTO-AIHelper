# Code Generation Plan — U8 Reporting and Re-baselining

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U8 | **Stage**: Code Generation (Part 1: Planning)
**Created**: 2026-08-31T10:15:00Z
**Status**: COMPLETE 2026-08-31 — all 18 steps executed

**This plan is the single source of truth for U8 Code Generation.**

---

## 1. Unit Context

### Stories (6)

| Story | Title | Release |
|---|---|---|
| US-RPT-01 | Produce the coverage report | R2 |
| US-RPT-02 | Produce the gap report | R2 |
| US-RPT-03 | Produce the automation report | R2 |
| US-DLT-01 | Detect changes since the last run | R3 |
| US-DLT-02 | Map changes to affected artefacts and classify them | R3 |
| US-DLT-03 | Retire obsolete cases without deleting them | R3 |

### Dependencies

U1 through U6 — all complete. U8 reads all of them.

### Release depth

**All six.** The three R3 delta stories cannot be deferred: `change_event`,
`is_obsolete` and D8 have been carried since U1 for this unit, and shipping the
reports without the delta pipeline would leave five entities written by nothing.

---

## 2. A Defect Found While Planning This Stage

Reading `SqliteGapRepository` ahead of writing the gap report surfaced a real fault in
U4's approved code: `services/generation.py` called `gaps.add(category, subject, ...)`
against a repository whose signature is `add(gap: dict, run_id)`. Confirmed by
execution, not inference.

**Two coincidences hid it**, and the second is the instructive one:

1. A duplicate finding always adds a rejection, and a rejected batch returns before the
   gap loop — so that path is unreachable.
2. **The shared fake had been written to match the caller rather than the port**, so it
   agreed with the mistake.

Fixed before starting this stage: S5 passes a dict, the unreachable branch is gone with
a comment saying why, `FakeGapRepository` now mirrors the real one, and two integration
tests cover both paths. **881 tests pass.**

The lesson is recorded in the fake's docstring: *a fake written to fit its caller is
not a stand-in for anything.*

---

## 3. Code Location

```
src/tto_testgen/
  adapters/sqlite/migrations/m007_run_baseline.py   NEW  two columns on `run`
  adapters/report_renderer.py                       NEW  L16
  adapters/change_detector.py                       NEW  L17
  services/reporting.py                             NEW  S8 + the section registry
  services/delta.py                                 NEW  S9 + advance_baseline
  mcp/tools_u8.py                                   NEW  3 tools
  adapters/sqlite/queries/__init__.py               MOD  report aggregations
  adapters/sqlite/repositories.py                   MOD  baseline read/write, gap reads
  ports/repositories.py                             MOD
  platform/config.py                                MOD  3 keys
  composition.py                                    MOD  wire L16, L17, S8, S9
tests/
  unit/test_report_renderer.py                      NEW
  unit/test_change_detector.py                      NEW
  integration/test_u8_reporting.py                  NEW
  integration/test_u8_delta.py                      NEW
  properties/test_u8_properties.py                  NEW
  benchmark/test_performance_budgets.py             MOD  + 3 budgets
```

`advance_baseline` is a **module-level function**, not a method, so the property test
can exercise it without constructing a service — which matters because it is the
function whose failure would be invisible.

---

## 4. Generation Steps

18 steps.

### Phase A — Foundation

- [x] **Step 1**: Migration 007 — `head_commits` and `jira_watermark` on `run`, with a
      tested reverse
      *Serves*: US-DLT-01

- [x] **Step 2**: Report aggregation queries — coverage per feature and test type, gap
      by category including empty ones, automation with deferral reasons
      *Serves*: US-RPT-01 to -03

- [x] **Step 3**: Repository and port updates — baseline read and write, gap reads,
      run history
      *Serves*: US-DLT-01, US-RPT-02

- [x] **Step 4**: Config keys — report root, formats, change cap
      *Serves*: US-RPT-01, US-DLT-01

### Phase B — Rendering

- [x] **Step 5**: L16 `report_renderer.py` — Markdown, deterministic, derivation per
      figure
      *Serves*: US-RPT-01 to -03

- [x] **Step 6**: L16 CSV — `csv.writer`, `lineterminator` pinned
      *Serves*: US-RPT-01, FR-RPT-03

- [x] **Step 7**: L16's last-line scan — L9 and L13 over rendered output
      *Serves*: U8-NFR-SEC-03

- [x] **Step 8**: L16 unit tests — byte-stability, a comma in a statement, a section
      marked not-available
      *Serves*: US-RPT-01 to -03

### Phase C — Reporting

- [x] **Step 9**: The section registry — name, precondition, query, producing stage,
      derivation
      *Serves*: US-RPT-01 to -03

- [x] **Step 10**: S8 `reporting.py` — iterate the registry, render, emit
      *Serves*: US-RPT-01 to -03

- [x] **Step 11**: S8 integration tests, including a report on an empty corpus
      *Serves*: US-RPT-01 to -03

### Phase D — Delta

- [x] **Step 12**: L17 `change_detector.py` — per-source detection under isolation,
      `DetectionResult` carrying `unavailable_sources`
      *Serves*: US-DLT-01

- [x] **Step 13**: `advance_baseline` and its guard
      *Serves*: U8-NFR-REL-04

- [x] **Step 14**: S9 `delta.py` — edges, D8 classification, retirement, the report
      *Serves*: US-DLT-01 to -03

- [x] **Step 15**: S9 integration tests — a partial run does not advance, retirement
      touches only three columns, `requires-update` is untouched
      *Serves*: US-DLT-01 to -03

### Phase E — Interface and Verification

- [x] **Step 16**: 3 MCP tools — `reports_generate`, `delta_detect`, `delta_retire`;
      chat mode registration; Agent Layer check
      *Serves*: all 6

- [x] **Step 17**: The 12 U8 properties, three of them on the baseline guard
      *Serves*: all 6

- [x] **Step 18**: Benchmarks, composition wiring, verification and the summary
      *Serves*: U8-NFR-PRF-01 to -04

---

## 5. The Three Benchmarks

| Budget | Target | Why it might fail |
|---|---|---|
| Full report set at 6,000 cases, **end to end** | < 30 s | **NFR-PRF-02, unexercised since U1** |
| Any single report at 6,000 cases | < 5 s | The one run repeatedly |
| Impact mapping, 6,000 cases and 500 changes | < 10 s | Edge construction per change |

**The first is the project NFR that has waited eight units.** U1 measured one
aggregation at 0.003 s against synthetic rows; this measures the whole report — query,
render and write — over a real corpus.

---

## 6. Not In This Unit

| Item | Reason |
|---|---|
| Creating a requirement or a case | **No such method on S9.** A delta run re-enters at U3 |
| Deleting anything | No delete method exists, and none is added |
| Rebuilding the traceability matrix | U4 owns it; U8 renders it |
| Pushing reports anywhere | U6's boundary, and the same reasoning |

---

## 7. Scope

| Measure | Estimate |
|---|---|
| New source files | 6 |
| Modified | 5 |
| Test files | 5 new, 1 modified |
| Property tests | 12 |
| MCP tools added | 3 |
| Migration | 007 |

---

## 8. Verification at Completion

- [x] All 18 steps `[x]`
- [x] All 6 U8 stories `[x]`
- [x] Migration 007 applies and reverses
- [x] Five import contracts pass — no classification logic in U8
- [x] All 12 U8 properties passing
- [x] **A partial delta run does not advance the baseline** — asserted over every
      combination of source outcomes
- [x] Retirement changes only `is_obsolete`, `obsolete_reason`, `obsoleted_by_change_id`
- [x] A `requires-update` case is byte-identical before and after a delta run
- [x] A report renders with a section marked `not_available` rather than failing
- [x] Every rendered figure carries a derivation
- [x] The full U1 through U6 suites still pass
- [x] **NFR-PRF-02 met**: the full report set inside 30 seconds at 6,000 cases
