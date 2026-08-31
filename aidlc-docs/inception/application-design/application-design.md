# Application Design

**Project**: TTO Test Analyst Agent System (TAAS)
**Stage**: INCEPTION - Application Design
**Version**: 1.0
**Date**: 2026-08-28

Consolidated design. Detail lives in [components.md](components.md),
[component-methods.md](component-methods.md), [services.md](services.md) and
[component-dependency.md](component-dependency.md).

---

## 1. Design Decisions

Seven decisions, taken at the Application Design planning gate and recorded here with their
consequences.

| # | Decision | Consequence |
|---|---|---|
| 1 | **Hexagonal architecture** | The domain core is I/O-free, which is what makes the property-based tests possible at all |
| 2 | **Two-tier MCP surface** | Coarse transactional writes own the invariants; fine-grained reads stay cheap and flexible |
| 3 | **Toolchain is the MCP client** for Atlassian and Bitbucket | Hundreds of Jira issue bodies never pass through the model's context; content-hash caching and idempotent re-ingest come free |
| 4 | **Repository over `sqlite3`, no ORM** | The integrity rules stay visible as plain DDL, and the indexed queries the performance budget needs stay under direct control |
| 5 | **Services orchestrate within a unit; the agent orchestrates between units** | Sequencing that must be correct sits in code; sequencing that needs judgement sits with the operator, per C-12 |
| 6 | **Deterministic Jinja2 rendering** for TypeScript | The only way to satisfy FR-AUT-11's byte-identical regeneration requirement |
| 7 | **Structured `Result` objects** | The agent can distinguish "fix your input" from "the system broke", which are different situations demanding different responses |

**The organising idea beneath all seven**: the model reasons about meaning; deterministic code owns
every fact that must stay true across thousands of records. Each decision above places a
responsibility on whichever side is actually good at it.

---

## 2. Two-Part System

TAAS is not one artefact. It is a **Copilot agent layer** (configuration, no executable code) and a
**Python toolchain** (executable, exposed as an MCP server). The agent layer is where reasoning is
shaped; the toolchain is where facts are kept.

### 2.1 Agent Layer

Configuration files in the VS Code workspace. Not covered by the component model in
[components.md](components.md), because they contain no code — but they are design artefacts and
are specified here.

| Artefact | Path | Purpose | Requirements |
|---|---|---|---|
| Repository instructions | `.github/copilot-instructions.md` | Role, pipeline model, traceability rules, output conventions, and the standing rule that all durable state goes through `tto-testgen-mcp` rather than direct file writes | FR-AGT-01, FR-AGT-06, NFR-USA-03 |
| Path-scoped instructions | `.github/instructions/*.instructions.md` | `applyTo` globs so editing generated Playwright code loads automation standards, and editing case views loads case standards | FR-AGT-02 |
| Chat modes | `.github/chatmodes/*.chatmode.md` | One per pipeline stage, each declaring only that stage's permitted tools, so an ingestion session cannot emit automation | FR-AGT-03, NFR-USA-01 |
| Prompt files | `.github/prompts/*.prompt.md` | Recurring tasks: analyse one story, generate cases for one feature, generate a page object, produce a coverage report | FR-AGT-04 |
| MCP registration | `.vscode/mcp.json` | Registers `tto-testgen-mcp`, TTO-Atlassian-MCP, TTO-Bitbucket-MCP, Playwright MCP; credentials from environment or OS credential store, never inline | FR-AGT-05, NFR-SEC-01 |

**Why chat modes carry scoped tool sets.** Constraining available tools per stage is a structural
guard rather than an instruction. A stage cannot do what it has no tool for, which is more reliable
than asking it not to.

### 2.2 Python Toolchain

37 components across six rings — 8 domain, 3 ports, 10 services, 9 adapters, 5 platform, 2 MCP
surface. Detailed in [components.md](components.md).

---

## 3. Module Structure

NFR-MNT-01 mandates separation into ingestion, analysis storage, coverage, generation,
traceability, emission and reporting. The hexagonal rings satisfy this while adding the dependency
direction that makes the domain testable.

```
tto_testgen/
  domain/          D1-D8   pure logic, no imports outside stdlib and domain
    model.py               D1  entities and value objects
    coverage.py           D2  coverage derivation and yield
    traceability.py       D3  Jira key enforcement, link typing, matrix
    similarity.py         D4  normalisation and de-duplication
    identity.py           D5  identifier allocation
    classification.py     D6  risk rating and automatability
    validation.py         D7  integrity validation
    impact.py             D8  delta impact analysis
  ports/           P1-P3   protocol definitions only
  services/        S1-S10  one module per service
  adapters/
    sqlite/               A1, A2  schema, migrations, repositories, query modules
    sources/              A3, A4, A5, A6  MCP clients and filesystem readers
    emit/                 A7, A8, A9  Jinja2 templates, views, reports
  platform/        X1-X5   result types, logging, config, resilience, health
  mcp/             M1, M2  server and two-tier tool registry
  composition.py           the only module that knows both a protocol and its implementation
templates/                 Jinja2 templates for the Playwright project
tests/
  unit/                    example-based
  properties/              Hypothesis, targeting domain/
  integration/             adapters against a real SQLite file and stubbed MCP servers
```

**Requirements**: NFR-MNT-01, NFR-MNT-08

---

## 4. Non-Functional Design Decisions

Where each non-functional requirement lives in the design.

### 4.1 Scale and Performance

| Requirement | Design response |
|---|---|
| NFR-SCL-01 (3-10 repos, 100-500 stories, 30-150 screens) | Per-resource ingestion with X4 isolation; no operation loads all repositories at once |
| NFR-SCL-02, NFR-SCL-03 (thousands of cases, responsive at 10,000) | SQLite with indexes on feature, type, tag, Jira key and normalised-case hash |
| NFR-SCL-04 (never the whole corpus in a context window) | The write tier is scoped to one feature per call; the read tier is filtered by design, with no unbounded list tool |
| NFR-PRF-01 (single-case operation under 200 ms) | Indexed primary and foreign keys; no table scan on any single-entity path |
| NFR-PRF-02 (reports under 30 seconds) | Aggregate SQL in A2 query modules; A9 renders, it does not compute |
| NFR-PRF-03 (indexed de-duplication, not pairwise) | D4 normalisation produces a hash and a bucketing key; A2 selects candidates by index, and only candidates are scored |
| NFR-PRF-04 (cache by content hash) | S1 skips retrieval when the stored hash matches |

**The de-duplication design is the load-bearing one.** Pairwise comparison at 10,000 cases is 50
million comparisons. Bucketing by a normalised key reduces the candidate set to cases that could
plausibly match, which is what keeps the 200 ms budget reachable.

### 4.2 Reliability

| Requirement | Design response |
|---|---|
| NFR-REL-01 (transactional) | Services own transaction boundaries; repositories never open their own |
| NFR-REL-02 (survive external MCP failure) | X4 isolation per resource; failures recorded against the unit |
| NFR-REL-03, NFR-REL-04 (bounded retry, no cascade) | X4 `with_retry` and `isolate`; a unit fails, the run continues |
| NFR-REL-05 (backup before destructive operations) | A1 backs up before every migration and destructive operation |
| NFR-REL-06 (portable export) | S8 exports the full corpus to YAML and CSV, sufficient to reconstruct without the database file |
| NFR-REL-07 (versioned reversible migrations) | A1 holds forward and reverse migrations with a version table |

### 4.3 Security

| Requirement | Design response |
|---|---|
| NFR-SEC-01 (no credentials anywhere) | X3 reads from environment and OS credential store; no component accepts a literal secret |
| NFR-SEC-02 (stdio, no listener) | M1 serves stdio only |
| NFR-SEC-03 (typed validated inputs) | M1 validates against the tool schema before any logic runs |
| NFR-SEC-04 (parameterised queries) | A2 query modules only; string-concatenated SQL is prohibited and checked in review |
| NFR-SEC-05 (safe deserialisation) | A5 and A6 use safe YAML loaders that cannot instantiate arbitrary types |
| NFR-SEC-06 (structured logs, no secrets) | X2 with redaction |
| NFR-SEC-07 (error handling, fail closed) | X1 `Result` everywhere; M1 global handler; no exception crosses the MCP boundary |
| NFR-SEC-08 (safe error messages) | X1 `sanitise` strips paths outside the workspace and internal stack detail |
| NFR-SEC-09 (pinned dependencies, scanning, SBOM) | Lockfiles for both Python and the generated project; scanning documented in build instructions |
| NFR-SEC-10, NFR-SEC-11 (confidentiality, synthetic data) | A7 templates emit behaviour and expectations only, never verbatim internal documentation; D1 test data is synthetic by construction |
| NFR-SEC-12 (exclude database and artefacts from VCS) | A7 emits `.gitignore` covering the database and ingested content |
| NFR-SEC-13 (auditable changes) | A2 records actor, timestamp and change on every case and coverage mutation |
| NFR-SEC-14 (read-only posture) | P2 protocols declare no write operation; A3 and A4 reference no write tool |
| NFR-SEC-15 (encryption at rest) | Relies on organisational full-disk encryption; **OD-04 open** — if not enforced, A1 gains a SQLCipher backend |
| NFR-SEC-16 (encryption in transit) | M1 is stdio with no network; A3 and A4 inherit TLS from the MCP servers they call |

**NFR-SEC-14 is worth singling out.** The read-only posture is not enforced by a rule anyone must
remember. The P2 source protocols contain no write method, so no component can call one. A
constraint expressed as an absent capability cannot be violated by forgetting.

### 4.4 Observability

| Requirement | Design response |
|---|---|
| NFR-OBS-01 (log every tool invocation with correlation) | M1 binds a correlation id per call; X2 propagates it through the unit of work |
| NFR-OBS-02 (health check) | X5, reporting database, schema version and per-server MCP reachability independently |
| NFR-OBS-03 (per-unit metrics) | X2 `record_metrics`, called by S10 on unit completion |

### 4.5 Maintainability and Testability

| Requirement | Design response |
|---|---|
| NFR-MNT-01 (module separation) | §3 above |
| NFR-MNT-02 (unit tests) | `tests/unit/` covering documented behaviour |
| NFR-MNT-03 (property tests, Hypothesis) | `tests/properties/` targeting `domain/` only — possible because the domain is I/O-free |
| NFR-MNT-04 (round-trip properties) | D1 `to_dict`/`from_dict`, D5 `encode`/`decode`, coverage model serialisation |
| NFR-MNT-05 (invariant properties) | D5 uniqueness and monotonicity, D3 matrix bidirectional consistency, D2 totals equal the sum of parts, D4 reflexivity and symmetry |
| NFR-MNT-06 (domain-specific generators) | Hypothesis strategies producing realistic Jira keys, step structures and coverage models |
| NFR-MNT-07 (shrinking and reproducibility) | Hypothesis default shrinking; seeds recorded on failure |
| NFR-MNT-08 (maintainable generated automation) | A7 templates are the single reviewable place the coding standard lives |

**The PBT surface** (partial mode: PBT-02, PBT-03, PBT-07, PBT-08, PBT-09) is exactly D1 through
D8. This is the concrete payoff of the hexagonal decision — those components need no database, no
network and no fixtures to test.

### 4.6 Usability and Portability

| Requirement | Design response |
|---|---|
| NFR-USA-01 (one instruction per stage) | Per-stage chat modes with scoped tools; the operator names a feature, not a tool sequence |
| NFR-USA-02 (human-readable artefacts) | A8 emits Markdown and YAML readable in the editor |
| NFR-USA-03 (say what could not be determined) | Repository instructions require it; X1 remediation text carries it at the tool boundary |
| NFR-POR-01 (macOS, Windows, Linux on Python 3.11+) | Standard library plus pure-Python dependencies; `pathlib` throughout; no shell invocation in the toolchain |
| NFR-POR-02 (no cloud, no hosted component) | SQLite file and local directories only; the MCP server is a local process |

---

## 5. Extension Compliance at Design Level

### Security Baseline (enabled, blocking)

| Rule | Status | Where |
|---|---|---|
| SECURITY-01 Encryption | Compliant with one open decision | NFR-SEC-15, NFR-SEC-16; OD-04 open |
| SECURITY-02 Network intermediary logging | **N/A** | No load balancer, gateway or CDN — stdio local process |
| SECURITY-03 Application logging | Compliant | X2 |
| SECURITY-04 HTTP security headers | **N/A** | No HTML-serving endpoint |
| SECURITY-05 Input validation | Compliant | M1 schema validation, A2 parameterised queries |
| SECURITY-06 Least privilege | Compliant | P2 declares no write capability |
| SECURITY-07 Network configuration | Compliant | No listener opened |
| SECURITY-08 Application access control | **N/A** | Single-operator local process, no multi-tenant surface |
| SECURITY-09 Hardening | Compliant | X1 `sanitise`, no default credentials, X3 fails fast |
| SECURITY-10 Supply chain | Compliant | NFR-SEC-09 |
| SECURITY-11 Secure design | Compliant | Security-critical logic isolated in X1, X3, D7; the D7-plus-constraint pairing is defence in depth |
| SECURITY-12 Credentials | Compliant | X3 |
| SECURITY-13 Integrity | Compliant | NFR-SEC-05 safe loaders, A2 change auditing |
| SECURITY-14 Alerting | Partially N/A | No running service to alert on; audit logging and retention compliant via A2 and X2 |
| SECURITY-15 Exception handling | Compliant | X1 `Result`, M1 global handler, fail closed |

**No blocking security findings.**

### Resiliency Baseline (enabled)

| Rule | Status | Where |
|---|---|---|
| RESILIENCY-01 Critical workload identification | Compliant | The SQLite corpus is identified as the critical state |
| RESILIENCY-02 Availability and recovery targets | **Deferred** | OD-01, scheduled at NFR Requirements |
| RESILIENCY-03 Change management | **Deferred** | OD-02 |
| RESILIENCY-04 Deployment and rollback | **Deferred** | OD-02 |
| RESILIENCY-05 Monitoring | Compliant | X2, NFR-OBS-01, NFR-OBS-03 |
| RESILIENCY-06 Health checks | Compliant | X5 |
| RESILIENCY-07 Resiliency monitoring | Compliant | X2 per-unit metrics |
| RESILIENCY-08 Multi-zone and region | **N/A** | Workstation-local, no deployment topology |
| RESILIENCY-09 Auto-scaling | **N/A** | No scaling surface |
| RESILIENCY-10 Dependency isolation | Compliant | X4 retry and isolation |
| RESILIENCY-11 DR strategy | **Deferred** | OD-01 |
| RESILIENCY-12 Backup and replication | Compliant | A1 backups, S8 portable export |
| RESILIENCY-13 Failover procedures | **Deferred** | OD-03 |
| RESILIENCY-14 Resiliency testing | **Deferred** | OD-03 |
| RESILIENCY-15 Incident response | **N/A** | No production workload |

**No blocking resiliency findings.** Deferred items are user decision points the extension reserves
to you; they are scheduled at NFR Requirements, not decided here.

### Property-Based Testing (partial mode)

| Rule | Status | Where |
|---|---|---|
| PBT-02 Round-trip | Compliant | NFR-MNT-04, D1 and D5 |
| PBT-03 Invariants | Compliant | NFR-MNT-05, D2, D3, D4, D5 |
| PBT-07 Generator quality | Compliant | NFR-MNT-06 |
| PBT-08 Shrinking and reproducibility | Compliant | NFR-MNT-07 |
| PBT-09 Framework selection | Compliant | Hypothesis, NFR-MNT-03 |

PBT-01, 04, 05, 06 and 10 are advisory in partial mode. **No blocking PBT findings.**

---

## 6. Data Entity Ownership

Each of the 18 entities from `requirements.md` §10.2 has exactly one owning service.

| Entity | Owner | Repository |
|---|---|---|
| `resource`, `artefact` | S1 | `ArtefactRepository` |
| `feature`, `journey`, `business_rule` | S2 | `FeatureRepository` |
| `api_endpoint`, `screen`, `ui_element` | S2 | `FeatureRepository` |
| `testable_requirement` | S3 | `RequirementRepository` |
| `coverage_item` | S4 | `CoverageRepository` |
| `test_case`, `test_step`, `test_data` | S5 | `TestCaseRepository` |
| `trace_link` | S3, S5 (write); D3 (construct) | `TraceRepository` |
| `automated_test` | S6 | `AutomationRepository` |
| `run`, `unit_state` | S10 | `RunStateRepository` |
| `change_event` | S9 | `ChangeEventRepository` |

`trace_link` is the only entity written by two services. Both write through D3, which is the single
place link typing and Jira key enforcement are implemented, so the rule cannot diverge between them.

---

## 7. Requirement Coverage Verification

**Functional requirements: 88 of 88 mapped.**

| Group | Count | Owner |
|---|---|---|
| FR-AGT-01 to FR-AGT-06 | 6 | Agent Layer (§2.1) and M1, M2 |
| FR-ING-01 to FR-ING-10 | 10 | S1, A3, A4, A5, A6 |
| FR-ANA-01 to FR-ANA-08 | 8 | S2, A4 |
| FR-TRQ-01 to FR-TRQ-05 | 5 | S3, D3, D6, D7 |
| FR-COV-01 to FR-COV-07 | 7 | S4, D2 |
| FR-TCG-01 to FR-TCG-10 | 10 | S5, D1, D4, D5, D6, D7, A8 |
| FR-AUT-01 to FR-AUT-11 | 11 | S6, A7 |
| FR-HND-01 to FR-HND-06 | 6 | S7, A7 |
| FR-TRC-01 to FR-TRC-06 | 6 | D3, S3, S5, S8 |
| FR-BAT-01 to FR-BAT-07 | 7 | S10 |
| FR-DLT-01 to FR-DLT-07 | 7 | S9, D8, A3, A4 |
| FR-RPT-01 to FR-RPT-05 | 5 | S8, A9 |

**Non-functional requirements: 47 of 47 mapped** in §4 above.

**Total: 135 of 135.**

### Requirements with no component of their own

Five requirements are satisfied by the Agent Layer (§2.1) rather than by toolchain code:
FR-AGT-01, FR-AGT-02, FR-AGT-03, FR-AGT-04 and FR-AGT-06. They are configuration, not executable
components, and are specified in §2.1 rather than in [components.md](components.md).

---

## 8. Open Items Carried to CONSTRUCTION

| Item | Type | Resolved at |
|---|---|---|
| OD-01 Backup interval and recovery point for the corpus | Resiliency decision point | NFR Requirements |
| OD-02 Toolchain distribution and rollback across workstations | Resiliency decision point | NFR Requirements |
| OD-03 Recovery rehearsal frequency | Resiliency decision point | NFR Requirements |
| OD-04 Whether SQLCipher is required (affects A1) | Security decision point | NFR Requirements |
| Similarity threshold value and normalisation rules | Business rule | Functional Design (D4) |
| Coverage depth policy per test design technique | Business rule | Functional Design (D2) |
| Commit-to-key selection rule when several candidates exist | Business rule | Functional Design (D3) |
| Risk rating factor weights | Business rule | Functional Design (D6) |
| Automatability classification criteria | Business rule | Functional Design (D6) |

The five business rules are deliberately absent here. Application Design establishes interfaces;
Functional Design establishes the logic inside them.
