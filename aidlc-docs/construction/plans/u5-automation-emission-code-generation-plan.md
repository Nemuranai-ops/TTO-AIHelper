# Code Generation Plan — U5 Automation Emission

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U5 | **Stage**: Code Generation (Part 1: Planning)
**Created**: 2026-08-30T14:30:00Z
**Status**: COMPLETE 2026-08-30 — all 19 steps executed

**This plan is the single source of truth for U5 Code Generation.**

---

## 1. Unit Context

### Stories (6)

| Story | Title | Release |
|---|---|---|
| US-AUT-01 | Generate a standard Playwright project with page objects | R1 |
| US-AUT-02 | Generate resilient locators without fixed waits | R2 |
| US-AUT-03 | Generate API tests in the same project | R1 |
| US-AUT-04 | Annotate tests with tags and traceability | R1 |
| US-AUT-05 | Externalise configuration and configure reporters | R1 |
| US-AUT-06 | Regenerate safely and automate only what qualifies | R2 |

### Dependencies

U1, U4 — complete. U2's UI model supplies the locators; U7's gate guards the stage.

### Release depth

**All six in this pass.** US-AUT-02 and -06 are R2 and are included, for the same
reason U3 included its R3 story: the R1 half cannot be built without them. A spec
emitted without the locator ladder would need every locator rewritten when R2 arrived,
and hand-edit detection cannot be retrofitted to files already written without it —
the first run would record no hashes, so the first regeneration would overwrite the
engineer's work.

---

## 2. What Makes U5 Different

**This unit's deliverable is TypeScript that leaves the workspace.** The templates are
the generated coding standard and the artefact the Automation Engineer reviews; the
Python that drives them is plumbing.

That inverts the usual weight of this stage. The nine template files matter more than
the five Python modules, and the properties assert what comes *out* rather than what
the code does.

---

## 3. Code Location

```
src/tto_testgen/
  adapters/sqlite/migrations/m006_emitted_view_kind.py   NEW
  domain/locators.py                                     NEW  L12, pure
  domain/secrets.py                                      NEW  L13, pure
  adapters/templates.py                                  NEW  L11
  adapters/playwright_emitter.py                         NEW  A7
  templates/playwright/*.j2                              NEW  9 templates
  services/automation.py                                 NEW  S6
  mcp/tools_u5.py                                        NEW  2 tools
  adapters/sqlite/repositories.py                        MOD  automated_test, view kind
  adapters/sqlite/queries/__init__.py                    MOD
  ports/repositories.py                                  MOD  view kind on upsert
  platform/config.py                                     MOD  5 keys
  composition.py                                         MOD  wire L11-L13, A7, S6
tests/
  unit/test_domain_locators.py                           NEW
  unit/test_domain_secrets.py                            NEW
  unit/test_playwright_emitter.py                        NEW
  integration/test_u5_automation.py                      NEW
  properties/test_u5_properties.py                       NEW
  benchmark/test_performance_budgets.py                  MOD  + 4 budgets
  fakes/repositories.py                                  MOD  automation fake
```

**Templates live inside the package** at `src/tto_testgen/templates/playwright/`, not at
the workspace root. `PackageLoader` resolves them relative to the installed package, so
output does not depend on the operator's working directory (P-U5-02).

---

## 4. Generation Steps

19 steps.

### Phase A — Foundation

- [x] **Step 1**: Migration 006 — `kind` column on `emitted_view` with its index and a
      tested reverse
      *Serves*: US-AUT-06

- [x] **Step 2**: Repository and port updates — `kind` on view upsert, automated-test
      writes, per-feature case reads
      *Serves*: US-AUT-06, US-AUT-01

- [x] **Step 3**: Config keys — destination, pinned versions, spec-line threshold,
      extra credential field names
      *Serves*: US-AUT-05, U5-NFR-MNT-06

### Phase B — Pure Domain

- [x] **Step 4**: `domain/locators.py` — L12, the five-rank ladder, XPath absent,
      `ResolvedLocator` with its annotations
      *Serves*: US-AUT-02

- [x] **Step 5**: `domain/secrets.py` — L13, field-name and value-shape signals, the
      finding that never quotes the value
      *Serves*: US-AUT-05

- [x] **Step 6**: Unit tests for both, including the values that must **not** fire —
      a UUID, a base64 fixture, a hash
      *Serves*: US-AUT-02, US-AUT-05

### Phase C — Templates

- [x] **Step 7**: L11 `adapters/templates.py` — the configured environment and the
      `ts` filter
      *Serves*: U5-NFR-SEC-06, U5-NFR-REL-01

- [x] **Step 8**: Scaffold templates — `package.json`, `playwright.config.ts`,
      `tsconfig.json`, `.env.example`, `README.md`
      *Serves*: US-AUT-05

- [x] **Step 9**: `auth.fixture.ts.j2` — one authentication path, shared by UI and API
      *Serves*: US-AUT-03

- [x] **Step 10**: `page-object.ts.j2` — central locators, unverified and fragile
      comments
      *Serves*: US-AUT-01, US-AUT-02

- [x] **Step 11**: `spec.ts.j2` and `api-spec.ts.j2` — describe per coverage item,
      annotations, assertions in place of waits
      *Serves*: US-AUT-01, US-AUT-03, US-AUT-04

### Phase D — Emitter and Service

- [x] **Step 12**: A7 `adapters/playwright_emitter.py` — rendering, deterministic
      ordering, three-outcome emission
      *Serves*: US-AUT-01, US-AUT-06

- [x] **Step 13**: A7 unit tests — byte-stability, hand-edit, no fixed wait, no XPath
      *Serves*: US-AUT-02, US-AUT-06

- [x] **Step 14**: S6 `services/automation.py` — gate, partition, secret refusal,
      emission, `automated_test` rows, gaps
      *Serves*: all 6

- [x] **Step 15**: 2 MCP tools — `automation_emit`, `automation_report`
      *Serves*: all 6

### Phase E — Verification

- [x] **Step 16**: Chat mode registration and U7's Agent Layer check re-run
      *Serves*: FR-AGT-05

- [x] **Step 17**: Integration tests — full emission, refusal writes nothing, a
      hand-edited config survives
      *Serves*: US-AUT-01 to -06

- [x] **Step 18**: The 10 U5 properties plus the 3 on L11
      *Serves*: all 6

- [x] **Step 19**: Benchmarks, composition wiring, verification and the summary
      *Serves*: U5-NFR-PRF-01 to -05

---

## 5. The Four Benchmarks

| Budget | Target | Why it might fail |
|---|---|---|
| One feature at 100 cases | < 5 s | The frequent operation |
| Whole project, 150 features | < 60 s | 300 files, rendered serially by choice |
| **Second whole-project emission** | **< 30 s, zero files written** | **The determinism assertion** |
| Locator resolution per case | < 20 ms | The ladder, per referenced element |

**The third is the one that carries real weight.** It is not a performance test wearing
a reliability hat — it asserts that a regeneration over an unchanged corpus writes
nothing, which is the property an operator needs before a handover and the one that
fails loudly if any determinism exclusion was forgotten.

---

## 6. Not In This Unit

| Item | Reason |
|---|---|
| Assembling or verifying the handover project | U6 |
| Running the generated tests | Jenkins. Explicitly outside scope |
| Live locator verification | U2's Playwright MCP work, still agent-side |
| Automation coverage reporting | U8 |

---

## 7. Scope

| Measure | Estimate |
|---|---|
| New Python source files | 6 |
| New template files | 9 |
| Modified | 6 |
| Test files | 5 new, 2 modified |
| Property tests | 13 |
| MCP tools added | 2 |
| Migration | 006 |

---

## 8. Verification at Completion

- [x] All 19 steps `[x]`
- [x] All 6 U5 stories `[x]`
- [x] Migration 006 applies and reverses
- [x] Import contracts pass — no classification or similarity logic in U5
- [x] All 13 U5 properties passing
- [x] No rendered file contains a fixed wait, an XPath, or a literal credential
- [x] A second emission over an unchanged corpus writes **zero** files
- [x] A hand-edited `playwright.config.ts` survives a regeneration
- [x] Agent Layer check passes with 2 more tools registered
- [x] The full U1, U7, U2, U3 and U4 suites still pass
- [x] All four U5 budgets met
