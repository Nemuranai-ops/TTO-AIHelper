# Story Generation Plan

**Project**: TTO Test Analyst Agent System (TAAS)
**Stage**: INCEPTION - User Stories (Part 1: Planning)
**Created**: 2026-08-28T09:06:00Z
**Status**: APPROVED 2026-08-28T09:20:00Z - Part 2 generation in progress

---

## Purpose

This plan defines *how* user stories and personas will be produced for TAAS. It does not contain
the stories themselves — those are generated in Part 2, after this plan is answered and approved.

The assessment justifying this stage is at
[user-stories-assessment.md](user-stories-assessment.md).

---

## Context Carried Forward

From `aidlc-docs/inception/requirements/requirements.md` v1.0:

- **3 actors**: Test Analyst (operator), Test Automation Engineer, Test Lead
- **79 functional requirements** in 12 groups, **48 non-functional requirements** in 8 categories
- **7 pipeline stages**, each ending at a human gate
- **12 hard constraints**, of which C-12 (operator names batch scope) most shapes interaction design
- **4 open decisions** (OD-01 to OD-04) deferred to the NFR Requirements stage

A structural fact worth stating before the questions: a meaningful share of the functional
requirements describe work the operator never sees directly — the SQLite schema, MCP server
plumbing, ingestion adapters, the de-duplication algorithm. How that work is represented is
Question 2, and it is the question most likely to affect the shape of the backlog.

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis. Tell me when done.

## Question 1
How should the stories be broken down and organised?

A) **Epic-based, with epics aligned to the 7 pipeline stages** plus cross-cutting epics for
traceability, batch/state, and reporting. Each epic holds stories for the roles it serves. Maps
cleanly onto Units Generation later, because a pipeline stage is a genuine deliverable boundary.
**(Recommended)**

B) **User journey-based** — stories follow the operator's end-to-end path from `resources.md` to
handover. Reads well as a narrative, but produces stories that cut across every component, which
makes unit decomposition harder.

C) **Persona-based** — grouped by Test Analyst, Automation Engineer, Test Lead. Clarifies role
boundaries, but scatters each pipeline stage across three groups.

D) **Feature-based** — grouped by system capability (ingestion, analysis, generation, reporting)
without the pipeline framing.

E) **Hybrid: epic-based primary structure, with a journey map as a supporting view** — epics for
structure, plus one document showing how a full run reads end to end.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 2
Much of this system is machinery the operator never touches directly — the SQLite schema, the MCP
server scaffolding, the ingestion adapters, the similarity algorithm. How should that work appear
in the backlog?

A) **Enabler stories in a separate technical epic**, written plainly ("As the toolchain, I need a
versioned SQLite schema so that...") and explicitly flagged as enablers rather than user value.
Honest about what they are, and keeps them visible and estimable. **(Recommended — the alternative is either fiction or invisible work)**

B) **Folded into the user stories they support** — no separate enabler stories; the schema work is
part of "As a Test Analyst, I want my generated cases to persist...". Keeps every story
user-valued, but hides significant effort inside deceptively small stories.

C) **Captured as technical tasks under each story**, not as stories in their own right.

D) **Kept out of the story set entirely** and handled during Application Design and Units Generation.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 3
What story granularity should be targeted?

A) **Capability-sized** — each story is one coherent, demonstrable capability, typically mapping to
3-8 functional requirements. Expect roughly 35-50 stories. Small enough to reason about, large
enough that the backlog stays readable. **(Recommended)**

B) **Fine-grained** — roughly one story per functional requirement. Expect 80+ stories. Maximum
traceability precision, at the cost of a backlog nobody reads end to end.

C) **Coarse-grained** — one story per epic-level capability. Expect 12-18 stories. Readable, but
too large to estimate or to complete within a single unit of work.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 4
What format should acceptance criteria take?

A) **Given/When/Then scenarios**, including the negative and error paths, not just the happy path.
Directly verifiable, and it sets the standard the system itself is meant to produce. **(Recommended — a test-generation system whose own acceptance criteria are vague would be an awkward artefact)**

B) **Checklist of verifiable statements** — simpler to write and scan, less precise about
preconditions and triggers.

C) **Given/When/Then for behavioural stories, checklists for enabler stories** — matching the form
to the kind of work.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 5
How much depth should the personas carry?

A) **Working profiles** — role, goals, what they approve, their frustrations with the manual
process today, what "good" looks like to them, and which stories serve them. Enough to settle
design arguments, not so much that it becomes fiction. **(Recommended)**

B) **Brief role definitions** — a paragraph each.

C) **Full personas** — names, backgrounds, day-in-the-life narratives, experience levels.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 6
How should stories trace back to requirements?

A) **Every story carries explicit FR and NFR identifiers**, and the generated `stories.md` includes
a coverage table proving every requirement in `requirements.md` is served by at least one story —
with any deliberate omissions named. **(Recommended — the same discipline this system is being built to enforce should apply to its own construction)**

B) **Epic-level traceability only** — epics reference requirement groups; individual stories do not.

C) **Informal** — stories reference requirements in prose where relevant.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 7
What prioritisation scheme should the stories carry?

A) **MoSCoW** (Must / Should / Could / Won't-this-release) — matches the Must/Should priorities
already assigned in `requirements.md`, so the two documents stay consistent. **(Recommended)**

B) **Value versus risk scoring** — each story rated on business value and delivery risk, ranked by
the combination.

C) **Release-based** — stories assigned to a first release (walking skeleton), second release, and
later, describing a delivery sequence rather than a ranking.

D) **MoSCoW plus a nominated walking-skeleton set** — priorities as in A, with the thin end-to-end
slice explicitly identified.

X) Other (please describe after [Answer]: tag below)

[Answer]: C

---

# Execution Checklist

To be executed in Part 2, after this plan is approved. Each step is marked `[x]` in the same
interaction in which it is completed.

## Phase 1: Foundation

- [x] 1.1 Load `requirements.md` v1.0 and extract the full actor set, requirement groups, and constraints
- [x] 1.2 Apply the approved breakdown approach from Question 1 to define the epic structure
- [x] 1.3 Define the story identifier scheme and the traceability convention from Question 6
- [x] 1.4 Define the story template reflecting the format decisions from Questions 3, 4 and 7

## Phase 2: Personas

- [x] 2.1 Draft the Test Analyst persona at the depth chosen in Question 5
- [x] 2.2 Draft the Test Automation Engineer persona
- [x] 2.3 Draft the Test Lead persona
- [x] 2.4 Record each persona's goals, approval authority, pain points in the current manual process, and success measures
- [x] 2.5 Write `aidlc-docs/inception/user-stories/personas.md`

## Phase 3: Story Generation

- [x] 3.1 Generate stories for the Input Sources epic
- [x] 3.2 Generate stories for the Analyse and Understand epic
- [x] 3.3 Generate stories for the Identify Testable Requirements epic
- [x] 3.4 Generate stories for the Establish Coverage Baseline epic
- [x] 3.5 Generate stories for the Generate Test Cases epic
- [x] 3.6 Generate stories for the Generate Automation epic
- [x] 3.7 Generate stories for the Handover Package epic
- [x] 3.8 Generate stories for the Traceability cross-cutting epic
- [x] 3.9 Generate stories for the Batch, State and Resumability cross-cutting epic
- [x] 3.10 Generate stories for the Incremental Re-baselining epic
- [x] 3.11 Generate stories for the Reporting epic
- [x] 3.12 Generate stories for the Agent Layer epic (instructions, chat modes, prompt files, MCP registration)
- [x] 3.13 Generate enabler stories per the decision in Question 2

## Phase 4: Quality Assurance

- [x] 4.1 Verify every story satisfies INVEST — Independent, Negotiable, Valuable, Estimable, Small, Testable
- [x] 4.2 Verify every story has acceptance criteria in the approved format, covering negative and error paths
- [x] 4.3 Verify every story carries a persona mapping
- [x] 4.4 Verify every story carries a priority
- [x] 4.5 Build the requirement coverage table and confirm every FR and NFR in `requirements.md` is served by at least one story
- [x] 4.6 Name any requirement deliberately not covered by a story, with the reason
- [x] 4.7 Check for overlapping or duplicate stories across epics
- [x] 4.8 Confirm no story depends on an undelivered story in a way that breaks Independence, and record genuine sequencing constraints explicitly

## Phase 5: Assembly

- [x] 5.1 Write `aidlc-docs/inception/user-stories/stories.md` with all epics, stories and the coverage table
- [x] 5.2 Add the persona-to-story mapping
- [x] 5.3 Validate all content per `common/content-validation.md` before writing
- [x] 5.4 Update `aidlc-docs/aidlc-state.md`
- [x] 5.5 Log completion in `aidlc-docs/audit.md`
- [x] 5.6 Present the completion message and await approval

---

# Mandatory Artifacts

These are produced regardless of the answers above:

- [x] `aidlc-docs/inception/user-stories/stories.md` — user stories following INVEST criteria
- [x] `aidlc-docs/inception/user-stories/personas.md` — user archetypes and characteristics
- [x] Every story verified Independent, Negotiable, Valuable, Estimable, Small, Testable
- [x] Acceptance criteria included for every story
- [x] Personas mapped to the stories they serve

---

# Story Breakdown Approaches Considered

Recorded for the audit trail, per `user-stories.md` Step 5.

| Approach | Benefit | Cost | Fit here |
|---|---|---|---|
| **User Journey-Based** | Reads as a narrative; keeps the operator's experience central | Stories cut across every component, making unit decomposition harder | Good supporting view, weak primary structure |
| **Feature-Based** | Familiar; groups by capability | Loses the pipeline sequencing that defines this system's behaviour | Adequate, not ideal |
| **Persona-Based** | Sharpens role boundaries and approval authority | Scatters each pipeline stage across three groups; duplicates context | Useful as a secondary index |
| **Domain-Based** | Suits systems with strong bounded contexts | This system's domains are thin — it is a pipeline, not a domain model | Poor fit |
| **Epic-Based (pipeline-aligned)** | Epic boundaries are real deliverable boundaries; feeds Units Generation directly; each epic is independently demonstrable | Cross-cutting concerns need their own epics rather than being distributed | Strong fit |
| **Hybrid (epic primary + journey view)** | Structural benefits of epics, narrative benefit of journeys | One extra document to keep current | Strong fit at slightly higher cost |

**Decision criteria for a hybrid**: if the journey view is chosen as a supplement, it is a derived
read-only view — epics remain the single structure stories belong to, and the journey document
references stories by identifier rather than restating them.
