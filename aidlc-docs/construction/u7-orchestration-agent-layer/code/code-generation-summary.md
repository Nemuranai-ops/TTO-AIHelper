# Code Generation Summary — U7 Orchestration and Agent Layer

**Phase**: CONSTRUCTION | **Unit**: U7 | **Stage**: Code Generation (Part 2 complete)
**Date**: 2026-08-29

---

## Result

All 14 planned steps executed. **337 tests passing**, 4 import contracts kept, all 8
U7 stories complete. The 7 benchmark budgets still pass unchanged.

| Measure | Planned | Actual |
|---|---|---|
| New source files | 4 | 4 |
| Modified source files | 1 | 2 (`tools_write.py`, `composition.py`) |
| Agent Layer files | 18 | 18 |
| Test files | 4 | 4 |
| Property tests | 9 | 9 |
| Agent Layer checks | 7 | 20 assertions across 7 requirements |

---

## Files

**Source**

```
src/tto_testgen/domain/gates.py                          L5 GateEvaluator (pure)
src/tto_testgen/services/__init__.py                     new package
src/tto_testgen/services/runstate.py                     S10 + ReportContext
src/tto_testgen/adapters/sqlite/migrations/m002_lease_columns.py
src/tto_testgen/mcp/tools_write.py                       rewired to delegate to S10
src/tto_testgen/composition.py                           constructs and injects S10
.importlinter                                            + services layer and contract
```

**Agent Layer**

```
.github/copilot-instructions.md
.github/chatmodes/{ingest,analyse,requirements,coverage,cases,automation,handover}.chatmode.md
.github/instructions/{playwright,testcase-views,toolchain}.instructions.md
.github/prompts/{analyse-story,generate-cases,review-batch,
                 generate-page-object,coverage-report,resume-run}.prompt.md
.vscode/mcp.json
```

**Tests**

```
tests/unit/test_domain_gates.py          34 tests, exhaustive over stages x conditions
tests/unit/test_agent_layer.py           20 tests, the 7 consistency requirements
tests/integration/test_runstate_service.py  35 tests
tests/properties/test_u7_properties.py    9 properties
```

---

## The Agent Layer Check Found a Real Gap on Its First Run

`test_every_registered_tool_appears_in_some_mode` failed immediately:
`gap_query` and `trace_matrix` were registered read tools that appeared in **no chat
mode**. The operator could not reach them from anywhere.

Both are now in the `coverage` and `handover` modes, which are the stages that review
coverage adequacy.

**This is exactly the drift the check exists to prevent, and it was already present
before a single new tool had been registered.** Seventeen more write tools are coming
from U2 through U8. A review checklist would not have caught this one; it was not
introduced by an edit, it was there from the moment the modes were written.

---

## Two Defects Found During Generation

### `fail_unit` treated a JSON column as a dict

`existing["metrics"]` is a JSON string from SQLite. `fail_unit` passed it to `dict()`
directly, which raised on any non-empty value. The `_metrics_of` helper existed for
precisely this and was not used in that one path — the kind of omission that only
surfaces when the failure path is actually exercised, which is why the test that
retries a failed unit is worth having.

### A shell substitution silently truncated seven files

The first attempt at generating the chat modes used `${stage^}` for capitalisation,
which zsh does not support. The files were created but their bodies were empty. The
`ls` output looked correct — seven files, right names — and only inspecting the
content revealed it. Regenerated with Python.

Worth recording because the failure was silent in the shell's own output: an exit
code and a directory listing both looked fine.

---

## Deviations from Plan

| Deviation | Reason |
|---|---|
| 5 write tools, not 3 | `unit_fail` and `unit_heartbeat` added. The heartbeat is what BR-U7-2 needs to tell a working session from an abandoned one — without a tool to refresh it, every long-running unit would be reported stale. `unit_fail` gives the failed state a way to be reached; without it, a unit that failed could only be left in progress. |
| `composition.py` modified as well | Not in the plan's file list, but S10 must be constructed somewhere and the composition root is the only module permitted to know both a protocol and its implementation. |
| A fifth import contract | `services-do-not-import-adapters`, added with the `services` package. The layers contract alone would have permitted a service importing a concrete repository. |
| Two U1 tests updated | `test_in_progress_unit_is_not_silently_resumed` asserted the old wrapper's blanket wording. Since U7, a *fresh* lease is reported active and the operator is told to wait; a *stale* one is told how to restart. Both refuse — only the advice differs, which is the point of classifying rather than issuing one message. A second test was added for the stale path. |

---

## The Rewiring Was Safe Because U1 Was Tested

Step 8 modified approved U1 code. The 28 U1 MCP tests were the regression guard, and
two of them failed — correctly, on behaviour that had genuinely changed. Both were
updated to assert the new guarantee rather than the old wording.

That is the value of the earlier work being tested: modifying it was a
twenty-minute change with a clear signal, rather than an act of faith.

---

## Story Completion

| Story | Status | Evidence |
|---|---|---|
| US-BAT-01 Name the batch scope | **Complete** | Operator names unit and stage; no method proposes either |
| US-BAT-02 Durable transactional state | **Complete** | Migration 002, lease lifecycle, metrics commit with state |
| US-BAT-03 Resume after interruption | **Complete** | Stale classification, resume view, "nothing was lost" |
| US-BAT-04 Stop at every stage gate | **Complete** | L5, exhaustively tested across 7 stages x 5 conditions |
| US-AGT-01 Repository instructions | **Complete** | Four standing rules, asserted present |
| US-AGT-02 Per-stage chat modes | **Complete** | 7 modes, tool lists machine-checked |
| US-AGT-03 Register the MCP servers | **Complete** | 4 servers, no literal secret |
| US-AGT-04 Path-scoped instructions and prompts | **Complete** | 3 instruction files, 6 prompts |

---

## Verification

| Check | Result |
|---|---|
| All 14 steps marked `[x]` | Yes |
| All 8 U7 stories complete | Yes |
| Migration 002 applies and reverses | Yes |
| Import contracts | 4 of 4 kept |
| U7 properties | 9 of 9 passing |
| Agent Layer checks | 7 of 7 requirements, 20 assertions |
| No file-write tool in any mode | Verified |
| No secret in `.vscode/mcp.json` | Verified |
| Full U1 suite still passes | Yes — the regression guard on the rewiring |
| Benchmarks unaffected | 7 of 7 still within budget |
