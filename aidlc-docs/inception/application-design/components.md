# Components

**Project**: TTO Test Analyst Agent System (TAAS)
**Stage**: INCEPTION - Application Design
**Architecture**: Hexagonal (ports and adapters)
**Version**: 1.0
**Date**: 2026-08-28

---

## Architectural Principle

The domain core holds every rule that must stay true — coverage derivation, traceability
resolution, similarity comparison, identifier allocation, integrity validation. It performs no I/O
and imports no adapter. Everything outside it exists to feed it or to carry its output somewhere.

This is not architectural decoration. Property-based testing is enabled in partial mode
(PBT-02, PBT-03, PBT-07, PBT-08, PBT-09), and its targets are exactly the round-trips and
invariants that live in the domain core. Keeping that core free of database and network dependencies
is what makes those properties testable at all.

```
                    +-----------------------------+
                    |      MCP TOOL SURFACE       |
                    |   write tier | read tier    |
                    +-----------------------------+
                                  |
                                  v
                    +-----------------------------+
                    |    APPLICATION SERVICES     |
                    |  orchestrate one unit of    |
                    |  work, own the transaction  |
                    +-----------------------------+
                          |                 |
                          v                 v
              +-------------------+   +-------------------+
              |    DOMAIN CORE    |   |       PORTS       |
              |  pure, no I/O,    |<--|  protocols only   |
              |  no dependencies  |   |                   |
              +-------------------+   +-------------------+
                                              ^
                                              |
                    +-----------------------------------------+
                    |               ADAPTERS                  |
                    |  SQLite | MCP clients | filesystem |    |
                    |  Jinja2 emitters | report writers       |
                    +-----------------------------------------+
```

**Dependency rule**: arrows point inward. Adapters depend on ports; services depend on domain and
ports; the domain depends on nothing.

---

## Component Inventory

| Ring | Count | Components |
|---|---|---|
| Domain Core | 8 | D1-D8 |
| Ports | 3 | P1-P3 |
| Application Services | 10 | S1-S10 |
| Adapters | 9 | A1-A9 |
| Platform | 5 | X1-X5 |
| MCP Surface | 2 | M1-M2 |
| **Total** | **37** | |

---

# Domain Core

Pure logic. No database, no network, no filesystem. Every component here is directly unit-testable
and is where the property-based tests point.

---

### D1: DomainModel

**Purpose**: the entity types the whole system speaks in.

**Responsibilities**
- Define the 18 entities from `requirements.md` §10.2 as immutable typed records
- Define value objects: `TestCaseId`, `JiraKey`, `LinkType`, `TestType`, `CoverageDepth`,
  `AutomatabilityClass`, `UnitState`, `ChangeClassification`
- Enforce construction-time invariants that do not require external context — a `TestCase` cannot be
  constructed with an empty step list; a `TraceLink` cannot be constructed without a typed target
- Provide serialisation to and from plain dictionaries

**Interface**: constructors, validators, `to_dict()` / `from_dict()`

**Requirements**: §10.2, §10.3, FR-TCG-01, FR-TCG-02
**PBT target**: round-trip properties (PBT-02) — `from_dict(to_dict(x)) == x` for every entity

---

### D2: CoverageModeller

**Purpose**: decide what must be tested, to what depth, and why.

**Responsibilities**
- Derive required test types per testable requirement with a stated rationale
- Apply equivalence partitioning, boundary value analysis, decision tables and state transition
  coverage to determine depth
- Apply documented reduction when combinatorial expansion would be unreasonable, recording the
  technique used
- Compute the expected yield per feature, per test type, and in total
- Identify requirements with no planned coverage

**Interface**: `derive_coverage(requirements, rules) -> CoverageModel`,
`compute_yield(model) -> YieldForecast`, `find_uncovered(model, requirements) -> list[Gap]`

**Requirements**: FR-COV-01 to FR-COV-05, FR-COV-07
**PBT target**: invariant (PBT-03) — total yield equals the sum of per-feature yields, for all models

---

### D3: TraceabilityResolver

**Purpose**: enforce and construct the traceability that keeps the corpus honest.

**Responsibilities**
- Validate that a candidate entity carries at least one link resolving to a Jira key
- Resolve a Jira key from commit history when no direct story link exists, recording
  `derived-from-commit` as the link type
- Classify link types: `direct-story`, `derived-from-commit`, `confluence`, `code-symbol`,
  `screenshot`
- Build the bidirectional matrix — requirement to case to automated test, and the reverse
- Route behaviour with no derivable key to the gap set

**Interface**: `require_jira_key(entity, links) -> Result`,
`derive_key_from_commits(file_path, commit_records) -> Optional[DerivedLink]`,
`build_matrix(links) -> TraceMatrix`

**Requirements**: FR-TRC-01 to FR-TRC-06, FR-TRQ-04
**PBT target**: invariant (PBT-03) — the matrix is bidirectionally consistent; every forward edge
has a corresponding reverse edge

---

### D4: SimilarityAnalyzer

**Purpose**: detect duplicate and near-duplicate test cases deterministically.

**Responsibilities**
- Normalise a case to a comparable form: lowercased, whitespace-collapsed, ordered steps and
  expected results, test data excluded
- Compute a similarity score between two normalised cases
- Apply the configured threshold to classify identical, near-duplicate, or distinct
- Treat differing equivalence class as a material difference even when steps are similar

**Interface**: `normalise(case) -> NormalisedCase`, `similarity(a, b) -> float`,
`classify(a, b, threshold) -> DuplicateVerdict`

**Requirements**: FR-TCG-05
**PBT target**: invariants (PBT-03) — reflexive (`similarity(a, a) == 1.0`), symmetric
(`similarity(a, b) == similarity(b, a)`), and bounded to `[0, 1]` for all generated cases

---

### D5: IdentifierAllocator

**Purpose**: allocate stable, unique identifiers the model never supplies.

**Responsibilities**
- Allocate test case, requirement, coverage item and automated test identifiers from a monotonic
  sequence scoped to its entity kind
- Guarantee identifiers are stable across regeneration when the underlying entity persists
- Encode and decode identifiers to and from their string form

**Interface**: `allocate(kind, sequence_state) -> (Id, sequence_state)`, `encode(id) -> str`,
`decode(s) -> Id`

**Requirements**: FR-TCG-04
**PBT target**: round-trip (PBT-02) — `decode(encode(id)) == id`; invariant (PBT-03) — allocation is
strictly monotonic and never repeats a value

---

### D6: Classifier

**Purpose**: rate risk and decide automatability, with reasons rather than verdicts alone.

**Responsibilities**
- Rate requirement risk from business criticality, complexity, integration surface and change
  frequency, recording each contributing factor
- Record a factor as unavailable rather than defaulting it to zero when its input is missing
- Classify a case automatable, manual-only, or needs-review with a stated basis
- Accept and record human overrides

**Interface**: `rate_risk(requirement, signals) -> RiskRating`,
`classify_automatability(case, ui_model, api_model) -> AutomatabilityVerdict`

**Requirements**: FR-TRQ-03, FR-TCG-06

---

### D7: IntegrityValidator

**Purpose**: the last gate before anything enters the corpus.

**Responsibilities**
- Reject a test case with no steps, or with steps lacking expected results
- Reject a test case with no Jira key link, or linked to a key absent from the ingested set
- Reject a test case whose identifier was supplied rather than allocated
- Validate coverage model internal consistency
- Produce a structured rejection carrying a machine-readable code and remediation guidance

**Interface**: `validate_case(case, links, known_keys) -> Result`,
`validate_coverage(model) -> Result`

**Requirements**: FR-TCG-02, FR-TRC-01, §10.3

**Note**: this component is the second line of defence, not the first. The same rules exist as
SQLite constraints (A1). The validator produces a good error message; the constraint makes the rule
unbreakable even if the validator is bypassed.

---

### D8: ImpactAnalyzer

**Purpose**: turn a detected change into a precise statement of what it affects.

**Responsibilities**
- Map changed files and updated Jira issues to affected features, requirements, cases and tests via
  the traceability graph
- Classify each affected case unchanged, requires-update, or obsolete, with a reason
- Report changes that map to nothing rather than assuming no impact
- Report the scale of impact before any regeneration is proposed

**Interface**: `map_impact(changes, trace_graph) -> ImpactSet`,
`classify(impact_set) -> list[ClassifiedImpact]`

**Requirements**: FR-DLT-03, FR-DLT-04, FR-DLT-05

---

# Ports

Protocol definitions only — no implementation. These are what the domain and services depend on,
and what adapters satisfy.

---

### P1: RepositoryPorts

**Purpose**: persistence contracts.

**Protocols**: `ArtefactRepository`, `FeatureRepository`, `RequirementRepository`,
`CoverageRepository`, `TestCaseRepository`, `TraceRepository`, `AutomationRepository`,
`RunStateRepository`, `ChangeEventRepository`

**Interface shape**: each exposes `get`, `query`, `upsert`, `soft_delete`, and participates in a
caller-supplied transaction. No repository opens its own transaction.

**Requirements**: §10.2, NFR-REL-01

---

### P2: SourcePorts

**Purpose**: external artefact retrieval contracts.

**Protocols**: `JiraSource`, `ConfluenceSource`, `BitbucketSource`, `DesignAssetSource`,
`ResourceManifestSource`

**Interface shape**: read-only retrieval returning normalised records with a content hash. No
protocol declares a write operation, so the read-only posture (C-05, C-06, NFR-SEC-14) is a
structural property rather than a policy anyone has to remember.

**Requirements**: FR-ING-01 to FR-ING-07, C-05, C-06

---

### P3: EmitterPorts

**Purpose**: output contracts.

**Protocols**: `AutomationEmitter`, `ViewEmitter`, `ReportEmitter`

**Interface shape**: each takes domain records and a destination path, returns a manifest of what
was written. Emitters never read from repositories directly.

**Requirements**: FR-AUT-01, FR-TCG-08, FR-RPT-05

---

# Application Services

Each service orchestrates one unit of work, owns its transaction boundary, and returns a structured
result. Services depend on the domain and on ports, never on adapters directly.

---

### S1: IngestionService

**Purpose**: resolve declared resources into stored, hashed, provenance-carrying artefacts.

**Responsibilities**: parse the resource manifest; classify each entry; delegate retrieval to
source ports; skip unchanged content by hash; store with provenance; report unclassified entries
and per-resource failures without aborting the run.

**Requirements**: FR-ING-01 to FR-ING-10, NFR-PRF-04

---

### S2: AnalysisService

**Purpose**: persist the application model the agent reasons out, and the parts the toolchain can
derive.

**Responsibilities**: accept structured feature, journey, business rule and UI model payloads from
the agent; derive the API model from endpoint records and OpenAPI specs deterministically; record
source discrepancies; report artefacts that map to no feature.

**Requirements**: FR-ANA-01 to FR-ANA-08

**Note on the split**: the API model is derived by the toolchain because endpoint extraction is
mechanical. The feature model and UI model arrive from the agent because they require judgement.
This division is the architecture's organising idea applied at method level.

---

### S3: TestableRequirementService

**Purpose**: store atomic testable requirements with classification, risk and traceability.

**Responsibilities**: validate atomicity and non-duplication; invoke D6 for risk rating; enforce
the Jira key rule through D3 before storage; route unresolvable behaviour to the gap set.

**Requirements**: FR-TRQ-01 to FR-TRQ-05

---

### S4: CoverageService

**Purpose**: build, forecast and gate the coverage baseline.

**Responsibilities**: invoke D2 to derive the model; compute and expose the yield forecast; record
approval with approver, timestamp and model version; invalidate approval when the model changes;
enforce that only the Test Lead role may approve; apply and record risk-based reduction.

**Requirements**: FR-COV-01 to FR-COV-07

---

### S5: TestCaseService

**Purpose**: the transactional heart of the system.

**Responsibilities**: accept a batch of agent-reasoned cases for one feature; validate each through
D7; check duplicates through D4; allocate identifiers through D5; classify automatability through
D6; enforce traceability through D3; commit the whole batch atomically or not at all; emit sharded
views.

**Requirements**: FR-TCG-01 to FR-TCG-10

---

### S6: AutomationService

**Purpose**: render automation deterministically from stored cases.

**Responsibilities**: select automatable cases for a feature; bind cases to page objects, fixtures
and API clients; invoke the template emitter; detect hand-edited files and stop rather than
overwrite; refuse to emit for any case lacking a Jira key.

**Requirements**: FR-AUT-01 to FR-AUT-11

---

### S7: HandoverService

**Purpose**: assemble and verify the deliverable project.

**Responsibilities**: assemble the standard Playwright project structure; verify every referenced
page object, fixture and data file exists; verify TypeScript compiles and tests enumerate; produce
the handover manifest; reconcile manifest against filesystem; never push and never write Jenkins
configuration.

**Requirements**: FR-HND-01 to FR-HND-06

---

### S8: ReportingService

**Purpose**: produce every report from queries, never from assembly by hand.

**Responsibilities**: coverage report with derivation; gap report across all five gap categories
with empty categories shown rather than omitted; automation report including at-risk tests;
traceability matrix in Markdown and CSV.

**Requirements**: FR-RPT-01 to FR-RPT-05, FR-COV-05, FR-TRC-05, FR-TRC-06

---

### S9: DeltaService

**Purpose**: keep the baseline true as the application moves.

**Responsibilities**: detect Bitbucket changes against the recorded head commit and Jira changes
against the recorded timestamp; detect a missing recorded head and offer full re-baseline; invoke
D8 for impact; soft-retire obsolete cases with reason and change event; maintain run history.

**Requirements**: FR-DLT-01 to FR-DLT-07

---

### S10: RunStateService

**Purpose**: make a multi-day, multi-session run survivable.

**Responsibilities**: record per-unit per-stage state transactionally; refuse a batch that would
re-run a completed unit without explicit instruction; report status on request without proposing
work; enforce stage gates; record approvals; detect a stale database lock and report it with
recovery guidance.

**Requirements**: FR-BAT-01 to FR-BAT-07

**Note on C-12**: this service reports and enforces. It contains no method that selects the next
unit, because the constraint reserves that to the operator. The absence is deliberate and is the
mechanism by which the constraint holds.

---

# Adapters

---

### A1: SqliteSchemaManager

**Purpose**: own the schema, its constraints, and its evolution.

**Responsibilities**: create the schema with the §10.3 integrity rules expressed as `CHECK`,
`NOT NULL`, `UNIQUE` and foreign key constraints; apply versioned forward and reverse migrations;
back up before any destructive or schema-changing operation; create the indexes the performance
budget depends on.

**Requirements**: §10.2, §10.3, NFR-REL-05, NFR-REL-07, NFR-PRF-01, NFR-PRF-03

---

### A2: SqliteRepositories

**Purpose**: implement the repository ports over `sqlite3`.

**Responsibilities**: parameterised SQL only, held in dedicated query modules; participate in
caller-supplied transactions; map rows to domain records; expose indexed queries for similarity
candidate selection and matrix construction; soft-delete rather than hard-delete.

**Requirements**: NFR-SEC-04, NFR-PRF-01 to NFR-PRF-03, FR-DLT-05

---

### A3: AtlassianSourceAdapter

**Purpose**: act as an MCP client to TTO-Atlassian-MCP.

**Responsibilities**: call `jira_get_issue`, `jira_search_issues`, `confluence_get_page`,
`confluence_search`; page through results without dropping records; normalise to source records
with content hashes; preserve Confluence tables as structured rows; distinguish not-found from
not-authorised; never reference a write tool.

**Requirements**: FR-ING-03, FR-ING-04, C-05, NFR-SEC-14

---

### A4: BitbucketSourceAdapter

**Purpose**: act as an MCP client to TTO-Bitbucket-MCP.

**Responsibilities**: call `bitbucket_repos`, `bitbucket_endpoints`, `bitbucket_file`,
`bitbucket_grep`, `bitbucket_log`, `bitbucket_changes`, `bitbucket_diff`, `bitbucket_tags`; record
branch, head commit, project key and slug; supply commit-to-Jira-key records for D3; supply change
ranges for S9; never reference a write tool.

**Requirements**: FR-ING-05, FR-ING-06, FR-TRC-02, FR-TRC-06, FR-DLT-01, C-06

---

### A5: DesignAssetAdapter

**Purpose**: read the Figma screenshot folder.

**Responsibilities**: parse the `<feature>__<screen>__<state>` filename convention; merge
`screens.manifest.yaml` with precedence to the manifest; hash content for change detection; list
unassociated files rather than guessing or dropping them; use a safe YAML loader.

**Requirements**: FR-ING-07, FR-ING-08, FR-ING-10, NFR-SEC-05

---

### A6: ResourceManifestAdapter

**Purpose**: parse `resources.md`.

**Responsibilities**: extract links and local paths; infer resource type from URL and path patterns;
recognise duplicates; report unclassifiable entries; report a missing manifest as a configuration
error without creating partial state.

**Requirements**: FR-ING-01, FR-ING-02

---

### A7: PlaywrightEmitter

**Purpose**: render the TypeScript project deterministically.

**Responsibilities**: render page objects, spec files, fixtures, API clients, `playwright.config.ts`,
`package.json`, `tsconfig.json`, `.env.example`, `.gitignore` and `README.md` from Jinja2 templates;
guarantee byte-identical output for identical input by sorting all iteration and pinning all
formatting; reject any template output containing a fixed wait or a literal credential; emit tag and
traceability annotations.

**Requirements**: FR-AUT-01 to FR-AUT-09, FR-HND-01 to FR-HND-03

---

### A8: ViewEmitter

**Purpose**: render sharded Markdown and YAML views of the corpus.

**Responsibilities**: one file per feature; deterministic ordering; detect hand-edits by comparing
against the last emitted hash and report before overwriting.

**Requirements**: FR-TCG-08, NFR-USA-02

---

### A9: ReportEmitter

**Purpose**: render reports in Markdown and CSV.

**Responsibilities**: render coverage, gap, automation and traceability reports from query results;
show empty categories explicitly.

**Requirements**: FR-RPT-01 to FR-RPT-04, FR-TRC-05

---

# Platform

Cross-cutting concerns used by every ring.

---

### X1: ResultAndErrors

**Purpose**: the failure vocabulary shared across the MCP boundary.

**Responsibilities**: define `Result[T]` carrying success or failure, a machine-readable error code,
a human-readable message and remediation guidance; define the error code taxonomy separating
*rejected* (the agent must fix its input) from *failed* (the system had a problem); guarantee no
exception crosses the MCP boundary; strip filesystem paths outside the workspace and internal stack
detail from every message.

**Requirements**: NFR-SEC-07, NFR-SEC-08, NFR-USA-03

**Why this matters here**: rejection is a normal event in this system — the design refuses invalid
work by intent. The agent must be able to tell "your test case has no Jira key, add one" from "the
database is unreachable", because the correct response differs completely.

---

### X2: StructuredLogger

**Purpose**: make a long run diagnosable.

**Responsibilities**: emit structured entries with timestamp, correlation identifier, level and
message; propagate the correlation identifier across a unit of work; redact credentials and personal
data; record per-unit metrics.

**Requirements**: NFR-SEC-06, NFR-OBS-01, NFR-OBS-03

---

### X3: ConfigAndSecrets

**Purpose**: keep credentials out of everything.

**Responsibilities**: read configuration from environment variables and the OS credential store;
fail at startup with the variable named when a required value is absent; never write a secret to
logs, the database, or any emitted artefact.

**Requirements**: NFR-SEC-01, FR-AUT-07

---

### X4: ResilienceGateway

**Purpose**: stop one bad unit from taking down a run.

**Responsibilities**: apply bounded retry with backoff to transient external failures; log every
attempt; fail the unit rather than the run when retries are exhausted; isolate per-resource failures
during ingestion so other resources still process.

**Requirements**: NFR-REL-02, NFR-REL-03, NFR-REL-04

---

### X5: HealthCheck

**Purpose**: answer whether the system can work right now.

**Responsibilities**: verify database accessibility and schema version; verify external MCP
reachability; report each independently so a single unreachable server does not read as total
failure.

**Requirements**: NFR-OBS-02

---

# MCP Surface

---

### M1: McpServer

**Purpose**: expose the toolchain to the Copilot agent over stdio.

**Responsibilities**: register tools with typed schemas; validate every input against its schema
before any logic runs; communicate over stdio only, opening no network listener; convert `Result`
objects to tool responses; run the health check at startup.

**Requirements**: C-10, NFR-SEC-02, NFR-SEC-03

---

### M2: ToolRegistry

**Purpose**: define the two-tier tool surface.

**Responsibilities**: register the coarse transactional **write tier**, where one call performs one
complete unit of work and owns its transaction; register the fine-grained **read tier**, where the
agent queries freely at low cost; ensure no write tool can partially apply.

**Requirements**: FR-AGT-05, and the Q2 two-tier decision

**Why two tiers**: writes carry the invariants and are where partial failure does real damage, so
they belong in a single transactional call. Reads carry no invariants and benefit from flexibility,
so they stay granular. The asymmetry is the point.

---

## Requirement Coverage

Every functional requirement maps to at least one component. Verified in
[application-design.md](application-design.md) §7.

| Requirement group | Owning components |
|---|---|
| FR-AGT | M1, M2 (plus agent-layer configuration, which is not toolchain code) |
| FR-ING | S1, A3, A4, A5, A6 |
| FR-ANA | S2, A4 |
| FR-TRQ | S3, D6, D3 |
| FR-COV | S4, D2 |
| FR-TCG | S5, D1, D4, D5, D6, D7, A8 |
| FR-AUT | S6, A7 |
| FR-HND | S7, A7 |
| FR-TRC | D3, S3, S5, S8 |
| FR-BAT | S10 |
| FR-DLT | S9, D8, A4 |
| FR-RPT | S8, A9 |
