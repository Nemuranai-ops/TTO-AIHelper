# Functional Design Plan — U7 Orchestration and Agent Layer

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U7 | **Stage**: Functional Design
**Created**: 2026-08-29T13:46:00Z
**Status**: APPROVED 2026-08-29T14:00:00Z - all recommendations accepted

---

## Unit Context

**Responsibility**: make a multi-day run survivable, and give the operator a usable
interface. U7 owns run state and gates, and the Copilot configuration.

**Components**: S10 RunStateService, plus the Agent Layer artefacts —
`.github/copilot-instructions.md`, `.github/instructions/*.instructions.md`,
`.github/chatmodes/*.chatmode.md`, `.github/prompts/*.prompt.md`, `.vscode/mcp.json`.

**Stories** (8): US-BAT-01 to US-BAT-04, US-AGT-01 to US-AGT-04.

**Why U7 is second in the build sequence**: without gates and chat modes, every unit
after it produces output the operator has no interface to review through. U7 is what
makes the other units' work reviewable.

---

## What already exists from U1

U1 built the storage and a thin tool surface over it. U7 builds the service and the
operator interface above them.

| Already built (U1) | Still to build (U7) |
|---|---|
| `RunStateRepository` — durable per-unit state | `RunStateService` — lease lifecycle, gate evaluation, status composition |
| `unit_begin`, `unit_complete`, `stage_approve` as thin wrappers | Gate evaluation those tools delegate to, including approval-hash comparison |
| `unit_state` table with content-hash binding | Stale lock detection and recovery guidance |
| `run_status`, `unit_state_get` read tools | The status *report* the operator actually reads |
| — | The entire Agent Layer |

**The thin wrappers were a deliberate R1 shortcut**, recorded in U1's API layer
summary. This stage decides what the real service does, and whether those wrappers
are superseded or kept.

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Business Rules: stale lock detection

A unit left `in-progress` means a run was interrupted. The database also has its own
lock, which a killed process can leave behind. How should the service tell a genuine
crash from a still-running session?

A) **Lease age plus a liveness marker.** Each lease records a heartbeat timestamp
updated as work proceeds. A lease whose heartbeat is older than a threshold
(default 30 minutes) is reported as stale, with the age stated, and the operator
decides. The service never clears a lease on its own. **(Recommended — clearing a
lock another process still holds is how databases get corrupted, and the operator
has context the service does not)**

B) **Lease age alone**, no heartbeat. Simpler, but a long-running legitimate unit
looks identical to a crashed one.

C) **Process liveness** — record the PID and check whether it is running. Accurate on
one machine, meaningless if two operators share a database over a network mount.

D) **Never detect** — always report `in-progress` and let the operator work it out.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 2 — Business Rules: gate evaluation

FR-BAT-07 stops every stage at a gate. What exactly must be true for a gate to be
open for unit U at stage S?

A) **The prior stage is completed, approved, and the approved content hash still
matches the current content.** Any of the three failing closes the gate, and the
refusal names which one. **(Recommended — the hash comparison is what makes approval
bind to what was approved rather than to a moment in time; without it, editing
approved content silently keeps the approval)**

B) **Completed and approved**, without the hash check. Simpler, and approval survives
edits to the thing approved.

C) **Approved only** — a stage may be approved before it completes.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 3 — Business Rules: what the status report contains

C-12 reserves scope selection to the operator: the agent must not propose the next
unit. What may a status report legitimately contain without crossing that line?

A) **Facts only**: per unit and stage — state, when it changed, who approved, what
it produced, and which gates are currently open. No ordering, no "next", no
highlighting of a suggested candidate. **(Recommended — a report that lists exactly
one open gate at the top is a proposal wearing a report's clothes)**

B) **Facts plus a dependency-ordered listing**, so the operator sees a natural order
without being told what to pick.

C) **Facts plus explicit next-step candidates**, which would reverse the Q19/CQ3
decision that the operator names each batch.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 4 — Business Logic: chat mode scoping

FR-AGT-03 gives each pipeline stage its own chat mode with only that stage's tools.
How strict should the scoping be?

A) **Stage tools plus the universal read tools** (`run_status`, `unit_state_get`,
`health_check`, `features_list`). Every mode can see where it is and what exists;
none can act outside its stage. **(Recommended — a mode that cannot check whether its
gate is open forces the operator to switch modes to answer a question the agent
should be able to answer itself)**

B) **Strictly stage tools only.** Maximum isolation, at the cost of the operator
switching modes to check status.

C) **All read tools in every mode, write tools scoped per stage.** Reads carry no
invariants, so the risk is low and the convenience high — but it lets an ingestion
session query the corpus, which invites work outside its stage.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 5 — Business Logic: instruction enforcement of the state rule

FR-AGT-06 requires all durable state changes to go through `tto-testgen-mcp` rather
than direct file writes. Instructions alone are guidance the model may drift from.
What else should back it?

A) **Instructions, plus chat modes that exclude file-write tools from every pipeline
stage.** The agent cannot write a test case to a file because the mode does not
offer the capability. **(Recommended — the same principle as the read-only source
protocols: a capability that is absent cannot be misused, and it does not depend on
the model remembering)**

B) **Instructions only**, relying on the model to comply.

C) **Instructions plus a post-hoc check** that flags files written outside
`generated/`.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 6 — Error Handling: what the operator sees when a gate is closed

A closed gate is the most common refusal the operator will meet. What should the
message contain?

A) **Which gate, why it is closed, and the exact action that opens it** — including
who may perform it when the stage is role-restricted. **(Recommended — "gate closed"
without the remedy makes the operator hunt through documentation for something the
system already knows)**

B) **Which gate and why**, leaving the remedy to the documentation.

C) **A generic refusal** with a pointer to `run_status`.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 7 — Business Scenarios: resuming after a context-window exhaustion

A Copilot session can end mid-unit without the process dying — the context window
fills, or the operator starts a new chat. The database still holds an `in-progress`
lease, but no crash occurred.

A) **Treat it identically to a crash.** The unit is `in-progress`, the operator is
told when it started and what it had produced, and they choose to resume or restart.
The service does not distinguish the causes, because the recovery is the same.
**(Recommended — distinguishing them adds a code path with no different outcome)**

B) **Detect it separately** via a session identifier and offer a distinct message.

C) **Auto-resume** from the last committed unit boundary.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

# Execution Checklist

## Phase 1: Domain and Service Logic

- [x] 1.1 Define the lease lifecycle: issue, heartbeat, complete, expire
- [x] 1.2 Define stale-lock detection per the Question 1 answer
- [x] 1.3 Define gate evaluation per the Question 2 answer, including hash comparison
- [x] 1.4 Define approval rules, including the Test Lead restriction on coverage
- [x] 1.5 Define status composition per the Question 3 answer
- [x] 1.6 Define the resume decision flow per the Question 7 answer
- [x] 1.7 Define state transition validity — which transitions are legal
- [x] 1.8 Write `business-rules.md`

## Phase 2: Domain Entities

- [x] 2.1 Define the lease record and its relationship to `unit_state`
- [x] 2.2 Define the gate evaluation result type
- [x] 2.3 Define the status report structure
- [x] 2.4 Confirm no new database entity is required, or specify the migration if one is
- [x] 2.5 Write `domain-entities.md`

## Phase 3: Agent Layer Design

- [x] 3.1 Define the repository instruction content and its standing rules
- [x] 3.2 Define the chat mode set, one per pipeline stage, with tool scoping per Question 4
- [x] 3.3 Define path-scoped instruction files and their `applyTo` globs
- [x] 3.4 Define the prompt file set for recurring tasks
- [x] 3.5 Define the MCP registration and its credential handling
- [x] 3.6 Define how the state rule is enforced per Question 5
- [x] 3.7 Write `frontend-components.md` covering the Agent Layer as the operator interface

## Phase 4: Business Logic Model

- [x] 4.1 Model the lease and gate algorithms
- [x] 4.2 Model the interaction between S10 and the U1 tools already built
- [x] 4.3 Decide whether the U1 thin wrappers are superseded or retained
- [x] 4.4 Model the operator's end-to-end interaction for one unit
- [x] 4.5 Identify the property-based test surface for U7
- [x] 4.6 Write `business-logic-model.md`

## Phase 5: Validation

- [x] 5.1 Verify all 8 U7 stories are served
- [x] 5.2 Verify C-12 is upheld — nothing proposes the next unit
- [x] 5.3 Verify FR-BAT-01 to FR-BAT-07 and FR-AGT-01 to FR-AGT-06 are covered
- [x] 5.4 Verify the design stays technology-agnostic where it can
- [x] 5.5 Verify Security and Resiliency applicability at this stage
- [x] 5.6 Validate content per `common/content-validation.md`
- [x] 5.7 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `aidlc-docs/construction/u7-orchestration-agent-layer/functional-design/domain-entities.md`
- [x] `aidlc-docs/construction/u7-orchestration-agent-layer/functional-design/business-rules.md`
- [x] `aidlc-docs/construction/u7-orchestration-agent-layer/functional-design/business-logic-model.md`
- [x] `aidlc-docs/construction/u7-orchestration-agent-layer/functional-design/frontend-components.md`

**`frontend-components.md` applies here.** U1 had no UI and the file was correctly
omitted. U7 owns the Agent Layer, which *is* the system's user interface — the chat
modes, instructions and prompt files are the operator's entire interaction surface.
The rule's intent is a UI design artefact, and this unit has one.
