# NFR Design Patterns — U7 Orchestration and Agent Layer

**Phase**: CONSTRUCTION | **Unit**: U7 | **Stage**: NFR Design
**Version**: 1.0 | **Date**: 2026-08-29

Six patterns specific to U7, on top of the eight inherited from U1.

---

## 1. Inherited from U1

| Pattern | Used by U7 |
|---|---|
| P-RES-01 Unit of Work | Every state transition is one transaction |
| P-RES-04 Lease-based unit state | U7 supplies the logic; U1 built the storage |
| P-SCL-01 Capped pagination | Status reports inherit the 200-record cap |
| P-SEC-01 Two-level validation | Pydantic at the boundary, domain invariants beneath |
| P-SEC-03 Message sanitisation | Every refusal passes through it |
| P-OBS-01 Correlation propagation | Approval and transition logging |
| P-MNT-01 Dependency inversion | S10 depends on `RunStateRepository`, not on SQLite |
| P-MNT-02 Enforced import contracts | Extended to the new modules |

**P-RES-02 bounded retry is not exercised.** U7 makes no external call — it reads and
writes local state only. The pattern remains available and is simply not reached.

---

## 2. P-U7-01: Request-Scoped Computation Cache

**Delivers**: U7-NFR-PRF-02, U7-NFR-PRF-03

A `ReportContext` is created when a status report begins and discarded when it ends.
Coverage content hashes computed during the report are memoised on it.

```
with report_context() as ctx:
    for record in records:
        gate = evaluate_gate(record.unit_ref, record.stage, ctx)
        # ctx.coverage_hash(feature_id) computes once, then returns the memo
```

**A cache that cannot outlive the read it serves cannot go stale.** That removes
invalidation as a concern rather than managing it — and the alternative is worse than
merely more work. A hash cached across reports could keep a *revoked* approval
looking valid, because BR-U7-3 decides approval validity by comparing the recorded
hash against the current one. Serving a stale current-hash would defeat the exact
mechanism the gate exists to provide.

This is why `functools.lru_cache` was rejected despite being the terser option: it
persists indefinitely with no invalidation at all.

---

## 3. P-U7-02: Read-Only Gate Evaluation

**Delivers**: U7-NFR-REL-05, U7-NFR-PRF-01

`GateEvaluator` reads state and returns a verdict. It writes nothing, opens no
transaction, and takes no lease.

**Why the guarantee matters.** Gate evaluation is called by S4, S5, S6 and S7 —
inside their transactions, before they do their own work. An evaluator that wrote
anything would join a caller's transaction and could roll back with it, leaving the
gate's own record inconsistent with the state it just reported. Keeping it read-only
means it can be called from anywhere, including from a status report that holds no
transaction at all.

---

## 4. P-U7-03: Advisory Classification

**Delivers**: U7-NFR-REL-02

`classify_lease` returns a `LeaseStatus` describing what it found and what would
change it. There is no method that clears, expires or reclaims a lease.

**The absence is the design.** Clearing a lock another process still holds is how
databases get corrupted, and the service cannot tell a dead session from a slow one —
the operator can look. A heuristic that is right most of the time is wrong precisely
where being wrong costs most.

Verified by property test: no generated input produces a clearing instruction. A
constraint on what must never happen is better guarded by a property over all inputs
than by the examples someone thought of.

---

## 5. P-U7-04: Neutral Ordering

**Delivers**: U7-NFR-USA-01 and constraint C-12

Status rows sort by `(unit_ref, stage_order)`. Stable, deterministic, and carrying no
signal about what to do next.

**Ordering is the subtle way C-12 gets violated.** A report sorted by readiness, or
filtered to open gates, or with one unit emphasised, is a proposal wearing a report's
clothes — the operator reads the top row as a recommendation whether or not it is
labelled one. Sorting by identifier is semantically empty, which is exactly what is
wanted.

Filtering *by operator request* is permitted: that is the operator expressing an
interest they already hold, not the system expressing one.

Verified by property test: output contains no field named `next`, `recommended` or
`ready`, for any generated input.

---

## 6. P-U7-05: Structured Refusal

**Delivers**: U7-NFR-USA-02, U7-NFR-USA-03

A refusal carries `failed_condition`, `detail`, `remediation` and `permitted_role` as
separate fields. The chat mode's instructions tell the agent how to render them.

**The toolchain does not own conversational tone.** The agent already renders
everything else it says, and structured fields let it adapt phrasing to context —
brief when the operator has met this refusal before, fuller when they have not —
without the toolchain guessing.

`failed_condition` being a distinct field rather than parsed from prose is what lets
the agent branch on the cause. Reading intent out of a sentence is exactly the
fragility the two-family error taxonomy was designed to avoid.

---

## 7. P-U7-06: Registry-Derived Configuration Checks

**Delivers**: U7-NFR-MNT-01 to U7-NFR-MNT-07

Chat mode files are parsed and compared against a registry built in memory with a
throwaway SQLite connection. The check asserts names, tiers and exclusions — none of
which depends on data.

**Building an empty registry rather than a live application** keeps the failure
attributable. A check that needs credentials would fail when credentials are missing,
and a documentation problem would present as a configuration problem. The tool
surface's *shape* is what is being checked, and shape does not depend on data.

Ordinary pytest tests, not a separate linter. One command, one report — a check that
must be remembered separately is a check that stops being run.

---

## 8. Patterns Deliberately Not Used in U7

Beyond the nine U1 declined, three were considered specifically for this unit.

| Pattern | Why not |
|---|---|
| **Persistent gate-state cache** | Would make every write path responsible for invalidating it — the same objection that ruled out pre-computed summaries at U1. Gate evaluation is cheap; the hash was the only expensive part, and P-U7-01 handles it. |
| **Generated chat mode files** | Removes drift entirely, but the prose in a mode file is what tells the model how to behave in that stage. Generating them would discard the substance to protect the index. |
| **Automatic stale lease reclamation** | The failure mode is silent data corruption when the "stale" session is actually alive. No detection heuristic is reliable enough to justify it, and the operator can simply look. |

---

## 9. Pattern-to-Requirement Coverage

| Requirement group | Delivered by |
|---|---|
| U7-NFR-REL-01, -03, -04 | P-RES-01, P-RES-04, L2 migration runner |
| U7-NFR-REL-02 | **P-U7-03** |
| U7-NFR-REL-05 | **P-U7-02** |
| U7-NFR-PRF-01 | P-U7-02 |
| U7-NFR-PRF-02, -03, -04 | **P-U7-01** |
| U7-NFR-USA-01, -05 | **P-U7-04**, chat mode scoping |
| U7-NFR-USA-02, -03, -04 | **P-U7-05** |
| U7-NFR-MNT-01 to -07 | **P-U7-06** |
| U7-NFR-SEC-01, -02 | P-OBS-01, P-RES-01 |
| U7-NFR-SEC-03 | P-SEC-01 two-level validation |
| U7-NFR-SEC-04 | Inherited P-SEC-02 |
| U7-NFR-SEC-05 | Inherited P-SEC-03 |

**All 26 U7 NFR requirements have a delivering pattern or component.**
