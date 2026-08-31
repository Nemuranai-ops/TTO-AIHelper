# API Layer Summary — U1 Core Platform

**Phase**: CONSTRUCTION | **Unit**: U1 | **Stage**: Code Generation (Steps 18-21)
**Date**: 2026-08-29

---

## Files Created

| Path | Component | Purpose |
|---|---|---|
| `src/tto_testgen/mcp/server.py` | M1, M2 | stdio server, tool registry, Result-to-response conversion, global handler |
| `src/tto_testgen/mcp/tools_read.py` | M2 | 16 read-tier tools |
| `src/tto_testgen/mcp/tools_write.py` | M2 | 3 write-tier tools U1 owns |
| `tests/integration/test_mcp_surface.py` | — | 28 tests covering the boundary guarantees and gate enforcement |

---

## The Two-Tier Surface

**Read tier — 16 tools.** `resources_list`, `artefacts_query`, `features_list`,
`feature_get`, `requirements_query`, `coverage_get`, `coverage_forecast`,
`testcases_query`, `testcase_get`, `duplicates_check`, `trace_query`,
`trace_matrix`, `gap_query`, `run_status`, `unit_state_get`, `health_check`.

**Write tier — 3 tools registered by U1.** `unit_begin`, `unit_complete`,
`stage_approve`. The remaining 17 write tools belong to the units that own their
services and are registered by U2 through U8.

The asymmetry is the point. Writes carry the invariants and partial failure does
real damage, so one call performs one complete unit of work inside one transaction.
Reads carry no invariants and benefit from flexibility, so they stay granular.

---

## Boundary Guarantees, Each Verified

| Guarantee | Requirement | How it is tested |
|---|---|---|
| No exception crosses the boundary | NFR-SEC-07 | A tool that raises returns `FAILED_INTERNAL` |
| Messages carry no path outside the workspace, no stack detail, no secret | NFR-SEC-08 | A tool raising `token=abc123 at /etc/shadow` yields neither in the response |
| Validation runs before any logic | NFR-SEC-03 | A handler with a counter is never entered on malformed input |
| Rejections and failures are distinguishable | NFR-USA-03 | `family` is `rejected` or `failed` |
| Every failure carries remediation | NFR-USA-03 | Asserted across the surface |
| stdio only, no listener | NFR-SEC-02 | AST import inspection of the whole `mcp` package |
| Page size hard-capped | NFR-SCL-04 | `limit` above 200 is refused by the schema |

---

## Gate Enforcement

Every gate behaviour from FR-BAT is enforced in code and covered by a test.

| Behaviour | Outcome |
|---|---|
| Claiming an in-progress unit | `FAILED_LOCKED`, with guidance to inspect then restart |
| Claiming a completed unit | `REJECTED_ALREADY_COMPLETE` unless `regenerate=true` |
| Completing without the matching lease | `FAILED_LOCKED` |
| Completing a unit never begun | Refused |
| Coverage approval by a non-Test-Lead | `REJECTED_ROLE_NOT_PERMITTED`, attempt logged |
| Coverage approval by the Test Lead | Accepted, bound to the content hash |
| Other stages | Not role-restricted |

**An interrupted unit is never silently resumed.** A lease that was never completed
leaves the unit `in-progress`, and re-claiming it fails with guidance rather than
picking up from an unknown point (US-BAT-03 AC3).

---

## Deviation Recorded

**Three write tools, not two.** The code generation plan named `unit_begin` and
`unit_complete` as U1's write tools. `stage_approve` was added alongside them,
because without it the R1 walking skeleton has no way to open a gate — and a gate
that cannot be opened is not a gate that can be exercised end to end, which is the
whole purpose of the first pass.

All three are thin wrappers over U1's `RunStateRepository`. The richer
`RunStateService` behaviour — status nuance, stale-lock recovery, resume semantics
— remains U7's, per the unit decomposition. If U7 later supersedes these
registrations, the repository beneath them does not change.

---

## Defect Found by a Test

`test_server_opens_no_network_listener` originally searched the module source for
`"bind("`. It failed — on `self._logger.bind(...)`, which is correlation context,
not a socket.

The check now inspects imports via AST. That matters beyond the false positive: a
guard that cries wolf gets weakened until it stops catching anything, and this one
protects NFR-SEC-02. It now covers the whole `mcp` package rather than one module,
so a listener added to a future tools file is caught too.

---

## Story Progress

| Story | Status |
|---|---|
| US-ENB-02 MCP server with typed, validated tools | **Complete** — 19 tools, all guarantees tested |
| US-ENB-04 Secrets and confidentiality | **Complete** — sanitisation verified at the boundary |
