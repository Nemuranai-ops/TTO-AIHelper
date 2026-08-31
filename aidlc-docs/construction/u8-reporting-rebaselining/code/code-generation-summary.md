# Code Generation Summary — U8 Reporting and Re-baselining

**Phase**: CONSTRUCTION | **Unit**: U8 | **Stage**: Code Generation (Part 2)
**Version**: 1.0 | **Date**: 2026-08-31

All 18 steps executed. **951 tests pass**, 5/5 import contracts kept, 23 benchmarks
within budget. **The last unit.**

---

## 1. What Was Built

| File | Content |
|---|---|
| `adapters/sqlite/migrations/m007_run_baseline.py` | Migration 007, with a tested reverse |
| `adapters/report_renderer.py` | **L16** — Markdown and CSV, deterministic |
| `adapters/change_detector.py` | **L17** — per-source detection under isolation |
| `services/reporting.py` | **S8** and the 7-row section registry |
| `services/delta.py` | **S9** and `advance_baseline` |
| `mcp/tools_u8.py` | `reports_generate`, `delta_detect`, `delta_status` |

**Modified**: queries and repositories (report aggregations, baseline read/write,
`for_target`, `current_run_id`), ports, `platform/config.py` (3 keys),
`composition.py`, the agent-layer check, two chat modes.

**Tests**: `test_report_renderer.py` (28), `test_u8_reporting.py` (12),
`test_u8_delta.py` (15), `test_u8_properties.py` (13), 3 new benchmarks.

---

## 2. NFR-PRF-02, Measured At Last

The project budget provisioned at U1 and never exercised until now.

| Budget | Target | Measured at **10,000 cases** |
|---|---|---|
| Full report set, **end to end** | < 30 s | **0.23 s** |
| Any single report | < 5 s | **0.06 s** |
| Impact mapping, 500 changes | < 10 s | **< 0.01 s** |

End to end means query, render and write. The margin comes from the decision made at
U1 and restated at U3, U4 and here: **aggregate in SQL, never by counting in Python.**

---

## 3. Defects Found and Fixed

### A carriage return would have broken a report table

Found by `test_a_markdown_row_never_loses_a_cell`, from the falsifying example
`{"feature": "\r"}`.

`_cell` normalised `\n` and nothing else. Python's `splitlines()` also splits on
carriage returns, form feeds, vertical tabs and the Unicode line separators — so a
requirement statement carrying any of them would split the table row it sat in, and
the report would render with the columns silently wrong from that row on.

Fixed with `" ".join(value.splitlines())`. **No hand-written test would have found
this**: nobody puts a bare `\r` in a fixture.

### Four API mismatches, each caught on first execution

| Called | Actual | Consequence had it shipped |
|---|---|---|
| `isolate(...)` as a context manager | A function over items | L17 would not import |
| `TraceEdge(...)` without `requirement_id` | Required positional | Delta detection raises |
| `impact.scale()`, `.is_large()` | Properties, not methods | `TypeError` mid-run |
| `changes.add(dict, run_id)` | Takes a `ChangeEvent` | No change event recorded |

None survived past the first run of the tests that exercise them. **The pattern is
worth naming**: every one came from writing a caller against a remembered API rather
than a read one, and every one was cheap because the test existed before the
integration.

### A gate check that was a hack

I first wrote `if not gate.is_open and gate.detail and "approved" not in gate.detail`
— a condition shaped to make tests pass rather than to express a rule.

Removed, and the reasoning recorded in its place. **FR-DLT-06 is about the work a delta
*triggers***: regenerating requirements and cases re-enters the pipeline at U3 and U4,
where the gates already are. Detection creates nothing.

Gating detection would also invert the intent: an operator could not learn the corpus
had gone stale until they had approved a stage, and **the thing they most need before
approving is the knowledge that it moved.**

---

## 4. Decisions Made During Implementation

### A detection is itself a run

`change_event.run_id` is `NOT NULL`, so there is no way to record a change without a
run — the schema saying that a change nobody can attribute to a run is not a fact worth
keeping. `run.kind = 'delta'` has existed since U1 with no writer; S9 is it.

Only a run whose detection was complete is marked `ended_at`, so **an incomplete delta
run can never become the next baseline** — which is P-U8-01 expressed a second way.

### The gap report has no precondition

Every other section can be `not_available`. Gaps are computable from the first run, and
"no requirements yet" is itself the useful finding at that point.

---

## 5. Enforcement Made Structural

| Rule | How it cannot be violated |
|---|---|
| A partial detection never advances the baseline | One guarded function, enumerated by property |
| A failed source contributes no head commit | Recorded only inside the success branch |
| No requirement or case is created by a delta run | **No such method on S9** — asserted by a test |
| Every section has a precondition and a derivation | A registry row cannot omit them |
| No figure is composed by a model | Every section's `query` is a repository call |
| Reports carry no personal data or credential | L9 and L13 re-run over rendered output; emission refuses |
| Nothing is ever deleted | No delete method exists anywhere in the corpus repositories |

---

## 6. Verification

- [x] All 18 steps `[x]`
- [x] All 6 U8 stories delivered
- [x] Migration 007 applies and reverses
- [x] Five import contracts pass — no classification logic in U8
- [x] 13 U8 properties passing
- [x] A partial delta run does not advance the baseline, over every combination of
      source outcomes
- [x] Retirement changes only the three obsolete columns; steps, data and links remain
- [x] A `requires-update` case is byte-identical before and after a delta run
- [x] A report renders with a section marked `not_available` rather than failing
- [x] Every rendered figure carries a derivation
- [x] U1 through U6 suites still pass — **951 total**
- [x] **NFR-PRF-02 met**: 0.23 s against a 30-second budget, at 10,000 cases
