# Business Rules — U7 Orchestration and Agent Layer

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U7 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-29

U7 owns the rules that make a multi-day run survivable and the gates real. U1 stores
the state; these rules decide what it means.

---

# BR-U7-1: Lease Lifecycle

A lease is the claim a session holds on one unit at one stage. It is what ties a
completion to the run that started it.

## BR-U7-1.1 States and transitions

```
                    unit_begin
   not-started  ------------------->  in-progress
                                         |    |
                       unit_complete     |    |  unit_fail
                                         v    v
                                    completed  failed
                                         |         |
                          unit_begin     |         | unit_begin
                          (regenerate)   |         | (no flag needed)
                                         v         v
                                    in-progress  in-progress
```

| From | To | Trigger | Condition |
|---|---|---|---|
| `not-started` | `in-progress` | `unit_begin` | none |
| `in-progress` | `completed` | `unit_complete` | lease matches |
| `in-progress` | `failed` | `unit_fail` | lease matches, reason given |
| `in-progress` | `in-progress` | `unit_begin` | **refused** — see BR-U7-2 |
| `completed` | `in-progress` | `unit_begin` | `regenerate=true` required |
| `failed` | `in-progress` | `unit_begin` | no flag needed — a failed unit is meant to be retried |
| any | `needs-review` | `unit_flag` | reviewer intervention |

**A failed unit needs no regenerate flag; a completed one does.** Retrying a failure
is the expected next action. Re-running a success is a decision with consequences —
it can discard reviewed work — so it must be stated.

## BR-U7-1.2 Heartbeat

The lease carries `last_heartbeat`, refreshed whenever the holding session performs
work against that unit. It is what separates a long-running unit from an abandoned
one.

| Field | Meaning |
|---|---|
| `lease_id` | UUIDv4, issued at `unit_begin` |
| `leased_at` | When the claim was made |
| `last_heartbeat` | Last sign of life |
| `lease_holder` | Correlation id of the claiming session |

## BR-U7-1.3 Completion requires the matching lease

`unit_complete` supplies its `lease_id`. A mismatch is refused with `FAILED_LOCKED`.

Without this, a session that lost its claim could mark complete work that another
session is midway through — and the second session's output would then be attributed
to a state it never reached.

---

# BR-U7-2: Stale Lock Detection

**Decision**: lease age plus heartbeat. The service reports; the operator decides.

## BR-U7-2.1 Classification

| Condition | Report | Guidance offered |
|---|---|---|
| `last_heartbeat` within 30 minutes | **active** | Another session appears to hold this unit |
| `last_heartbeat` older than 30 minutes | **stale** | Age stated; restart with `regenerate=true` if the session has ended |
| No heartbeat, `leased_at` older than 30 minutes | **stale** | As above |
| Database file lock held, no matching lease | **orphaned lock** | Verify no TAAS process is running, then retry |

The threshold is configurable (`TAAS_LEASE_STALE_MINUTES`, default 30).

## BR-U7-2.2 The service never clears a lease

Not on staleness, not on age, not on any heuristic. It reports the state, its age,
and what would clear it. The operator acts.

**Clearing a lock another process still holds is how databases get corrupted.** The
service cannot know whether the other session is dead or merely slow; the operator
can look. A heuristic that is right 95% of the time is wrong in exactly the situation
where being wrong is most expensive.

## BR-U7-2.3 Recovery guidance is specific

A stale lease report states the unit, the stage, the age, what the unit had produced
before it stopped, and the exact command to restart it.

---

# BR-U7-3: Gate Evaluation

**Decision**: three conditions, all required. The refusal names which failed.

## BR-U7-3.1 The three conditions

A gate is open for unit `U` at stage `S` when **all** hold for the prior stage `P`:

1. **`P` is `completed`** — the work exists
2. **`P` is approved** — a human saw it
3. **`P`'s `approved_content_hash` equals the current content hash** — they saw *this*

## BR-U7-3.2 Why the hash is not optional

Conditions 1 and 2 make approval a fact about a moment. Condition 3 makes it a fact
about content.

Without it: a Test Lead approves a coverage baseline, someone adjusts the model, and
generation proceeds against an unapproved model carrying an approval that was never
given to it. Nothing fails. The coverage position is then indefensible in exactly the
way FR-COV-06 exists to prevent.

## BR-U7-3.3 The refusal names the condition

| Failed condition | Message | Remediation |
|---|---|---|
| Not completed | `{P} is not complete` | Complete `{P}` for `{U}` first |
| Not approved | `{P} is complete but not approved` | Approve `{P}` — names the permitted role if restricted |
| Hash mismatch | `{P} was approved, but its content has changed since` | Re-approve `{P}`; the prior approval no longer applies |

"Gate closed" without the remedy makes the operator hunt documentation for something
the system already knows.

## BR-U7-3.4 Stage order

`ingest` → `analyse` → `requirements` → `coverage` → `cases` → `automation` →
`handover`. The first stage has no prior, so its gate is always open.

## BR-U7-3.5 Role restriction

Only `coverage` is role-restricted, to `test-lead` (FR-COV-06). An attempt by another
role is refused with `REJECTED_ROLE_NOT_PERMITTED` and recorded with the actor.

Recording matters: an approval attempted by the wrong role is a process signal, not
merely a rejected call.

---

# BR-U7-4: Status Composition

**Decision**: facts only. No ordering, no next-step candidate.

## BR-U7-4.1 What a report contains

Per unit and stage: state, when it last changed, who approved and when, what it
produced (from `metrics`), whether its gate is currently open, and lease age where
`in-progress`. Plus corpus totals: active cases, features, requirements.

## BR-U7-4.2 What it must not contain

- Any field named or rendered as "next"
- Ordering by readiness, dependency, or any priority
- Highlighting, emphasis, or truncation that surfaces one unit above others
- A count framed as remaining work in a suggested sequence

**C-12 reserves scope selection to the operator.** A report listing exactly one open
gate at the top is a proposal wearing a report's clothes. Sorting is by unit
reference and stage order — stable, and carrying no signal about what to do next.

## BR-U7-4.3 Filtering is permitted

The operator may filter by unit, stage or state. Filtering is the operator expressing
an interest they already have; ordering by readiness is the system expressing one.

---

# BR-U7-5: Resume After Interruption

**Decision**: every interruption is treated identically.

## BR-U7-5.1 One path, several causes

A process kill, a context-window exhaustion, a closed editor, a lost connection — all
leave the same state: a unit `in-progress` with a lease whose heartbeat has stopped.

The recovery is identical in every case, so the service does not distinguish them.
Adding a code path that produces the same outcome adds surface without adding value.

## BR-U7-5.2 What resume presents

1. Which units are `in-progress`, with lease age
2. What each had produced before stopping, from `metrics` and the corpus
3. What is `completed` and approved
4. The choice: restart the unit, or leave it and work elsewhere

## BR-U7-5.3 Never resume from an unknown point

The system does not continue a partially-processed unit. Unit work is transactional:
either it committed or it did not. A unit that stopped mid-way produced nothing
durable, so "resuming" it means running it again (US-BAT-03 AC3).

## BR-U7-5.4 Completed work is never at risk

Interruption cannot damage a completed unit. The transaction boundary guarantees it,
and this is what makes a multi-day run across many sessions viable at all.

---

# BR-U7-6: Agent Layer Tool Scoping

**Decision**: stage tools plus universal read tools.

## BR-U7-6.1 Universal reads

`run_status`, `unit_state_get`, `health_check`, `features_list` are available in
every chat mode.

A mode that cannot check whether its own gate is open forces the operator to switch
modes to answer a question the agent should be able to answer itself.

## BR-U7-6.2 Stage tools

| Chat mode | Additional tools |
|---|---|
| Ingest | `ingest_resources`, `resources_list`, `artefacts_query` |
| Analyse | `analysis_upsert`, `api_model_derive`, `ui_model_upsert`, `artefacts_query`, `feature_get` |
| Requirements | `requirements_upsert`, `requirements_query`, `feature_get`, `trace_query` |
| Coverage | `coverage_build`, `coverage_approve`, `coverage_reduce`, `coverage_get`, `coverage_forecast`, `requirements_query` |
| Cases | `testcases_upsert`, `views_emit`, `testcases_query`, `testcase_get`, `duplicates_check`, `coverage_get` |
| Automation | `automation_emit`, `testcases_query`, `testcase_get` |
| Handover | `handover_assemble`, `handover_verify`, `reports_generate` |

`unit_begin`, `unit_complete` and `stage_approve` are available in every mode — a
mode that cannot claim or complete its own unit cannot do its job.

## BR-U7-6.3 No file-write tool in any pipeline mode

FR-AGT-06 requires durable state to go through `tto-testgen-mcp`. Instructions alone
are guidance the model may drift from over a long session.

Excluding file-write capability from every pipeline chat mode makes the rule
structural: the agent cannot write a test case to a file because the mode does not
offer the capability. The same principle as the read-only source protocols — an
absent capability cannot be misused, and it does not depend on remembering.

Emitters write files, but they run *inside* the toolchain, not through an agent tool.

---

# BR-U7-7: State Transition Validity

| Attempted | Permitted | Refusal |
|---|---|---|
| `unit_complete` on a unit never begun | No | `FAILED_INTERNAL` — call `unit_begin` first |
| `unit_complete` with a non-matching lease | No | `FAILED_LOCKED` |
| `unit_begin` on `in-progress` | No | `FAILED_LOCKED`, with staleness assessment |
| `unit_begin` on `completed` without flag | No | `REJECTED_ALREADY_COMPLETE` |
| `unit_begin` on `completed` with flag | Yes | — |
| `unit_begin` on `failed` | Yes | — |
| `stage_approve` on an incomplete stage | Yes | Approval is recorded; the gate still requires completion |
| `stage_approve` on `coverage` by a non-lead | No | `REJECTED_ROLE_NOT_PERMITTED`, attempt recorded |

**Approving an incomplete stage is permitted deliberately.** Approval and completion
are independent facts, and a Test Lead may reasonably approve a model before the unit
that produced it is formally closed. The gate requires both, so nothing is bypassed.

---

# Rule-to-Requirement Traceability

| Rule | Requirements | Stories |
|---|---|---|
| BR-U7-1 Lease lifecycle | FR-BAT-02, FR-BAT-05, FR-BAT-06 | US-BAT-01, US-BAT-02 |
| BR-U7-2 Stale lock detection | FR-BAT-04, NFR-REL-06 | US-BAT-03 |
| BR-U7-3 Gate evaluation | FR-BAT-07, FR-COV-06 | US-BAT-04 |
| BR-U7-4 Status composition | FR-BAT-03, C-12 | US-BAT-01, US-BAT-02 |
| BR-U7-5 Resume | FR-BAT-04 | US-BAT-03 |
| BR-U7-6 Tool scoping | FR-AGT-03, FR-AGT-06, NFR-USA-01 | US-AGT-02, US-AGT-01 |
| BR-U7-7 Transition validity | FR-BAT-01, FR-BAT-06, FR-BAT-07 | US-BAT-01, US-BAT-04 |
