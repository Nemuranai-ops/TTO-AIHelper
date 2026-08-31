# Unit of Work Plan

**Project**: TTO Test Analyst Agent System (TAAS)
**Stage**: INCEPTION - Units Generation (Part 1: Planning)
**Created**: 2026-08-28T10:46:00Z
**Status**: APPROVED 2026-08-28T10:55:00Z - recommendations accepted; Q6 answered by documented assumption

---

## Purpose

This plan defines *how* the system will be decomposed into units of work. It does not contain the
decomposition itself; that is generated in Part 2, after this plan is answered and approved.

---

## Context

| Input | Content |
|---|---|
| `requirements.md` v1.0 | 88 functional, 47 non-functional requirements, 12 constraints |
| `stories.md` v1.0 | 55 stories, 13 epics, releases R1 (29) / R2 (25) / R3 (4) |
| `application-design.md` v1.0 | 37 components across 6 hexagonal rings; 20 write tools, 16 read tools |
| `execution-plan.md` v1.0 | Outlook of 6-9 units, critical path identified |

**Terminology for this project.** TAAS is not a microservices system. There is one deployable
artefact — the `tto-testgen-mcp` Python package — plus a separate *generated output* (the Playwright
project, which is a product of the system rather than part of it). So units of work here are
**modules within a single deployable**, not independently deployable services. This matters for
Question 7.

**A tension worth naming before the questions.** Two structures are in play and they do not align.
The **epic structure** follows the pipeline: ingest, analyse, requirements, coverage, cases,
automation, handover. The **architectural structure** follows the hexagon: domain, ports, services,
adapters, platform. A unit drawn along epic lines cuts vertically through every ring; a unit drawn
along ring lines cuts horizontally through every epic. Questions 1, 2 and 4 decide how that is
resolved.

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis. Tell me when done.

## Question 1 — Story Grouping
How should the 55 stories be grouped into units?

A) **By pipeline capability (epic-aligned), with one foundation unit underneath.** A Core Platform
unit carries the schema, MCP server, platform components and the domain primitives everything
depends on; each subsequent unit is a vertical slice — its domain logic, its service, its adapters —
for one pipeline capability. **(Recommended — each unit after the foundation is independently
demonstrable, which is what makes a per-unit gate meaningful)**

B) **By architectural ring** — a domain unit, a ports unit, an adapters unit, a services unit.
Clean layering, but no unit does anything on its own until nearly all are complete, so per-unit
review has nothing to review.

C) **By release** — an R1 unit, an R2 unit, an R3 unit. Matches the delivery sequence exactly, but
produces three units far too large for the per-unit design and code generation loop.

D) **By persona** — units serving the Test Analyst, the Automation Engineer, the Test Lead.
Sharpens who reviews what, but scatters shared machinery across all three.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 2 — Business Domain
The domain core (D1-D8) holds the rules that make the corpus trustworthy: traceability enforcement,
de-duplication, coverage derivation, identifier allocation, integrity validation. Where should it
live?

A) **Distributed into the capability units that use it** — D2 with Coverage, D4 and D5 with Test
Cases, D3 with Traceability. Each unit owns its own domain logic end to end.

B) **Concentrated in the Core Platform unit** as a single domain kernel that every other unit
depends on. One place holds every invariant, and the property-based suite has one home.
**(Recommended — D3 is written by two services and D7 duplicates rules that also exist as database
constraints; splitting either across units is how the same rule ends up with two implementations
that drift)**

C) **Split by stability** — the invariant-bearing components (D3, D5, D7) in Core Platform; the
policy-bearing components (D2, D4, D6, D8) in their capability units, since their rules are
expected to be tuned.

X) Other (please describe after [Answer]: tag below)

[Answer]: B  (accepted recommendation)

## Question 3 — Unit Sizing
How large should units be?

A) **Capability-sized: 6-9 units, roughly 5-10 stories each.** Each unit is a coherent, reviewable
increment. **(Recommended — matches the execution plan outlook and keeps the per-unit CONSTRUCTION
loop, which runs four stages and four gates per unit, at a sensible total)**

B) **Fine-grained: 12-15 units, 3-5 stories each.** Tighter review, but 48-60 CONSTRUCTION stage
executions and as many approval gates.

C) **Coarse: 3-4 units, 14-18 stories each.** Fewest gates, but each unit becomes too large to hold
in one design conversation.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 4 — Walking Skeleton
R1 is a thin end-to-end slice touching almost every epic. How should it relate to the units?

A) **R1 is a slice through units, not a unit.** Each unit is built to its R1 depth first, in
dependency order, then revisited for R2. Preserves the walking-skeleton benefit — every seam
exercised early — but each unit is visited more than once. **(Recommended — the whole value of a
walking skeleton is finding architectural mistakes while they are cheap, and a separate skeleton
unit that is later discarded loses that)**

B) **R1 becomes its own unit** — a thin end-to-end implementation built first, with later units
thickening it. Clean sequencing, but the skeleton unit and the units that supersede it overlap
heavily.

C) **Ignore releases in unit definition.** Units are built completely, in dependency order. Simple,
but nothing works end to end until the last unit lands, which is exactly the risk R1 exists to
retire.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 5 — Dependencies
How should units integrate while others are still incomplete?

A) **Contract-first with in-memory fakes.** Ports are defined in Core Platform; every unit codes
against protocols and tests against in-memory fakes, so no unit waits on another's adapter.
**(Recommended — the hexagonal design already makes this nearly free, and it is what allows the
non-critical-path units to genuinely proceed in parallel)**

B) **Strict dependency order** — a unit starts only when everything it depends on is complete.
Simple to manage, no parallelism.

C) **Stub adapters** — each unit ships throwaway stubs for its dependencies, replaced later.
Similar to A but with duplicated stub effort and no shared contract.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 6 — Team Alignment
How many people or parallel streams will build this? This determines whether parallelism in the
decomposition is worth designing for at all.

A) **One developer, sequential.** Units are a review and planning device, not a parallelism device;
optimise the decomposition for reviewability and order.

B) **Two to three developers working in parallel** where dependencies allow.

C) **A larger team, four or more**, needing maximum parallelism and clear ownership boundaries.

D) **Unknown at this stage** — design the decomposition so it works sequentially but does not
obstruct parallelism if more people join.

X) Other (please describe after [Answer]: tag below)

[Answer]: D  (ASSUMED - no recommendation was offered; team size not stated. Decomposition designed to work sequentially without obstructing parallelism. Tell me if the team is 1 person or 4+ and I will revisit Q3 and Q5.)

## Question 7 — Code Organization
TAAS is one deployable Python package plus a separate generated output. How should the repository be
organised?

A) **Single installable Python package, units as internal modules**, with the Jinja2 templates and a
`generated/` output directory alongside. One `pyproject.toml`, one lockfile, one version.
**(Recommended — there is one MCP server process; splitting it into separately versioned packages
would add release coordination with nothing to gain)**

B) **Monorepo with multiple installable packages** — `tto-testgen-core`, `tto-testgen-adapters`,
`tto-testgen-mcp` — each independently versioned.

C) **Separate repositories per unit.** Maximum isolation, at a coordination cost that a
single-process tool does not justify.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 8 — Technical Considerations
The Playwright emitter (A7) and its Jinja2 templates are the one part of the system whose output is
TypeScript, whose reviewer is the Automation Engineer rather than the Test Analyst, and whose
correctness criterion is byte-identical reproducibility. Should it be its own unit?

A) **Yes — a dedicated Automation Emission unit.** Different output language, different reviewer,
different correctness criterion, and the templates are where the generated coding standard lives.
**(Recommended — it is the only part of the system with a genuinely different audience and a
different definition of correct)**

B) **No — fold it into a combined Automation and Handover unit** with S6 and S7, since they are
consumed together.

C) **No — fold the emitter into whichever unit produces the cases it renders**, keeping generation
and emission adjacent.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

# Execution Checklist

Executed in Part 2, after this plan is approved. Each item marked `[x]` in the interaction that
completes it.

## Phase 1: Unit Definition

- [x] 1.1 Apply the grouping strategy from Question 1 to derive candidate units
- [x] 1.2 Place the domain core per the Question 2 answer
- [x] 1.3 Adjust unit sizing to the Question 3 target
- [x] 1.4 Apply the Question 8 decision on the automation emitter
- [x] 1.5 Name each unit and state its responsibility and boundary
- [x] 1.6 Assign components (D, P, S, A, X, M) to units with no component in two units
- [x] 1.7 Record the release depth expectation per unit per the Question 4 answer

## Phase 2: Dependencies

- [x] 2.1 Build the unit dependency matrix
- [x] 2.2 Verify the dependency graph is acyclic
- [x] 2.3 Identify the critical path
- [x] 2.4 Identify units that can proceed in parallel
- [x] 2.5 Define the integration approach per the Question 5 answer
- [x] 2.6 Define the contract surface each unit exposes to the others
- [x] 2.7 Write `aidlc-docs/inception/application-design/unit-of-work-dependency.md`

## Phase 3: Story Mapping

- [x] 3.1 Assign every one of the 55 stories to exactly one unit
- [x] 3.2 Verify no story is unassigned and none is assigned twice
- [x] 3.3 Verify each unit's stories form a coherent capability
- [x] 3.4 Map the release sequencing across units
- [x] 3.5 Write `aidlc-docs/inception/application-design/unit-of-work-story-map.md`

## Phase 4: Code Organization (Greenfield)

- [x] 4.1 Define the repository layout per the Question 7 answer
- [x] 4.2 Define the directory structure mapping units to modules
- [x] 4.3 Define the packaging, dependency and lockfile strategy
- [x] 4.4 Define where generated output is written and how it is excluded from version control
- [x] 4.5 Confirm application code sits at the workspace root and never under `aidlc-docs/`

## Phase 5: Validation and Assembly

- [x] 5.1 Verify all 37 components are assigned to exactly one unit
- [x] 5.2 Verify all 135 requirements are reachable through the unit set
- [x] 5.3 Verify unit boundaries do not split a single transaction across units
- [x] 5.4 Verify each unit is independently testable
- [x] 5.5 Write `aidlc-docs/inception/application-design/unit-of-work.md` including the code organization strategy
- [x] 5.6 Validate all content per `common/content-validation.md`
- [x] 5.7 Update `aidlc-docs/aidlc-state.md` and log in `aidlc-docs/audit.md`

---

# Mandatory Artifacts

Produced regardless of the answers above:

- [x] `unit-of-work.md` — unit definitions, responsibilities, and the code organization strategy
- [x] `unit-of-work-dependency.md` — dependency matrix
- [x] `unit-of-work-story-map.md` — stories mapped to units
- [x] Unit boundaries and dependencies validated
- [x] All 55 stories assigned to units
