# Logical Components — U7 Orchestration and Agent Layer

**Phase**: CONSTRUCTION | **Unit**: U7 | **Stage**: NFR Design
**Version**: 1.0 | **Date**: 2026-08-29

One supporting component beyond S10, plus a request-scoped helper.

---

## Why One, Not None or Three

| Considered | Decision |
|---|---|
| **L5 GateEvaluator** | **Added** — called by four other units' services, heavily tested, and independent of lease management |
| `LeaseManager` split from S10 | Declined — lease logic is small and inseparable from the state it manages; splitting would leave two components that always change together |
| `AgentLayerValidator` as a runtime component | Declined — the checks answer a build-time question. Nothing at runtime can act on a mismatched mode file, so a runtime component would report a problem to nobody |

`ReportContext` is listed below as a helper rather than a component: it holds no
policy and exists only for the duration of one call.

---

## L5: GateEvaluator

**Ring**: Domain (pure — no I/O, receives state as input)
**Delivers**: U7-NFR-REL-05, U7-NFR-PRF-01, and BR-U7-3

### Responsibility

Decide whether a gate is open, and when it is not, say which of the three conditions
failed and what would open it.

### Interface

```
evaluate(unit_ref, stage, prior_record, current_content_hash) -> GateEvaluation
prior_stage(stage) -> StageName | None
is_role_permitted(stage, role) -> bool
```

`evaluate` takes the prior stage's record and the current content hash **as
arguments**. It does not fetch them.

### Why it is pure

Placing the evaluator in the domain rather than the service ring has three
consequences that matter:

**It can be called from inside a caller's transaction.** S4, S5, S6 and S7 evaluate
gates while holding their own transaction. A component that read from a repository
would join that transaction; one that receives its inputs cannot.

**It is exhaustively testable.** Gate evaluation has three conditions and seven
stages. A pure function over supplied state can be property-tested across every
combination without a database.

**The read-only guarantee is structural.** It has no repository, so it cannot write.
U7-NFR-REL-05 is enforced by what the component lacks rather than by review.

### Role restriction

`is_role_permitted` returns false only for `coverage` with a role other than
`test-lead`. Keeping the rule in one function means the four calling services cannot
disagree about who may approve what.

---

## S10: RunStateService (defined at Application Design, specified here)

**Ring**: Application Service
**Delivers**: U7-NFR-REL-01 to -04, U7-NFR-PRF-02 to -04, U7-NFR-SEC-01 to -03

### Responsibility

Own the lease lifecycle, compose status reports, and record approvals. Delegates all
gate policy to L5.

### Interface

```
begin_unit(unit_ref, stage, regenerate=False) -> Result[UnitLease]
complete_unit(lease_id, unit_ref, stage, metrics) -> Result[None]
fail_unit(lease_id, unit_ref, stage, reason) -> Result[None]
heartbeat(lease_id) -> Result[None]
classify_lease(record, now) -> LeaseStatus
get_status(scope=None) -> StatusReport
approve_stage(unit_ref, stage, approver, role, content_hash) -> Result[Approval]
is_gate_open(unit_ref, stage) -> GateEvaluation
resume_view() -> ResumeReport
```

**There is no `next_unit`, `suggest`, `ready_units` or equivalent.** C-12 is enforced
by the absence, as it is in U1's repository.

### The four callers

S4, S5, S6 and S7 call `is_gate_open` only. That single read-only method is the whole
of the cross-unit surface, which is what keeps the one service-to-service edge in the
system narrow and acyclic.

---

## ReportContext (helper)

**Ring**: Application Service (request-scoped)
**Delivers**: U7-NFR-PRF-03

```
with report_context(coverage_repo) as ctx:
    ctx.coverage_hash(feature_id)   # computed once per feature, per report
```

Created when a report begins, discarded when it ends. Memoises coverage content
hashes for that call only.

**Not a component in its own right** because it holds no policy — it is a
memoisation scope, and giving it component status would overstate what it does. But
its lifetime is a design decision, recorded here: a cache that cannot outlive its
report cannot serve a stale hash, and a stale hash would make a revoked approval look
valid.

---

## Placement

```
        +-------------------------------------------+
        |             MCP SURFACE  M1, M2           |
        |   unit_begin  unit_complete  stage_approve|
        +-------------------------------------------+
                            |
        +-------------------------------------------+
        |     APPLICATION SERVICES                  |
        |     S10 RunStateService                   |
        |     + ReportContext (request-scoped)      |
        +-------------------------------------------+
              |                          |
   +---------------------+    +---------------------+
   |   DOMAIN            |<---|    PORTS  P1        |
   |   L5 GateEvaluator  |    |  RunStateRepository |
   |   pure, no I/O      |    |                     |
   +---------------------+    +---------------------+
                                         ^
        +-------------------------------------------+
        |         ADAPTERS  A2 (U1)                 |
        +-------------------------------------------+

   S4, S5, S6, S7  ----> S10.is_gate_open()   (read-only, no transaction)
```

**Text alternative**: the three MCP tools delegate to S10. S10 depends on the
`RunStateRepository` port and on L5. L5 sits in the domain ring, is pure, and
receives its inputs as arguments. The four other services call only
`is_gate_open`, which is read-only and joins no transaction.

---

## Dependency Rule Verification

| Component | Imports | Violates? |
|---|---|---|
| L5 GateEvaluator | `domain.model` only | No — domain ring, no adapter, no service |
| S10 RunStateService | `domain` (L5, model), `ports.repositories`, `platform` | No |
| ReportContext | `ports.repositories`, `domain.model` | No |

L5 imports nothing outside `domain`, so the import-linter contract holds and the
property suite can exercise it without a database.

---

## Configuration Additions

| Setting | Default | Component | Requirement |
|---|---|---|---|
| `TAAS_LEASE_STALE_MINUTES` | 30 | S10 | U7-NFR-REL-01 |

One addition. Everything else U7 needs is already in the U1 configuration surface.

---

## Agent Layer Consistency Checks

Not components — pytest tests in `tests/unit/test_agent_layer.py`.

| Check | Requirement |
|---|---|
| Every tool named in a mode exists in the registry | U7-NFR-MNT-01 |
| Every registered tool appears in at least one mode | U7-NFR-MNT-02 |
| Every mode includes the universal read tools | U7-NFR-MNT-03 |
| No mode grants a file-write tool | U7-NFR-MNT-04 |
| Every mode names a valid `StageName` | U7-NFR-MNT-05 |
| The repository instructions state all four standing rules | U7-NFR-MNT-06 |
| Every path-scoped instruction declares an `applyTo` glob | U7-NFR-MNT-07 |

**U7-NFR-MNT-04 is the load-bearing one.** It is how FR-AGT-06 stops being an
instruction the model may drift from and becomes a capability that is absent. The
check is what keeps it absent as seventeen more tools are registered by U2 through U8
and the mode files are edited to match.

---

## Requirement Coverage

All 26 U7 NFR requirements have a delivering pattern (in
[nfr-design-patterns.md](nfr-design-patterns.md) §9) or one of the components above.
