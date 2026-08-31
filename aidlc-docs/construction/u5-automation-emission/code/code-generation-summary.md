# Code Generation Summary — U5 Automation Emission

**Phase**: CONSTRUCTION | **Unit**: U5 | **Stage**: Code Generation (Part 2)
**Version**: 1.0 | **Date**: 2026-08-30

All 19 steps executed. **805 tests pass**, 4/4 import contracts kept, 17 benchmarks
within budget.

---

## 1. What Was Built

| File | Content |
|---|---|
| `adapters/sqlite/migrations/m006_emitted_view_kind.py` | Migration 006, with a tested reverse |
| `domain/locators.py` | **L12** — the five-rank ladder, XPath absent |
| `domain/secrets.py` | **L13** — field-name and value-shape signals |
| `adapters/templates.py` | **L11** — the configured environment, the `ts` filter |
| `adapters/playwright_emitter.py` | **A7** — deterministic rendering, three-outcome emission |
| `templates/playwright/*.j2` | **9 templates** — the generated coding standard |
| `services/automation.py` | **S6** — gate, partition, refuse, render, emit, record |
| `mcp/tools_u5.py` | `automation_emit`, `automation_report` |

**Modified**: repositories and queries, ports, `platform/config.py` (5 keys),
`composition.py`, the agent-layer check, two chat modes, the shared fakes.

**Tests**: `test_domain_locators.py` (24), `test_domain_secrets.py` (31),
`test_playwright_emitter.py` (39), `test_u5_automation.py` (16),
`test_u5_properties.py` (16), 4 new benchmarks.

---

## 2. Measured

| Budget | Target | Measured |
|---|---|---|
| One feature at 100 cases | < 5 s | **0.003 s** (2,642 lines) |
| Whole project, 150 features | < 60 s | **0.07 s** |
| Second emission | < 30 s, **zero files** | Zero written, every file `unchanged` |
| Locator resolution | < 20 ms | **0.08 ms** for 50 elements |

The margins are wide because rendering is string substitution over data already in
memory — the corpus read dominates, and it is U4's cost rather than U5's. **The
serial-rendering decision cost nothing measurable**, which is worth recording: the
10-second whole-project option was declined because parallelism would break
determinism, and it turns out no performance was traded for that.

---

## 3. Defects Found and Fixed

### A Turkish UI label would have emitted uncompilable TypeScript

Found by `test_a_property_name_is_always_a_valid_js_identifier`, not by any example.

`property_name` filtered characters with `str.isalnum()`, which is true for `İ`
(U+0130, Turkish dotted capital I). Lowercasing it produces **`i` plus a combining
dot above** (U+0307), which is not a valid identifier character — so an accessible
name containing it would generate a page-object property TypeScript refuses to
compile.

Fixed by restricting the alphabet to ASCII. A Unicode-aware identifier rule would be
correct in principle and would still have to handle combining marks case by case;
restricting the alphabet is the smaller and more defensible change for generated code.

**No hand-written test would have found this.** Nobody writes `İ` into a test fixture.

### Two faults in S6, both found by reading the code back

| Fault | Consequence | Fix |
|---|---|---|
| A gaps loop whose two branches wrote the same category | Duplicate `manual-only` rows, double-counted in U8's report | Removed — U4 already records them |
| `max_spec_lines` accepted and never used | U5-NFR-SCL-04 silently undelivered | Wired into `_check_spec_size` with a warning |

The first is the more interesting: U5 and U4 both know a case is manual-only, and both
had a plausible reason to record it. The rule that settles it is that **U8 reads the
gap table, not U5's report** — so the table must carry each gap once, and the
needs-review/manual-only distinction belongs in the emission report where the
Automation Engineer is looking.

### A tautological assertion

`assert "https://" not in scaffold.replace("https://", "", 0) or True` asserts
nothing. Replaced with the per-line check over `.env.example` that was doing the real
work beside it.

### The shared fake fell behind its port

`FakeEmittedViewRepository.upsert` did not accept `kind`, so A7's first emission test
failed. Caught immediately because the fake is shared rather than per-unit — which is
the reason contract-first fakes were chosen at Units Generation.

---

## 4. Decisions Made During Implementation

### Step bodies render a TODO, not a guessed Playwright call

`_step_lines` emits the step's text as a comment plus an explicit `TODO`, and the
expected result as an assertion placeholder. Inferring `click` versus `fill` versus
`goto` from prose was the alternative.

**A guessed call looks authoritative and is frequently wrong**, which is worse for the
engineer than an honest placeholder beside the text they need. The structure, tags,
annotations, page objects, fixtures and config are all generated — the automation
engineer supplies the interaction, which is the part that needs the application.

### An exact-version guard in config

`TAAS_PLAYWRIGHT_VERSION=^1.49` is refused at startup. A range lets two regenerations
resolve to different versions, which makes the generated project non-reproducible in
the one dimension U5 cannot control after handover.

### `playwright_version` joins the business-rule fingerprint

Two runs on different Playwright versions are not comparable artefacts, so the version
sits beside `similarity_threshold` in the run record.

---

## 5. Enforcement Made Structural

| Rule | How it cannot be violated |
|---|---|
| No fixed wait | No template fragment emits a delay |
| No XPath | Absent from the ladder; an XPath-only element yields no locator |
| Escaping | `\| ts` at every interpolation, visible to the reviewer |
| A missing template variable | `StrictUndefined` — a render-time error, not an empty string |
| Unsafe slug | Refused, never sanitised |
| No literal credential | Refusal writes no file at all |
| No classification logic in U5 | `.importlinter`, checked in CI |

---

## 6. Verification

- [x] All 19 steps `[x]`
- [x] All 6 U5 stories delivered
- [x] Migration 006 applies and reverses
- [x] Import contracts: 4 kept, 0 broken
- [x] 16 U5 properties passing (13 planned, 3 added during implementation)
- [x] No rendered file contains a fixed wait, an XPath, or a credential literal
- [x] A second emission writes **zero** files, every file reported `unchanged`
- [x] A hand-edited `playwright.config.ts` survives a regeneration
- [x] Agent Layer check passes with 2 more tools registered
- [x] U1, U7, U2, U3 and U4 suites still pass — **805 total**
- [x] All four U5 budgets met with wide margins
