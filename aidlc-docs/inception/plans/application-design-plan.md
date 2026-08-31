# Application Design Plan

**Project**: TTO Test Analyst Agent System (TAAS)
**Stage**: INCEPTION - Application Design
**Created**: 2026-08-28T10:11:00Z
**Status**: APPROVED 2026-08-28T10:20:00Z - all recommendations accepted by user

---

## Purpose

This plan defines *how* the application design will be produced — component boundaries, method
signatures, the service layer, and dependencies. It does not contain the design itself; that is
generated after this plan is answered and approved.

---

## Context

From `requirements.md` v1.0 and `stories.md` v1.0:

- **Toolchain**: Python 3.11+, exposed as the local MCP server `tto-testgen-mcp` (C-10)
- **Module separation is mandated** by NFR-MNT-01: ingestion, analysis storage, coverage,
  generation, traceability, emission, reporting
- **18 data entities** with integrity rules enforced as database constraints (§10.2, §10.3)
- **Three external read-only MCP servers** plus Playwright MCP
- **The agent reasons; the toolchain guarantees** — this split is the architecture's organising idea
- **55 stories across 13 epics**, with a likely 6-9 units of work

The most consequential decision in this stage is the **shape of the MCP tool surface**. It is the
contract between the reasoning layer and the deterministic layer. Once instructions, chat modes and
prompt files are written against it, changing it is expensive. Questions 2, 5 and 7 address it from
three directions.

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis. Tell me when done.

## Question 1
How should the Python toolchain's internal components be organised?

A) **Hexagonal (ports and adapters)** — a pure domain core (coverage model, traceability graph,
de-duplication, identifier allocation) with adapters at the edges for SQLite, the MCP servers, and
file emission. The domain never imports an adapter. **(Recommended — the domain logic is exactly
what the property-based tests target under PBT partial mode, and this keeps it testable without a
database or a network)**

B) **Layered** — presentation (MCP tools), service, domain, persistence, in strict downward
dependency order. Familiar, but tends to leak SQL concerns upward as queries get complex.

C) **Vertical slices per pipeline stage** — each of the seven stages owns its full stack from tool
to storage. Good isolation between stages, at the cost of duplicating persistence and traceability
logic seven times.

D) **Flat modules** matching NFR-MNT-01 exactly — ingestion, storage, coverage, generation,
traceability, emission, reporting — with no further architectural layering.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 2
What granularity should the `tto-testgen-mcp` tool surface have?

A) **Fine-grained entity operations** — `testcase_upsert`, `trace_link_add`, `coverage_item_add`,
`unit_state_set`, and so on. The agent composes them. Maximum flexibility, but the agent must
sequence many calls correctly for every test case, and a dropped call is a silent inconsistency.

B) **Coarse-grained stage operations** — `ingest_resources`, `build_coverage_model`,
`generate_cases_for_feature`, `emit_automation_for_feature`. One call per unit of work. Simple for
the agent, but it pushes reasoning into the toolchain, which is exactly what the toolchain cannot do.

C) **Two tiers: coarse orchestration tools that own transactions and invariants, plus fine-grained
read and query tools.** The agent calls one write tool per unit with a structured payload it has
reasoned out; the toolchain validates, allocates identifiers, enforces constraints, de-duplicates
and commits atomically. Reads stay granular so the agent can look things up freely.
**(Recommended — writes are where invariants live and where partial failure hurts, so they belong in one transactional call; reads are cheap and benefit from flexibility)**

D) **Fine-grained writes plus an explicit transaction tool** — `begin`, operations, `commit`.
Flexible and atomic, but it makes the agent responsible for transaction discipline across a
context window, which is a poor place to put it.

X) Other (please describe after [Answer]: tag below)

[Answer]: C  (accepted recommendation)

## Question 3
Who calls the external MCP servers for bulk ingestion — the agent, or the toolchain?

Note the practical stake: at 100-500 Jira stories, having the agent fetch each issue and forward
its content to the toolchain means every issue body passes through the model's context window.
That is slow, consumes Copilot request budget, and adds a transcription step between source and
storage that can lose fidelity.

A) **The toolchain acts as an MCP client** for Atlassian and Bitbucket, so `ingest_jira(query)`
fetches, normalises, hashes and stores without the model in the loop. The agent still calls
Playwright MCP directly, since UI exploration genuinely needs reasoning about what it sees.
**(Recommended — bulk ingestion is deterministic work, and routing it through the model is expensive with no benefit; it also makes content-hash caching and idempotent re-ingest straightforward)**

B) **The agent calls all external MCP servers** and passes results to the toolchain for storage.
Keeps the toolchain free of credentials and network concerns, at significant cost in throughput.

C) **Hybrid by volume** — the toolchain fetches in bulk; the agent fetches individual items when it
needs to inspect something specific during analysis.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 4
How should the toolchain access SQLite?

A) **A repository layer over `sqlite3` with parameterised SQL in dedicated query modules.** No ORM.
Direct control over the indexed queries the performance budget needs (NFR-PRF-01, NFR-PRF-03), and
the schema constraints stay visible in plain DDL. **(Recommended — the integrity rules are the
architecture here, and an ORM would obscure them)**

B) **SQLAlchemy Core** — parameterisation and composability without full ORM mapping.

C) **SQLAlchemy ORM** — entity mapping and session management, at the cost of distance from the
constraints and less predictable query plans.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 5
Where does orchestration live — the service layer, or the agent?

A) **Services orchestrate within a unit of work; the agent orchestrates between units.** A single
tool call runs a complete, transactional unit-of-work operation. The agent decides which unit and
which stage, per constraint C-12. **(Recommended — it puts sequencing that must be correct inside code, and sequencing that requires judgement with the operator and the agent)**

B) **The agent orchestrates everything**, calling granular tools in sequence. Maximum transparency
into each step, but multi-step invariants become the agent's responsibility.

C) **Services orchestrate whole pipeline stages** across many units. Fewest agent decisions, but it
conflicts with C-12, which reserves scope selection to the operator.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 6
How should Playwright TypeScript code be produced?

FR-AUT-11 requires that regeneration with unchanged inputs produce byte-for-byte identical output.
That requirement is the deciding factor: a language model cannot guarantee it.

A) **Deterministic template rendering (Jinja2) from the stored case and UI models.** The agent
supplies structured data; templates produce the code. Reproducible by construction, and the coding
standard lives in one reviewable place. **(Recommended — it is the only option that satisfies FR-AUT-11 without qualification)**

B) **The agent writes the TypeScript**, and the toolchain validates it against the standards. More
adaptable to unusual cases, but regeneration is not reproducible and review has no fixed baseline.

C) **Templates for structure, agent-authored fragments for complex assertions**, with the fragments
stored so regeneration reuses them rather than re-deriving them.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 7
How should the toolchain report failure to the agent?

A) **Structured result objects** — every tool returns a typed result carrying success or failure, a
machine-readable code, a human-readable message, and remediation guidance. Exceptions never cross
the MCP boundary. **(Recommended — a rejection is a normal, expected event here, since the whole design refuses invalid work; the agent needs to distinguish "you must fix this" from "the system broke")**

B) **Exceptions surfaced as MCP errors** — conventional, but it conflates a rejected test case with
a database failure, and the agent should respond differently to each.

C) **Success returns data, failure raises** — the common Python idiom, with the same conflation
problem at the agent boundary.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

# Execution Checklist

Executed after this plan is approved. Each item marked `[x]` in the interaction that completes it.

## Phase 1: Component Identification

- [x] 1.1 Derive the component set from the 13 epics, the 7 NFR-MNT-01 modules, and the answers above
- [x] 1.2 Define each component's purpose and responsibilities
- [x] 1.3 Define each component's interface at the boundary
- [x] 1.4 Verify every one of the 88 functional requirements maps to at least one component
- [x] 1.5 Verify no component carries responsibilities from more than one architectural concern
- [x] 1.6 Write `aidlc-docs/inception/application-design/components.md`

## Phase 2: Component Methods

- [x] 2.1 Define method signatures per component with input and output types
- [x] 2.2 State each method's high-level purpose (detailed business rules deferred to Functional Design)
- [x] 2.3 Define the shared result and error types
- [x] 2.4 Define the MCP tool surface at the granularity chosen in Question 2
- [x] 2.5 Map each MCP tool to the components it invokes
- [x] 2.6 Write `aidlc-docs/inception/application-design/component-methods.md`

## Phase 3: Service Layer

- [x] 3.1 Define services and their orchestration responsibilities per the Question 5 answer
- [x] 3.2 Define the transaction boundary for each service operation
- [x] 3.3 Define how each pipeline stage maps to service operations
- [x] 3.4 Define the human gate enforcement point in the service layer (FR-BAT-07)
- [x] 3.5 Write `aidlc-docs/inception/application-design/services.md`

## Phase 4: Dependencies

- [x] 4.1 Build the component dependency matrix
- [x] 4.2 Define communication patterns between components
- [x] 4.3 Produce data flow diagrams for the seven pipeline stages
- [x] 4.4 Verify the dependency graph is acyclic
- [x] 4.5 Identify which components each external MCP server touches
- [x] 4.6 Write `aidlc-docs/inception/application-design/component-dependency.md`

## Phase 5: Consolidation and Validation

- [x] 5.1 Verify design completeness against all 88 functional requirements
- [x] 5.2 Verify the 47 non-functional requirements have a design home
- [x] 5.3 Verify each of the 18 data entities has an owning component
- [x] 5.4 Verify Security Baseline applicability at design level and record compliance
- [x] 5.5 Verify Resiliency Baseline applicability at design level and record compliance
- [x] 5.6 Identify the pure-domain surface the property-based tests will target (PBT partial mode)
- [x] 5.7 Write consolidated `aidlc-docs/inception/application-design/application-design.md`
- [x] 5.8 Validate all content per `common/content-validation.md`
- [x] 5.9 Update `aidlc-docs/aidlc-state.md` and log in `aidlc-docs/audit.md`

---

# Mandatory Artifacts

Produced regardless of the answers above:

- [x] `components.md` — component definitions and high-level responsibilities
- [x] `component-methods.md` — method signatures with input and output types
- [x] `services.md` — service definitions and orchestration patterns
- [x] `component-dependency.md` — dependency relationships and communication patterns
- [x] `application-design.md` — consolidated design document
- [x] Design completeness and consistency validated
