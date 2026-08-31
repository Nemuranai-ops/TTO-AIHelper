# Code Generation Plan — U7 Orchestration and Agent Layer

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U7 | **Stage**: Code Generation (Part 1: Planning)
**Created**: 2026-08-29T15:16:00Z
**Status**: COMPLETE 2026-08-29 - all 14 steps executed

**This plan is the single source of truth for U7 Code Generation.**

---

## 1. Unit Context

### Stories implemented by U7 (8)

| Story | Title | Release |
|---|---|---|
| US-BAT-01 | Name the batch scope | R1 |
| US-BAT-02 | Track unit state durably and transactionally | R1 |
| US-BAT-03 | Resume after interruption | R1 |
| US-BAT-04 | Stop at every stage gate | R1 |
| US-AGT-01 | Establish repository instructions | R1 |
| US-AGT-02 | Provide per-stage chat modes | R1 |
| US-AGT-03 | Register the MCP servers | R1 |
| US-AGT-04 | Path-scoped instructions and prompt files | R2 |

### Dependencies

**U1 Core Platform only**, and it is complete. U7 uses `RunStateRepository`,
`unit_of_work`, the `Result` type, the logger, and the three MCP tool registrations
already in place.

### Interfaces U7 exposes

| Consumer | Contract |
|---|---|
| S4, S5, S6, S7 (U3-U6) | `is_gate_open(unit_ref, stage) -> GateEvaluation` — read-only, joins no transaction |
| The operator | Seven chat modes, the instruction set, the prompt files |
| All units | The Agent Layer conventions their tools must fit |

### Release depth

**R1 for everything except US-AGT-04** (path-scoped instructions and prompt files),
which is R2. Both are included in this pass: they are Markdown files whose content
is already fully specified in `frontend-components.md`, and deferring them would mean
returning to this unit for an afternoon's work later.

---

## 2. Code Location

**Workspace root**. Documentation to
`aidlc-docs/construction/u7-orchestration-agent-layer/code/` as markdown only.

```
src/tto_testgen/
  domain/gates.py                     L5 GateEvaluator (pure)
  services/__init__.py                new package
  services/runstate.py                S10 RunStateService + ReportContext
  adapters/sqlite/migrations/m002_lease_columns.py
  mcp/tools_write.py                  rewired to delegate to S10
.github/
  copilot-instructions.md
  instructions/{playwright,testcase-views,toolchain}.instructions.md
  chatmodes/{ingest,analyse,requirements,coverage,cases,automation,handover}.chatmode.md
  prompts/{analyse-story,generate-cases,review-batch,generate-page-object,
           coverage-report,resume-run}.prompt.md
.vscode/mcp.json
tests/
  unit/test_domain_gates.py
  unit/test_agent_layer.py
  properties/test_u7_properties.py
  integration/test_runstate_service.py
```

**`services/` is a new package.** The import-linter layers contract must be extended
to include it between `adapters` and `ports`, or the first service import will break
the build. Step 2 does this.

---

## 3. Generation Steps

14 steps. Each marked `[x]` in the interaction that completes it.

### Phase A — Foundation

- [x] **Step 1**: Migration 002 — add `leased_at`, `last_heartbeat`, `lease_holder`
      to `unit_state`, with a table-rebuild reverse that does not depend on the
      SQLite version supporting `DROP COLUMN`
      *Serves*: US-BAT-02, U7-NFR-REL-04

- [x] **Step 2**: Extend the import-linter layers contract for `services`, and create
      the package
      *Serves*: NFR-MNT-01

### Phase B — Business Logic

- [x] **Step 3**: L5 `domain/gates.py` — stage ordering, `evaluate`, `prior_stage`,
      `is_role_permitted`, `GateEvaluation`, `GateFailure`, `Role`. Pure: receives
      the prior record and current hash as arguments
      *Serves*: US-BAT-04

- [x] **Step 4**: L5 unit tests — all three conditions across all seven stages, the
      role restriction, and the failed-condition naming
      *Serves*: US-BAT-04

- [x] **Step 5**: S10 `services/runstate.py` — lease lifecycle, heartbeat, stale
      classification, status composition, approval recording, `ReportContext`
      *Serves*: US-BAT-01, US-BAT-02, US-BAT-03

- [x] **Step 6**: S10 integration tests against a real database — transitions,
      lease matching, stale detection, status neutrality, approval binding
      *Serves*: US-BAT-01 to US-BAT-04

- [x] **Step 7**: U7 property tests — the 9 properties from
      `business-logic-model.md` §5, including the two that assert forbidden behaviour
      *Serves*: US-BAT-03, US-BAT-04, C-12

- [x] **Step 8**: Rewire `mcp/tools_write.py` to delegate to S10 rather than writing
      to the repository directly. Tool names and schemas unchanged
      *Serves*: US-BAT-01, US-BAT-02, US-BAT-04

- [x] **Step 9**: Business logic summary → `.../code/business-logic-summary.md`

### Phase C — Agent Layer

- [x] **Step 10**: `.github/copilot-instructions.md` — role, pipeline model, and the
      four standing rules
      *Serves*: US-AGT-01, FR-AGT-06

- [x] **Step 11**: Seven chat modes with front-matter tool lists, per BR-U7-6.
      Universal reads in every mode; no file-write tool in any
      *Serves*: US-AGT-02, NFR-USA-01

- [x] **Step 12**: Three path-scoped instruction files with `applyTo` globs, six
      prompt files, and `.vscode/mcp.json` with no secret in it
      *Serves*: US-AGT-03, US-AGT-04

- [x] **Step 13**: Agent Layer consistency tests — the seven checks from
      U7-NFR-MNT-01 to -07
      *Serves*: US-AGT-02, NFR-MNT-08

### Phase D — Completion

- [x] **Step 14**: Full verification and the code generation summary
      → `.../code/code-generation-summary.md`

---

## 4. Not In This Unit

| Item | Reason |
|---|---|
| The 17 remaining write tools | Registered by U2-U8 as those units build their services |
| Services S1-S9 | Owned by U2-U6 and U8 |
| Emitters | Owned by U4, U5, U8 |
| Any change to U1's schema beyond migration 002 | U1 is complete and approved |

---

## 5. Scope

| Measure | Estimate |
|---|---|
| Source files | 4 new, 1 modified |
| Agent Layer files | 18 |
| Test files | 4 |
| Property tests | 9 |
| Agent Layer checks | 7 |

Smaller than U1 by a wide margin. Most of U7's substance is the Agent Layer, which is
Markdown whose content is already specified in `frontend-components.md` — this step
writes it, it does not design it.

---

## 6. Story Traceability

| Story | Steps |
|---|---|
| US-BAT-01 Name the batch scope | 5, 6, 8 |
| US-BAT-02 Durable transactional state | 1, 5, 6, 8 |
| US-BAT-03 Resume after interruption | 5, 6, 7 |
| US-BAT-04 Stop at every stage gate | 3, 4, 6, 7, 8 |
| US-AGT-01 Repository instructions | 10, 13 |
| US-AGT-02 Per-stage chat modes | 11, 13 |
| US-AGT-03 Register the MCP servers | 12, 13 |
| US-AGT-04 Path-scoped instructions and prompts | 12, 13 |

---

## 7. Verification at Completion

- [x] All 14 steps marked `[x]`
- [x] All 8 U7 stories marked `[x]`
- [x] Migration 002 applies and reverses cleanly
- [x] Import contracts pass with `services` included
- [x] All 9 U7 properties present and passing
- [x] All 7 Agent Layer checks passing
- [x] No file-write tool in any chat mode
- [x] No secret in `.vscode/mcp.json`
- [x] The full U1 suite still passes — U7 changes `tools_write.py`, so U1's MCP tests
      are the regression guard on that rewiring
