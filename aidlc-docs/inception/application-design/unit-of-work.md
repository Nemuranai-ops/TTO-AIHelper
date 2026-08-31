# Units of Work

**Project**: TTO Test Analyst Agent System (TAAS)
**Stage**: INCEPTION - Units Generation
**Version**: 1.0
**Date**: 2026-08-28

---

## Decomposition Approach

Pipeline-capability grouping with one foundation unit underneath. **8 units**, 55 stories, all 37
components assigned exactly once.

**Terminology**: TAAS is a single deployable Python package. These units are **modules within one
deployable**, not independently deployable services. The generated Playwright project is an *output*
of the system, not a unit of it.

### Decisions applied

| Decision | Choice | Effect on this decomposition |
|---|---|---|
| Q1 Grouping | Pipeline-capability with a foundation unit | U1 is the foundation; U2-U8 are vertical slices |
| Q2 Domain core | Concentrated in Core Platform | All of D1-D8 lives in U1 |
| Q3 Sizing | Capability-sized, 6-9 units | 8 units, 3-10 stories each |
| Q4 Walking skeleton | A slice through units, not a unit | Each unit carries a release depth; R1 depth is built across units first |
| Q5 Dependencies | Contract-first with in-memory fakes | Ports defined in U1; no unit waits on another's adapter |
| Q6 Team | **Assumed** — sequential-capable, parallelism-friendly | See AS-01 below |
| Q7 Code organization | Single installable package | One `pyproject.toml`, one lockfile, one version |
| Q8 Automation emitter | Its own unit | U5 is separate from U4 and U6 |

### AS-01: Team size assumption

**Question 6 was not answered.** Option D was taken: the decomposition is designed to work
sequentially, while not obstructing parallelism if more people join. This is safe under any team
size, so proceeding under it cannot invalidate the work.

**If the team is one person**, unit boundaries function purely as a review and sequencing device,
and the parallelism identified in `unit-of-work-dependency.md` is informational only. **If the team
is four or more**, unit sizing (Q3) and the integration approach (Q5) are worth revisiting — 8 units
gives at most 2-3 genuinely parallel streams, which would leave a larger team contending.

---

## Unit Summary

| Unit | Name | Stories | Components | Depends on | Release depth |
|---|---|---|---|---|---|
| **U1** | Core Platform | 7 | 20 | — | R1 then R2 |
| **U2** | Ingestion and Analysis | 8 | 6 | U1 | R1 then R2 |
| **U3** | Requirements and Coverage | 10 | 2 | U1, U2 | R1 then R2, R3 |
| **U4** | Test Case Generation | 7 | 2 | U1, U3 | R1 then R2 |
| **U5** | Automation Emission | 6 | 2 | U1, U4 | R1 then R2 |
| **U6** | Handover | 3 | 1 | U1, U5 | R1 then R2 |
| **U7** | Orchestration and Agent Layer | 8 | 1 + config | U1 | R1 then R2 |
| **U8** | Reporting and Re-baselining | 6 | 3 | U1, U2, U4 | R2 then R3 |
| | **Total** | **55** | **37** | | |

---

# Unit Definitions

## U1: Core Platform

**Responsibility**: everything every other unit stands on — the domain kernel, the port protocols,
the SQLite schema and repositories, the platform services, and the MCP server.

**Boundary**: U1 contains no pipeline logic. It knows what a test case *is* and what makes one
valid; it does not know how one is produced.

**Components** (20)

| Ring | Components |
|---|---|
| Domain | D1 DomainModel, D2 CoverageModeller, D3 TraceabilityResolver, D4 SimilarityAnalyzer, D5 IdentifierAllocator, D6 Classifier, D7 IntegrityValidator, D8 ImpactAnalyzer |
| Ports | P1 RepositoryPorts, P2 SourcePorts, P3 EmitterPorts |
| Adapters | A1 SqliteSchemaManager, A2 SqliteRepositories |
| Platform | X1 ResultAndErrors, X2 StructuredLogger, X3 ConfigAndSecrets, X4 ResilienceGateway, X5 HealthCheck |
| MCP | M1 McpServer, M2 ToolRegistry |

**Stories** (7): US-ENB-01, US-ENB-02, US-ENB-03, US-ENB-04, US-ENB-05, US-ENB-06, US-TRC-01

**Why the whole domain kernel sits here**: D3 is written by two services and D7 duplicates rules
that also exist as database constraints. Splitting either across units is the reliable way to end up
with one rule and two implementations that drift. US-TRC-01 belongs here for the same reason — the
Jira key rule is enforced as a SQLite constraint in A1 and as validation in D3 and D7, and all three
must move together.

**Release depth**: R1 — schema, MCP server, observability, secrets, the domain kernel.
R2 — scale and performance work, the property-based suite.

**Independently testable**: yes, and more easily than any other unit. The domain is I/O-free and the
adapters run against a temporary SQLite file.

---

## U2: Ingestion and Analysis

**Responsibility**: turn declared resources into stored artefacts, and artefacts into the
application model.

**Boundary**: U2 owns everything that reads from outside the workspace. No other unit touches an
external MCP server.

**Components** (6): S1 IngestionService, S2 AnalysisService, A3 AtlassianSourceAdapter,
A4 BitbucketSourceAdapter, A5 DesignAssetAdapter, A6 ResourceManifestAdapter

**Stories** (8): US-ING-01, US-ING-02, US-ING-03, US-ING-04, US-ANA-01, US-ANA-02, US-ANA-03,
US-ANA-04

**Why ingestion and analysis are one unit**: they are consecutive pipeline stages with a single
handoff, they share A4, and analysis has no value without ingestion having run. Separating them
would create a unit whose only consumer is the next unit.

**Release depth**: R1 — `resources.md`, Jira ingest, Bitbucket repos and endpoints, feature model,
business rules, API model. R2 — Confluence, Figma screenshots, journeys, UI model with live
Playwright selector derivation, discrepancy recording.

---

## U3: Requirements and Coverage

**Responsibility**: atomic testable requirements, and the coverage baseline that gates everything
downstream.

**Boundary**: U3 decides *what must be tested*. It never produces a test case.

**Components** (2): S3 TestableRequirementService, S4 CoverageService

**Stories** (10): US-TRQ-01, US-TRQ-02, US-TRQ-03, US-COV-01, US-COV-02, US-COV-03, US-COV-04,
US-COV-05, US-TRC-02, US-TRC-03

**Why this is the largest unit**: the coverage baseline is where the system's most consequential
decision is made, and its approval gate is the only one restricted to a single role. The
commit-derived traceability stories (US-TRC-02, US-TRC-03) sit here because derivation happens when
a requirement is created, and routing to the gap set is a requirements-stage outcome.

**Release depth**: R1 — atomic requirements, coverage model, Test Lead approval gate.
R2 — risk rating, edge cases, depth from test design techniques, yield forecast, commit-derived
keys, gap routing. R3 — risk-based reduction.

---

## U4: Test Case Generation

**Responsibility**: the transactional heart. Every rule that makes the corpus trustworthy runs here,
in one call.

**Boundary**: U4 produces cases and views. It does not produce automation.

**Components** (2): S5 TestCaseService, A8 ViewEmitter

**Stories** (7): US-TCG-01, US-TCG-02, US-TCG-03, US-TCG-04, US-TCG-05, US-TCG-06, US-TRC-04

**Note on component count**: two components, seven stories, and the highest logical density in the
system. S5 orchestrates six domain components in a single transaction. Component count is a poor
proxy for unit size here.

**Release depth**: R1 — structured cases with mandatory steps, synthetic test data, identifier
allocation, sharded views and tags. R2 — de-duplication, automatability classification, derived
volume reporting, the traceability matrix.

---

## U5: Automation Emission

**Responsibility**: render automatable cases into TypeScript, deterministically.

**Boundary**: U5 produces code. It does not assemble or verify a project.

**Components** (2): S6 AutomationService, A7 PlaywrightEmitter (with the Jinja2 template set)

**Stories** (6): US-AUT-01, US-AUT-02, US-AUT-03, US-AUT-04, US-AUT-05, US-AUT-06

**Why this is its own unit**: it is the only part of the system whose output is TypeScript, whose
reviewer is the Automation Engineer rather than the Test Analyst, and whose correctness criterion is
byte-identical reproducibility rather than semantic correctness. The templates are also where the
generated coding standard lives, which makes them a review artefact in their own right.

**Release depth**: R1 — project scaffold, page objects, API tests, annotations, config and
reporters. R2 — resilient locators from live exploration, no-fixed-wait enforcement, hand-edit
detection, deterministic regeneration.

---

## U6: Handover

**Responsibility**: assemble the project, verify it, and stop.

**Boundary**: U6 writes to disk and reports. It has no method that pushes, branches, or writes
Jenkins configuration.

**Components** (1): S7 HandoverService

**Stories** (3): US-HND-01, US-HND-02, US-HND-03

**Why it is separate from U5 despite being small**: the failure modes are entirely different. U5
fails when generated code is wrong; U6 fails when the assembled project will not install or compile.
Keeping them apart means the verification gate is real rather than a continuation of code review.

**Release depth**: R1 — assembly. R2 — integrity and compile verification, handover manifest.

---

## U7: Orchestration and Agent Layer

**Responsibility**: make a multi-day run survivable, and give the operator a usable interface.

**Boundary**: U7 owns run state and gates, and the Copilot configuration. It owns no pipeline logic.

**Components** (1 + configuration): S10 RunStateService, plus the Agent Layer artefacts —
`.github/copilot-instructions.md`, `.github/instructions/*.instructions.md`,
`.github/chatmodes/*.chatmode.md`, `.github/prompts/*.prompt.md`, `.vscode/mcp.json`

**Stories** (8): US-BAT-01, US-BAT-02, US-BAT-03, US-BAT-04, US-AGT-01, US-AGT-02, US-AGT-03,
US-AGT-04

**Why run state and the agent layer are one unit**: they are two halves of the same thing. S10
enforces the gates; the chat modes and instructions are how the operator experiences them. Building
either without the other produces something untestable — gates nobody can reach, or an interface
with nothing behind it.

**This unit can start as soon as U1 exists**, which makes it the main parallelism opportunity.

**Release depth**: R1 — operator-named scope, durable transactional state, resume, gates,
repository instructions, chat modes, MCP registration. R2 — path-scoped instructions, prompt files.

---

## U8: Reporting and Re-baselining

**Responsibility**: turn the corpus into defensible reports, and keep it current as the application
moves.

**Boundary**: U8 reads the corpus and detects change. It creates no requirement and no case — a
delta run re-enters the pipeline at U3 for the affected scope.

**Components** (3): S8 ReportingService, S9 DeltaService, A9 ReportEmitter

**Stories** (6): US-RPT-01, US-RPT-02, US-RPT-03, US-DLT-01, US-DLT-02, US-DLT-03

**Why reporting and re-baselining are one unit**: both read the corpus rather than producing it,
both serve the Test Lead primarily, both are entirely R2 and R3, and both depend on the traceability
graph being complete. Neither is large enough alone.

**Release depth**: R2 — coverage, gap and automation reports. R3 — delta detection, impact
classification, soft retirement, run history.

---

# Code Organization Strategy

Greenfield, single installable Python package (Q7 = A).

## Repository Layout

```
<workspace-root>/
  pyproject.toml                  single package definition, pinned dependencies
  uv.lock                         committed lockfile (NFR-SEC-09)
  README.md
  .gitignore                      excludes .taas/ and generated/ (NFR-SEC-12)
  .env.example                    documents every required variable, holds no value

  src/tto_testgen/
    __init__.py
    composition.py                U1  the only module knowing both protocol and implementation
    domain/                       U1  D1-D8, pure, no imports outside stdlib and domain
      model.py  coverage.py  traceability.py  similarity.py
      identity.py  classification.py  validation.py  impact.py
    ports/                        U1  P1-P3, protocol definitions only
      repositories.py  sources.py  emitters.py
    platform/                     U1  X1-X5
      result.py  logging.py  config.py  resilience.py  health.py
    mcp/                          U1  M1, M2
      server.py  tools_write.py  tools_read.py
    adapters/
      sqlite/                     U1  A1, A2
        schema.py  migrations/  repositories.py  queries/
      sources/                    U2  A3, A4, A5, A6
        atlassian.py  bitbucket.py  design_assets.py  manifest.py
      emit/
        views.py                  U4  A8
        playwright.py             U5  A7
        reports.py                U8  A9
    services/
      ingestion.py  analysis.py   U2  S1, S2
      requirements.py  coverage.py  U3  S3, S4
      testcase.py                 U4  S5
      automation.py               U5  S6
      handover.py                 U6  S7
      runstate.py                 U7  S10
      reporting.py  delta.py      U8  S8, S9

  templates/playwright/           U5  Jinja2 templates for the generated project
    page_object.ts.j2  spec.ts.j2  api_client.ts.j2  fixtures.ts.j2
    playwright.config.ts.j2  package.json.j2  tsconfig.json.j2
    env.example.j2  gitignore.j2  README.md.j2

  tests/
    unit/                         example-based, mirrors src structure
    properties/                   Hypothesis, targets domain/ only
    integration/                  adapters against a temp SQLite file and stubbed MCP servers
    fakes/                        in-memory port implementations shared across units (Q5)

  .github/
    copilot-instructions.md       U7
    instructions/                 U7  path-scoped, applyTo globs
    chatmodes/                    U7  one per pipeline stage
    prompts/                      U7  reusable tasks
  .vscode/
    mcp.json                      U7  four MCP servers registered

  resources.md                    operator input: plain link list
  design-assets/                  operator input: Figma screenshots + screens.manifest.yaml

  .taas/                          RUNTIME STATE - gitignored
    taas.db                       SQLite, the system of record
    backups/                      pre-migration and pre-destructive backups
    logs/
  generated/                      OUTPUT - gitignored
    views/                        sharded Markdown and YAML per feature
    playwright-suite/             the handover project the team pushes manually
    reports/

  aidlc-docs/                     DOCUMENTATION ONLY - never application code
```

## Rules

| Rule | Reason |
|---|---|
| Application code at the workspace root, never under `aidlc-docs/` | AI-DLC critical rule |
| One `pyproject.toml`, one lockfile, one version | One process; separate versioning would add release coordination with nothing to gain |
| `.taas/` and `generated/` are gitignored | NFR-SEC-12 — ingested corporate content must not reach version control |
| `tests/fakes/` is shared, not per-unit | Q5 contract-first — one in-memory implementation per port, used by every unit |
| Unit ownership is by directory, not by package | Units are a planning and review device; the deployable is one package |

**Where units map to directories**: each unit owns whole files, never parts of files. The mapping is
annotated inline in the tree above so a developer can see a unit's footprint without a lookup table.

---

# Validation

## Component assignment

All 37 components assigned to exactly one unit. No component appears twice.

| Unit | Components | Count |
|---|---|---|
| U1 | D1-D8, P1-P3, A1, A2, X1-X5, M1, M2 | 20 |
| U2 | S1, S2, A3, A4, A5, A6 | 6 |
| U3 | S3, S4 | 2 |
| U4 | S5, A8 | 2 |
| U5 | S6, A7 | 2 |
| U6 | S7 | 1 |
| U7 | S10 | 1 |
| U8 | S8, S9, A9 | 3 |
| | **Total** | **37** |

## Story assignment

All 55 stories assigned to exactly one unit. Verified in
[unit-of-work-story-map.md](unit-of-work-story-map.md).

## Transaction integrity

No unit boundary splits a transaction. Each transactional operation is owned entirely by one unit:

| Transaction | Unit |
|---|---|
| Per-resource ingestion commit | U2 |
| Feature model upsert | U2 |
| Requirements upsert per feature | U3 |
| Coverage model build and approval | U3 |
| Test case batch upsert | U4 |
| Automation emission per feature | U5 |
| Handover assembly | U6 |
| Unit state transition | U7 |
| Delta retirement | U8 |

**The one cross-unit call** is `S10.is_gate_open()`, called by S4 (U3), S5 (U4), S6 (U5) and S7 (U6)
into U7. It is a read, participates in no transaction, and creates no cycle.

## Independent testability

| Unit | Testable without other units? | How |
|---|---|---|
| U1 | Yes | Domain is I/O-free; adapters run against a temp SQLite file |
| U2 | Yes | Stubbed MCP servers, in-memory repositories from `tests/fakes/` |
| U3 | Yes | In-memory repositories seeded with requirement fixtures |
| U4 | Yes | In-memory repositories, fake emitter |
| U5 | Yes | Fixture cases plus a fake UI model; output compared byte-for-byte |
| U6 | Yes | A pre-built fixture project directory |
| U7 | Yes | In-memory run-state repository |
| U8 | Yes | Seeded corpus, stubbed Bitbucket and Jira adapters |

Every unit is testable in isolation because Q5's contract-first approach puts one shared in-memory
implementation behind every port.

## Requirement reachability

All 135 requirements are reachable through the unit set. The mapping runs
requirement → component (in [application-design.md](application-design.md) §7) →
unit (in the component assignment table above). The five FR-AGT configuration requirements map to
U7's Agent Layer artefacts.
