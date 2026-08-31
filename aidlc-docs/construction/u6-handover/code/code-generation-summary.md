# Code Generation Summary — U6 Handover

**Phase**: CONSTRUCTION | **Unit**: U6 | **Stage**: Code Generation (Part 2)
**Version**: 1.0 | **Date**: 2026-08-30

All 16 steps executed. **879 tests pass**, **5/5 import contracts kept**, 20
benchmarks within budget.

---

## 1. What Was Built

| File | Content |
|---|---|
| `ports/commands.py` | The argv-only `CommandRunner` protocol and `CommandResult` |
| `adapters/command_runner.py` | **L14** — the sole importer of `subprocess` |
| `adapters/structural_verifier.py` | **L15** — files, imports, paths, credentials |
| `services/handover.py` | **S7** — assemble, verify, reconcile, report |
| `mcp/tools_u6.py` | `handover_assemble`, `handover_verify` |
| `.importlinter` | **Fifth contract** — `subprocess` isolation |

**Modified**: queries and repositories (`list_all` on automation),
`ports/repositories.py`, `platform/config.py` (3 keys), `composition.py`, the
agent-layer check, the shared fakes.

**Tests**: `test_command_runner.py` (13), `test_structural_verifier.py` (21),
`test_u6_handover.py` (24), `test_u6_properties.py` (13), 3 new benchmarks.

**No migration.** `unit_state.metrics` records the outcome, as U7 designed it to.

---

## 2. Measured

| Budget | Target | Measured |
|---|---|---|
| Structural verification, ~300 files | < 10 s | **0.05 s** across 921 checks |
| Reconciliation, 6,000 identifiers | < 10 s | **< 0.01 s** |
| Manifest render, 6,000 entries | < 5 s | **0.001 s** |

No toolchain benchmark, by design: it would measure the operator's network, and the
timeout is the guarantee U6 owes.

---

## 3. The Fifth Contract, Verified by Breaking It

```
[importlinter:contract:subprocess-is-isolated]
source_modules = domain, services, mcp, platform, ports
forbidden_modules = subprocess
```

A contract that passes because nothing violates it would also pass if it were
misconfigured. So a one-line probe module importing `subprocess` was added to
`services/`, the linter run, and the output confirmed:

```
Only the command runner imports subprocess BROKEN
tto_testgen.services._probe -> subprocess (l.1)
Contracts: 4 kept, 1 broken.
```

The probe was then removed and the suite returned to 5 kept. **The check is real.**

---

## 4. Defects Found and Fixed

### `with_suffix` broke every correct import

`Path("checkout.page").with_suffix(".ts")` yields `checkout.ts`, not
`checkout.page.ts` — it *replaces* the existing suffix rather than appending. Every
page-object import in the project resolved to a file that never exists, so **every
structurally sound project would have been reported as broken**.

Caught by the L15 fixture using a realistic filename. A fixture named `page.ts` rather
than `checkout.page.ts` would have passed and shipped the bug.

Fixed with `with_name(name + suffix)`.

### A property test asserted something false about correct code

`ts_literal("\\")` renders `"\\"`. The property's third assertion counted quotes minus
escaped quotes and expected 2 — but the escaped backslash immediately precedes the
closing quote, so the naive count sees `\"` and subtracts one too many.

The code was right; the heuristic was wrong. Replaced with an explicit escape-aware
scan of the interior, plus the observation that **`json.loads` rejects trailing
content**, so a successful round-trip is itself proof the literal is exactly one
complete string.

Hypothesis took roughly six minutes to shrink to `"\\"`, which read as a hang while it
was running. It was not one.

### S7 called a repository method that did not exist

`uow.automation.list_all()` was written before the method was added. Caught on the
first import. Added with its query, its port declaration and its SQLite implementation.

### A case row does not carry its trace links

`_jira_key` expected `trace_links` on the case record; `CASE_PAGE` returns the row
without them. Fixed by reading links per test through `uow.traces.for_source` — bounded
by the suite size rather than the corpus, since there is one test per case.

---

## 5. Decisions Made During Implementation

### Toolchain commands stop at the first failure

`tsc` needs `node_modules`, which `npm ci` installs. Running the remaining commands
after `npm ci` fails produces three failures describing one cause — noise rather than
information.

### `.env.example` is exempt from the credential-field check, and checked separately

Its keys are named `TAAS_AUTH_PASSWORD` by design, so the field-name rule would refuse
the file that does the right thing. It gets its own check instead: **no variable may
carry a value.**

The same reasoning applies inside generated code, where only value shapes are checked —
a TypeScript property named `password` reading from `process.env` is correct code, not
a leak.

### `node_modules/` is never read

Otherwise verification would walk a dependency tree of tens of thousands of files and
report findings about code that is not ours.

---

## 6. Enforcement Made Structural

| Rule | How it cannot be violated |
|---|---|
| No shell | `shell=False` in one module; the port takes a sequence |
| No `subprocess` outside L14 | **Import contract, proven to fire** |
| No push, branch, or CI write | **No such method on S7** — asserted by a test |
| A skipped tier does not block | Three-valued enum; two properties pin both directions |
| A truncated manifest is never read | Atomic write via `os.replace` |
| No lifecycle scripts run | `--ignore-scripts` in a literal argv, asserted |

---

## 7. Verification

- [x] All 16 steps `[x]`
- [x] All 3 U6 stories delivered
- [x] **Five** import contracts pass, and the new one fails when violated
- [x] 13 U6 properties passing
- [x] The whole suite passes with **no Node installed**
- [x] A skipped tier does not block readiness; a failed one does
- [x] A spec importing a missing page object blocks readiness and names the file
- [x] Two handovers over an unchanged corpus produce identical manifest bytes
- [x] S7 exposes no `push`, `branch`, `commit`, `git` or `configure_ci`
- [x] U1, U7, U2, U3, U4 and U5 suites still pass — **879 total**
- [x] All three U6 budgets met with wide margins
