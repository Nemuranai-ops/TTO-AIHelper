# Unit of Work Dependencies

**Project**: TTO Test Analyst Agent System (TAAS)
**Stage**: INCEPTION - Units Generation
**Version**: 1.0
**Date**: 2026-08-28

---

## Dependency Matrix

`X` = depends on. Read as: the row unit cannot be completed without the column unit.

| From \ To | U1 | U2 | U3 | U4 | U5 | U6 | U7 | U8 |
|---|---|---|---|---|---|---|---|---|
| **U1** Core Platform | — | | | | | | | |
| **U2** Ingestion and Analysis | X | — | | | | | | |
| **U3** Requirements and Coverage | X | X | — | | | | | |
| **U4** Test Case Generation | X | | X | — | | | X* | |
| **U5** Automation Emission | X | | | X | — | | X* | |
| **U6** Handover | X | | | | X | — | X* | |
| **U7** Orchestration and Agent Layer | X | | | | | | — | |
| **U8** Reporting and Re-baselining | X | X | | X | | | | — |

`X*` denotes the gate-check call `S10.is_gate_open()`. It is a read-only call into U7 that
participates in no transaction. U3 also makes this call.

### Acyclicity

**Verified acyclic.** A topological order exists:

```
U1  ->  U2  ->  U3  ->  U4  ->  U5  ->  U6
 |                       |
 +---->  U7              +---->  U8
```

No unit depends on a unit later in this order. U7 depends only on U1 and is depended on only for
gate reads, so it cannot participate in a cycle.

---

## Critical Path

```
U1 Core Platform
      |
      v
U2 Ingestion and Analysis
      |
      v
U3 Requirements and Coverage
      |
      v
U4 Test Case Generation
      |
      v
U5 Automation Emission
      |
      v
U6 Handover
```

**Six units on the critical path.** This is the pipeline itself, and it cannot be shortened —
each stage genuinely consumes what the previous one produces. There is no way to generate a test
case before deciding it should exist.

**U1 is the schedule risk.** Everything waits on it, and it is the largest unit by component count
(20 of 37). It is also where the invariants live, so building it quickly and wrongly is the most
expensive available mistake. The walking-skeleton approach (Q4) is the mitigation: build U1 to R1
depth only, prove it end to end through the pipeline, then thicken it.

---

## Parallelism

Two opportunities exist, both opening as soon as U1 reaches R1 depth.

| Stream | Units | Opens after |
|---|---|---|
| **Main** | U2 → U3 → U4 → U5 → U6 | U1 |
| **Orchestration** | U7 | U1 |
| **Reporting** | U8 | U4 (and U2 for delta) |

```
Time -->

U1 [==========]
U2            [========]
U3                     [==========]
U4                                [========]
U5                                         [======]
U6                                                [===]
U7            [========]
U8                                         [======]
```

**Maximum useful concurrency is 2**, occasionally 3. With the sequential-capable assumption (AS-01)
this is sufficient. A team of four or more would contend, which is the trigger to revisit unit
sizing.

**U7 is the best parallel candidate.** It has one service dependency (U1), no downstream unit waits
on it except for gate reads, and it is what makes every other unit's work reviewable — building it
early means the pipeline units have a working operator interface to be reviewed through.

---

## Integration Approach

**Contract-first with in-memory fakes** (Q5 = A).

### How it works

1. **U1 defines every port protocol** (P1 RepositoryPorts, P2 SourcePorts, P3 EmitterPorts) as part
   of its R1 depth. These are protocol definitions with no implementation.
2. **U1 also ships `tests/fakes/`** — one in-memory implementation per port, shared across all
   units. Not per-unit stubs.
3. **Every other unit codes against protocols**, never against a concrete adapter.
4. **Any unit can be developed and tested before its dependencies have real adapters**, because the
   fake satisfies the protocol.
5. **`composition.py` binds concrete adapters at startup** — the only module that knows both sides.

### Why shared fakes rather than per-unit stubs

Per-unit stubs (Q5 option C) would mean eight in-memory repository implementations that drift apart.
When U3's stub and U4's stub disagree about what `TestCaseRepository.upsert` does, the disagreement
surfaces only at integration. One shared fake makes that impossible.

The hexagonal architecture (Q1 of Application Design) makes this nearly free — the ports already
exist for the property-based tests.

### Contract surfaces between units

| Provider | Consumer | Contract |
|---|---|---|
| U1 | all | Domain types (D1), port protocols (P1-P3), `Result` (X1), MCP tool registration (M2) |
| U2 | U3 | Stored artefacts, feature model, business rules, API model, UI model — read through P1 |
| U2 | U8 | Bitbucket change ranges and commit records for delta detection — through P2 |
| U3 | U4 | Approved coverage model and testable requirements — read through P1 |
| U4 | U5 | Stored test cases with automatability classification — read through P1 |
| U4 | U8 | The corpus and traceability graph — read through P1 |
| U5 | U6 | Emitted TypeScript files on disk plus an emission manifest |
| U7 | U3, U4, U5, U6 | `is_gate_open(unit, stage) -> bool` — read-only, no transaction |

**Every contract except U5-to-U6 is expressed as a port protocol.** U5 to U6 is a filesystem
handoff, because the artefact genuinely is files on disk, and modelling that as a protocol would add
indirection without adding safety.

---

## Build Sequence

Following Q4 — R1 depth across units first, then R2, then R3.

### Pass 1 — Walking Skeleton (R1)

| Order | Unit | R1 scope |
|---|---|---|
| 1 | U1 | Schema with constraints, MCP server, platform, domain kernel |
| 2 | U7 | Run state, gates, repository instructions, chat modes, MCP registration |
| 3 | U2 | `resources.md`, Jira ingest, Bitbucket repos and endpoints, feature model, business rules, API model |
| 4 | U3 | Atomic requirements, coverage model, Test Lead gate |
| 5 | U4 | Structured cases with steps, synthetic data, identifiers, views, tags |
| 6 | U5 | Project scaffold, page objects, API tests, annotations, config, reporters |
| 7 | U6 | Assembly |

**At the end of pass 1, one feature runs end to end** — from a Jira story to a Playwright project on
disk. Every architectural seam has been exercised. If something is structurally wrong, this is where
it surfaces, with one feature's worth of work at risk rather than the whole corpus.

U7 is placed second deliberately: without gates and chat modes, the units after it have no operator
interface to be reviewed through.

### Pass 2 — Production Baseline (R2)

| Order | Unit | R2 scope |
|---|---|---|
| 1 | U1 | Scale and performance, property-based suite |
| 2 | U2 | Confluence, Figma, journeys, UI model with live selectors, discrepancies |
| 3 | U3 | Risk rating, edge cases, depth techniques, yield forecast, commit-derived keys, gap routing |
| 4 | U4 | De-duplication, automatability classification, derived volume, traceability matrix |
| 5 | U5 | Resilient locators, no-fixed-wait enforcement, hand-edit detection, deterministic regeneration |
| 6 | U6 | Integrity and compile verification, handover manifest |
| 7 | U7 | Path-scoped instructions, prompt files |
| 8 | U8 | Coverage, gap and automation reports |

### Pass 3 — Sustaining (R3)

| Order | Unit | R3 scope |
|---|---|---|
| 1 | U8 | Delta detection, impact classification, soft retirement, run history |
| 2 | U3 | Risk-based coverage reduction |

---

## CONSTRUCTION Phase Cost

Per `execution-plan.md`, each unit runs four stages with four gates: Functional Design,
NFR Requirements, NFR Design, Code Generation.

| | Count |
|---|---|
| Units | 8 |
| Stages per unit | 4 |
| Per-unit stage executions | 32 |
| Build and Test | 1 |
| **Total CONSTRUCTION executions** | **33** |

This sits within the 27-39 estimated in the execution plan.

**Where OD-01 to OD-04 are answered**: at U1's NFR Requirements stage. All four decisions concern
the SQLite database, the toolchain's distribution, and recovery — every one of them lands in Core
Platform, so they are settled once rather than revisited per unit.

---

## Risks Introduced by This Decomposition

| Risk | Consequence | Mitigation |
|---|---|---|
| U1 is large and everything waits on it | A slow or wrong U1 delays all seven other units | Build U1 to R1 depth only in pass 1; the walking skeleton proves it before it is thickened |
| U3 is the largest unit by story count (10) | Harder to hold in one design conversation | Its stories split cleanly along the requirements/coverage seam if the Functional Design stage proves unwieldy |
| Two passes per unit means each is revisited | Context reload cost between R1 and R2 for the same unit | Per-unit design artefacts persist under `aidlc-docs/construction/{unit}/`, so pass 2 resumes from written design rather than memory |
| Maximum concurrency of 2-3 | A larger team would contend | AS-01 — revisit sizing if the team turns out to be four or more |
