# Code Generation Plan — U6 Handover

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U6 | **Stage**: Code Generation (Part 1: Planning)
**Created**: 2026-08-30T16:04:00Z
**Status**: COMPLETE 2026-08-30 — all 16 steps executed

**This plan is the single source of truth for U6 Code Generation.**

---

## 1. Unit Context

### Stories (3)

| Story | Title | Release |
|---|---|---|
| US-HND-01 | Assemble a standalone Playwright project | R1 |
| US-HND-02 | Verify integrity before declaring handover ready | R2 |
| US-HND-03 | Produce a handover manifest | R2 |

### Dependencies

U1, U5 — both complete.

### Release depth

**All three.** US-HND-02 and -03 are R2 and cannot be deferred: assembly without
verification declares a handover ready on no evidence, which is worse than not
declaring it at all. The unit's whole purpose is the gate.

---

## 2. What Makes U6 Different

**It is the only unit that starts a process.** Everything else in this codebase reads a
database, renders a string, or writes a file.

That single fact shapes the whole stage: one new port, one adapter that is the sole
importer of `subprocess`, a fifth import contract to keep it that way, and a test suite
that must pass on a machine with no Node — because working without Node is a feature of
this unit rather than a limitation of the test environment.

---

## 3. Code Location

```
src/tto_testgen/
  ports/commands.py                       NEW  CommandRunner protocol, CommandResult
  adapters/command_runner.py              NEW  L14, sole importer of subprocess
  adapters/structural_verifier.py         NEW  L15
  services/handover.py                    NEW  S7
  mcp/tools_u6.py                         NEW  2 tools
  platform/config.py                      MOD  3 keys
  composition.py                          MOD  wire L14, L15, S7
.importlinter                             MOD  fifth contract
tests/
  unit/test_command_runner.py             NEW
  unit/test_structural_verifier.py        NEW
  integration/test_u6_handover.py         NEW
  properties/test_u6_properties.py        NEW
  benchmark/test_performance_budgets.py   MOD  + 3 budgets
  fakes/commands.py                       NEW  FakeCommandRunner
```

**No migration.** A handover is an event, and `unit_state.metrics` already records the
outcome — U7 built that column for this.

---

## 4. Generation Steps

16 steps.

### Phase A — The Command Boundary

- [x] **Step 1**: `ports/commands.py` — the argv-only protocol and `CommandResult`
      *Serves*: US-HND-02, U6-NFR-SEC-01

- [x] **Step 2**: L14 `adapters/command_runner.py` — `shell=False`, timeout, output
      truncated at capture, sanitised
      *Serves*: US-HND-02, U6-NFR-SEC-01 to -04

- [x] **Step 3**: The fifth import contract, and confirm it fails when violated
      *Serves*: U6-NFR-MNT-01

- [x] **Step 4**: `tests/fakes/commands.py` — a fake runner that can report Node
      absent, a command failing, and a timeout
      *Serves*: all 3

- [x] **Step 5**: L14 unit tests, including one that runs a real trivial command
      *Serves*: U6-NFR-SEC-01 to -04

### Phase B — Structural Verification

- [x] **Step 6**: L15 `adapters/structural_verifier.py` — required files, import
      resolution, absolute paths, credential re-scan
      *Serves*: US-HND-02

- [x] **Step 7**: L15 unit tests, including a spec importing a page object that does
      not exist — US-HND-02 AC4's exact failure
      *Serves*: US-HND-02

### Phase C — The Service

- [x] **Step 8**: `CheckStatus`, `TierResult`, `VerificationReport`, and the readiness
      expression naming all three states
      *Serves*: US-HND-02, U6-NFR-REL-04, -05

- [x] **Step 9**: S7 assembly — `.gitignore`, the lockfile attempt, the manifest
      *Serves*: US-HND-01

- [x] **Step 10**: S7 toolchain tier — detection, three commands, skip with reason
      *Serves*: US-HND-02

- [x] **Step 11**: S7 manifest and three-way reconciliation
      *Serves*: US-HND-03

- [x] **Step 12**: Atomic write, and the outcome recorded in `unit_state`
      *Serves*: U6-NFR-REL-03, -07

### Phase D — Interface

- [x] **Step 13**: 2 MCP tools — `handover_assemble`, `handover_verify`
      *Serves*: all 3

- [x] **Step 14**: Config keys, composition wiring, Agent Layer check re-run
      *Serves*: FR-AGT-05

### Phase E — Verification

- [x] **Step 15**: Integration tests — full handover, Node absent, a broken import
      blocking readiness, a re-run producing identical bytes
      *Serves*: US-HND-01 to -03

- [x] **Step 16**: The 9 U6 properties, 3 benchmarks, verification and the summary
      *Serves*: U6-NFR-PRF-01 to -05

---

## 5. The Three Benchmarks

| Budget | Target | Why it might fail |
|---|---|---|
| Structural verification, ~300 files | < 10 s | Reads and regexes every generated file |
| Three-way reconciliation, 6,000 cases | < 10 s | Three sets and their differences |
| Manifest construction, 6,000 cases | < 5 s | Sorted rows plus a database read |

**No toolchain benchmark.** It would measure the operator's network, and the timeout is
the guarantee U6 actually owes.

---

## 6. Testing Without Node

The suite must pass on a machine with no Node, because that is the environment U6 was
designed for. Every toolchain path is tested through `FakeCommandRunner`:

| Scenario | Fake behaviour |
|---|---|
| Node absent | `is_available` returns False |
| Compilation fails | Non-zero exit with captured stderr |
| Registry unreachable | `timed_out=True` |
| Everything passes | Zero exits |

One test invokes a real command — `python -c "print(1)"` — to confirm L14 actually runs
processes. It uses the interpreter already running the suite, so it needs nothing
installed.

---

## 7. Not In This Unit

| Item | Reason |
|---|---|
| Pushing, branching, Jenkins configuration | FR-HND-04. **No such method exists** |
| Regenerating a broken project | The operator's call, through `automation_emit` |
| Gap and coverage reporting | U8 |
| Running the tests | Jenkins. Explicitly outside scope |

---

## 8. Scope

| Measure | Estimate |
|---|---|
| New source files | 5 |
| Modified | 3, plus `.importlinter` |
| Test files | 4 new, 1 modified |
| Property tests | 9 |
| MCP tools added | 2 |
| Migrations | **0** |

---

## 9. Verification at Completion

- [x] All 16 steps `[x]`
- [x] All 3 U6 stories `[x]`
- [x] **Five** import contracts pass, including `subprocess` isolation
- [x] All 9 U6 properties passing
- [x] The full suite passes with **no Node installed**
- [x] A skipped tier does not block readiness; a failed one does
- [x] A spec importing a missing page object blocks readiness and names the file
- [x] Two handovers over an unchanged corpus produce identical manifest bytes
- [x] S7 has no method that pushes, branches, or invokes git
- [x] The full U1, U7, U2, U3, U4 and U5 suites still pass
- [x] All three U6 budgets met
