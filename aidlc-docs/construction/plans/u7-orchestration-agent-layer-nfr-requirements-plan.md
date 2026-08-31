# NFR Requirements Plan — U7 Orchestration and Agent Layer

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U7 | **Stage**: NFR Requirements
**Created**: 2026-08-29T14:31:00Z
**Status**: APPROVED 2026-08-29T14:45:00Z - all recommendations accepted

---

## What U7 inherits, and what is left to decide

U1's NFR Requirements stage settled the cross-cutting qualities once, for every unit.
U7 inherits all of them and re-opens none:

| Inherited from U1 | Status |
|---|---|
| OD-01 corpus recovery point | Closed — backup before destructive ops, export per unit |
| OD-02 toolchain distribution and rollback | Closed — git clone plus `uv sync` |
| OD-03 recovery rehearsal | Closed — before 1,000 cases and after each migration |
| OD-04 encryption at rest | Closed — organisational full-disk encryption (assumption AS-02) |
| All 8 Resiliency decision points | Answered |
| Tech stack | Fixed: Python 3.11+, `uv`, `mcp` SDK, Pydantic v2, stdlib `sqlite3`, pytest, Hypothesis |
| 37 of 47 project NFRs | Owned by U1 |

**U7 owns three of the remaining ten**: NFR-USA-01 (one instruction per stage) and
NFR-USA-03 (say what could not be determined), plus a share of NFR-MNT-08
(maintainable generated artefacts — here, the Agent Layer's own maintainability).

This stage is therefore short. Five questions, all specific to this unit.

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Reliability: the lease staleness threshold

BR-U7-2 reports a lease as stale when its heartbeat is older than a threshold. The
functional design proposed 30 minutes as a default.

A) **30 minutes, configurable.** Long enough that a genuinely working session is not
mislabelled, short enough that a crashed one is noticed in the same working session.
**(Recommended — a unit is a single feature's work, and one that has produced nothing
in half an hour has almost certainly stopped)**

B) **2 hours** — very unlikely to mislabel an active session, at the cost of an
operator waiting a long time before the system tells them anything is wrong.

C) **10 minutes** — fast detection, but a unit legitimately waiting on a slow Jira
query or a long Playwright exploration would be reported stale while working.

D) **No default; require the operator to set it.** Explicit, and one more thing to
configure before anything runs.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 2 — Maintainability: keeping chat modes in step with the tool surface

The seven chat modes each list the tools that stage may use. As U2 through U8
register their write tools, those lists must stay accurate. A mode listing a tool
that does not exist, or omitting one that does, fails at the worst moment — mid-run,
in front of the operator.

A) **A test asserts every tool named in a chat mode exists in the registry, and every
registered tool appears in at least one mode.** Drift fails the build rather than the
run. **(Recommended — this is the same class of problem as the import contracts, and
the same answer: a machine check, because a documentation convention will not hold
across eight units)**

B) **Generate the mode files from the registry** at build time. No drift possible, at
the cost of the modes no longer being hand-editable prose.

C) **Review discipline** — a checklist item when a unit registers new tools.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 3 — Usability: refusal verbosity

Closed gates are the most common refusal the operator will meet. How much should a
refusal say?

A) **The gate, the failed condition, the remedy, and who may perform it — in two or
three sentences.** Enough to act on without reading documentation, short enough to
read at a glance. **(Recommended)**

B) **Terse** — the gate and the failed condition, with the remedy in the docs.

C) **Verbose** — the above plus the full stage history and every related requirement
identifier.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 4 — Performance: status composition

`run_status` evaluates the gate for every unit and stage it reports. At 8 units and 7
stages that is 56 gate evaluations, each reading state and possibly hashing coverage
content.

A) **Compute gates lazily — only for units the report actually includes, and cache
the coverage content hash for the duration of one report.** Keeps the common filtered
call cheap and bounds the unfiltered one. **(Recommended — the hash is the expensive
part, and it cannot change during a single read)**

B) **Compute every gate on every call**, no caching. Simplest, and the unfiltered
report re-hashes the same coverage content repeatedly.

C) **Precompute gate state on write** and store it. Fastest reads, and it puts a
consistency obligation on every write path.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 5 — Maintainability: testing the Agent Layer

The chat modes, instructions and prompt files are Markdown, not code. What can
usefully be asserted about them?

A) **Structural checks**: every mode file parses, names a stage that exists, lists
only registered tools, includes the universal reads, and excludes file-write tools.
Plus: the repository instructions state the four standing rules. **(Recommended —
these are the properties that break silently, and each is mechanically checkable)**

B) **Existence only** — the files are present and non-empty.

C) **No automated checks** — the Agent Layer is prose and is reviewed by reading it.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

# Execution Checklist

## Phase 1: NFR Determination

- [x] 1.1 Record reliability requirements: lease threshold, transition safety
- [x] 1.2 Record performance requirements for status composition
- [x] 1.3 Record usability requirements: refusal content, mode opening behaviour
- [x] 1.4 Record maintainability requirements: mode-registry consistency, Agent Layer checks
- [x] 1.5 Record security requirements specific to U7 (approval attribution, role validity)
- [x] 1.6 Confirm every inherited U1 decision applies unchanged, and record any that does not
- [x] 1.7 Write `nfr-requirements.md`

## Phase 2: Tech Stack

- [x] 2.1 Confirm the U1 stack applies to U7 without addition
- [x] 2.2 Record any U7-specific dependency, or state that there is none
- [x] 2.3 Record the Agent Layer file formats and their constraints
- [x] 2.4 Write `tech-stack-decisions.md`

## Phase 3: Validation

- [x] 3.1 Verify the three U7-owned project NFRs are addressed
- [x] 3.2 Verify no inherited decision is silently re-opened
- [x] 3.3 Verify Security and Resiliency applicability at this stage
- [x] 3.4 Validate content per `common/content-validation.md`
- [x] 3.5 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `aidlc-docs/construction/u7-orchestration-agent-layer/nfr-requirements/nfr-requirements.md`
- [x] `aidlc-docs/construction/u7-orchestration-agent-layer/nfr-requirements/tech-stack-decisions.md`
