# Services

**Project**: TTO Test Analyst Agent System (TAAS)
**Stage**: INCEPTION - Application Design
**Version**: 1.0
**Date**: 2026-08-28

---

## Orchestration Model

Per the Q5 decision: **services orchestrate within a unit of work; the agent orchestrates between
units.**

The division follows from what each party is good at. Sequencing that must be correct — validate,
then de-duplicate, then allocate, then commit — is put inside code, where it either happens or the
transaction rolls back. Sequencing that requires judgement — which feature next, is this analysis
good enough to proceed — stays with the operator and the agent, where constraint C-12 puts it.

```
Operator names scope
        |
        v
   Agent selects stage and reasons out the payload
        |
        v
   ONE write-tier MCP tool call
        |
        v
   Service opens transaction
        |
        +--> domain validation
        +--> domain computation
        +--> repository writes
        +--> emitter output
        |
        v
   Commit or roll back, entirely
        |
        v
   Structured Result returned to agent
        |
        v
   Agent presents the outcome; execution stops at the gate
```

**One tool call, one transaction, one unit of work.** There is no partial application. If a batch of
forty test cases contains one that fails validation, none of the forty are stored and the report
names every failure rather than only the first — so the agent can fix them all in one pass.

---

## Transaction Boundaries

| Service operation | Transaction scope | Rollback consequence |
|---|---|---|
| `ingest_resources` | Per resource, not per run | One unreachable repository does not discard successfully ingested Jira issues |
| `analysis_upsert` | Whole payload | The feature model is coherent or absent; a half-built hierarchy is worse than none |
| `requirements_upsert` | Whole payload per feature | Requirements for a feature land together |
| `coverage_build` | Whole model | The model is internally consistent or not stored |
| `coverage_approve` | Single record | — |
| `testcases_upsert` | Whole batch per feature | All cases in a batch, or none |
| `automation_emit` | Whole feature | Partial emission would leave a project that does not compile |
| `handover_assemble` | Whole package | — |
| `delta_retire` | Whole impact set | Retirement is all-or-nothing so the corpus is never half-migrated |
| `unit_begin` / `unit_complete` | Single record each | State transitions are atomic by definition |

**The ingestion exception is deliberate.** Every other operation is all-or-nothing because partial
state is meaningless. Ingestion is per-resource because NFR-REL-04 requires failure isolation: at
3-10 repositories and hundreds of Jira issues, one unreachable source must not discard an hour of
successful retrieval.

---

# Service Definitions

## S1: IngestionService

**Responsibility**: turn declared resources into stored artefacts with provenance.

**Orchestrates**: A6 (manifest parsing) → A3/A4/A5 (retrieval) → X4 (isolation and retry) →
P1 repositories (storage)

**Sequence**
1. Parse `resources.md` through A6; report unclassifiable entries
2. For each classified resource, under X4 isolation:
   a. Retrieve through the matching source adapter
   b. Compute content hash; skip if unchanged (NFR-PRF-04)
   c. Normalise to artefact records with provenance
   d. Commit that resource's artefacts
3. Return a report naming successes, skips, failures and unclassified entries

**Gate**: operator confirms the ingested inventory (E1 approval)

---

## S2: AnalysisService

**Responsibility**: hold the application model, part reasoned and part derived.

**Orchestrates**: agent payloads → D1 validation → P1 repositories; A4 → API model derivation

**The reasoned/derived split**

| Model | Produced by | Why |
|---|---|---|
| Feature hierarchy | Agent | Requires judgement about what constitutes a feature |
| User journeys | Agent | Requires understanding intent across screens |
| Business rules | Agent | Requires reading meaning out of prose and code |
| **API model** | **Toolchain** | Endpoint extraction is mechanical; `bitbucket_endpoints` and OpenAPI parsing need no judgement |
| UI model | Agent via Playwright MCP | Requires looking at a screen and deciding what matters |
| Discrepancies | Either | Recorded wherever detected, never resolved automatically |

This table is the architecture's organising idea at method level: reasoning where reasoning is
needed, determinism everywhere else.

**Gate**: operator reviews the application model (E2 approval)

---

## S3: TestableRequirementService

**Responsibility**: atomic requirements that are classified, rated and traceable.

**Orchestrates**: D7 (atomicity validation) → D6 (risk rating) → D3 (Jira key enforcement) →
P1 repositories

**Sequence**
1. Validate each candidate is atomic and not a restatement of an existing requirement
2. Rate risk through D6, recording every contributing factor
3. Enforce the Jira key rule through D3; where no direct link exists, attempt commit derivation
4. Route anything unresolvable to the gap set rather than storing it
5. Commit the feature's requirements as one transaction

**Gate**: operator reviews the requirement set (E3 approval)

---

## S4: CoverageService

**Responsibility**: the baseline, its forecast, and the approval that guards it.

**Orchestrates**: D2 (derivation and yield) → P1 repositories → approval records

**Sequence for `build_model`**
1. Load testable requirements and business rules
2. Derive required test types with rationale through D2
3. Derive depth through the test design techniques
4. Apply reduction where combinatorial expansion is unreasonable, recording the technique
5. Compute yield; flag features whose yield is disproportionate to risk, and any at zero
6. Commit the model with a version identifier

**Approval enforcement**
- `approve_baseline` checks the caller's role and refuses any role but Test Lead, recording the
  attempt (US-COV-04 AC4)
- Approval binds to a model version. Modifying the model invalidates the approval, so a
  re-approval is required rather than an old approval silently covering new content
- `is_approved` is consulted by S5 before any case is generated

**Gate**: **Test Lead only** (FR-COV-06) — the one approval restricted to a single role

---

## S5: TestCaseService

**Responsibility**: the transactional heart. Everything that makes the corpus trustworthy happens
here, in one call.

**Orchestrates**: S4 (gate check) → D7 (validation) → D4 (de-duplication) → D5 (identifiers) →
D6 (automatability) → D3 (traceability) → P1 repositories → A8 (views)

**Sequence for `upsert_cases`**
1. Verify the coverage baseline is approved for this feature; refuse with `REJECTED_GATE_CLOSED`
   if not
2. Open one transaction for the whole batch
3. For each candidate case:
   a. D7 validates steps present, expectations present, identifier not self-supplied
   b. D3 resolves and enforces the Jira key
   c. D4 checks for duplicates against the existing corpus and within the batch itself
   d. D6 classifies automatability with a reason
   e. D5 allocates the identifier
4. If any case failed, roll back and return **every** failure with its code and remediation
5. Commit all cases, steps, data and links
6. Emit sharded views through A8
7. Return the batch report with counts, rejections and the derivation of the count

**Why the whole batch fails together**: partial acceptance would leave the agent to reconcile which
of forty cases landed, across a context boundary. Failing the batch and naming every problem lets
one correction pass fix everything.

**Gate**: operator reviews generated cases per batch (E5 approval)

---

## S6: AutomationService

**Responsibility**: deterministic rendering of automatable cases.

**Orchestrates**: P1 repositories (cases, UI model, API model) → A7 (Jinja2 emission)

**Sequence**
1. Select cases classified automatable for the named feature
2. Refuse to proceed for any case lacking a Jira key (FR-AUT-04 AC4 — the rule holds at this
   boundary too)
3. Detect hand-edited files by comparing against last-emitted hashes; stop and report rather than
   overwrite
4. Bind cases to page objects, fixtures and API clients
5. Render through A7 with sorted iteration and pinned formatting so output is byte-identical for
   identical input
6. Reject any rendered output containing a fixed wait or a literal credential
7. Record the emission with its input hash

**Gate**: automation engineer reviews generated code per batch (E6 approval)

---

## S7: HandoverService

**Responsibility**: assemble, verify, and stop.

**Orchestrates**: A7 (project scaffold) → filesystem → verification

**Sequence**
1. Assemble the standard Playwright project structure with pinned dependencies and lockfile
2. Verify every referenced page object, fixture and data file exists
3. Verify TypeScript compiles
4. Verify `playwright test --list` enumerates without error
5. Produce the manifest and reconcile it against the filesystem in both directions
6. Report ready, or report exactly what is broken

**What this service does not do**: push to a repository, create a branch, or write Jenkins
configuration. There is no method for any of them (FR-HND-04).

**Gate**: automation engineer verifies, then pushes manually (E7 approval)

---

## S8: ReportingService

**Responsibility**: every report from a query.

**Orchestrates**: P1 repositories (queries) → D3 (matrix construction) → A9 (rendering)

**Constraint**: no figure in any report is assembled by the model. Every number originates in a
database query (FR-RPT-05). This is what makes the coverage position defensible rather than
asserted.

---

## S9: DeltaService

**Responsibility**: keep the baseline true.

**Orchestrates**: A4 (change detection) → A3 (Jira updates) → D8 (impact) → P1 repositories

**Sequence**
1. Compare the recorded head commit against current; detect a missing recorded head and offer full
   re-baseline rather than producing a meaningless comparison
2. Query Jira for issues updated since the recorded timestamp
3. Map impact through D8 across the traceability graph
4. Report unmapped changes rather than assuming no impact
5. Assess and report scale before proposing any regeneration
6. Soft-retire obsolete cases with reason and originating change event

**Gate**: same gates as the initial baseline (FR-DLT-06)

---

## S10: RunStateService

**Responsibility**: make the run survivable and the gates real.

**Orchestrates**: P1 `RunStateRepository` — this service touches no other service, by design

**Gate enforcement**: `is_gate_open` is consulted by S4, S5, S6 and S7 before they act. The gate is
a service-layer check backed by a stored approval record, not a convention the agent is asked to
honour.

**Lease model**: `unit_begin` returns a lease. `unit_complete` requires it. A lease that is never
completed leaves the unit in `in-progress`, which `get_status` reports honestly on resume — the
operator then decides whether to restart it, rather than the system silently resuming from an
unknown point (US-BAT-03 AC3).

---

## Service Interaction Map

```
                        +---------------------+
                        |     S10 RunState    |
                        |  gates and leases   |
                        +---------------------+
                          ^   ^   ^   ^   ^
                          |   |   |   |   |
   +------+   +------+   +------+   +------+   +------+   +------+
   |  S1  |-->|  S2  |-->|  S3  |-->|  S4  |-->|  S5  |-->|  S6  |
   |ingest|   |analys|   | reqs |   | cover|   | cases|   | autom|
   +------+   +------+   +------+   +------+   +------+   +------+
                                                   |          |
                                                   |          v
                                                   |      +------+
                                                   |      |  S7  |
                                                   |      | hand |
                                                   |      +------+
                                                   v
                                               +------+
                                               |  S8  |
                                               | rept |
                                               +------+

   +------+
   |  S9  |  delta: re-enters the chain at S3 for affected scope only
   +------+
```

**Text alternative**: S1 through S7 form the pipeline in order. S10 gates every one of them and is
called by S4, S5, S6 and S7 before they act. S8 reads from the corpus S5 produces. S9 detects change
and re-enters the pipeline at S3 for the affected scope only, subject to the same gates.
