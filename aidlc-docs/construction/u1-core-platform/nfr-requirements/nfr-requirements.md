# NFR Requirements — U1 Core Platform

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U1 | **Stage**: NFR Requirements
**Version**: 1.0 | **Date**: 2026-08-29

---

## 1. Open Decisions — Now Closed

All four decisions deferred from `application-design.md` §11.9 are resolved. They concern the
database, distribution and recovery, all of which live in U1, so they are settled once here and
inherited by U2 through U8.

### OD-01 — Corpus recovery point (RESILIENCY-02, RESILIENCY-11) — **CLOSED**

**Decision**: back up before every destructive or schema-changing operation, and export
automatically after every completed unit of work.

**Recovery point**: one unit of work. At most one feature's generation is at risk.

**Rationale**: a unit is already the transactional boundary, so it is the natural checkpoint —
nothing extra has to be invented to know when a consistent state exists. Losing one feature's
generation costs an afternoon; losing a week's costs a week.

| Requirement | Statement | Measurement |
|---|---|---|
| U1-NFR-REC-01 | A backup is taken before any migration or destructive operation | Backup file exists with a timestamp preceding the operation |
| U1-NFR-REC-02 | A portable export is written after each `unit_complete` | Export file exists for every completed unit |
| U1-NFR-REC-03 | An export is sufficient to reconstruct the corpus without the database file | Restore rehearsal per OD-03 |
| U1-NFR-REC-04 | Backups are retained locally, oldest pruned beyond 10 | Backup directory holds at most 10 |

### OD-02 — Toolchain distribution and rollback (RESILIENCY-04) — **CLOSED**

**Decision**: git clone plus `uv sync` from the committed lockfile. Rollback is `git checkout` of a
previous tag followed by `uv sync`.

**Rationale**: the test team already has a Bitbucket repository. This is the lowest-ceremony option
that still pins every dependency exactly, and it needs no package-index infrastructure.

| Requirement | Statement | Measurement |
|---|---|---|
| U1-NFR-DIST-01 | `uv sync` from the committed lockfile produces an identical dependency set on any workstation | Verified on macOS, Windows and Linux |
| U1-NFR-DIST-02 | Every release is a git tag | Tag exists per release |
| U1-NFR-DIST-03 | Rollback is `git checkout <tag>` then `uv sync`, with no manual steps | Documented in README, rehearsed once |
| U1-NFR-DIST-04 | A schema migration is reversible, so a rollback across one does not strand the database | Reverse migration exists and is tested per migration |

**U1-NFR-DIST-04 is the one that needs care.** Rolling the code back is trivial; rolling it back
across a schema migration is not. Every forward migration ships with its reverse, and the pair is
tested together.

### OD-03 — Recovery rehearsal (RESILIENCY-13, RESILIENCY-14) — **CLOSED**

**Decision**: document a restore procedure and rehearsal scenario now. Execute the rehearsal before
the corpus first exceeds 1,000 cases, and after every schema migration.

**Rationale**: both triggers are points where the value at risk rises sharply. A backup nobody has
restored is a hypothesis.

| Requirement | Statement | Measurement |
|---|---|---|
| U1-NFR-REH-01 | A restore procedure is documented in the repository | Document exists |
| U1-NFR-REH-02 | A rehearsal scenario covers database loss and corruption | Scenario documented |
| U1-NFR-REH-03 | The rehearsal is executed before the corpus exceeds 1,000 cases | Result recorded with date |
| U1-NFR-REH-04 | The rehearsal is executed after each schema migration | Result recorded per migration |

### OD-04 — Encryption at rest (SECURITY-01) — **CLOSED, with a stated assumption**

**Decision**: rely on organisational full-disk encryption. SQLCipher is not a dependency.

> **AS-02 — assumption requiring confirmation.** This decision rests on full-disk encryption being
> mandatory and enforced on operator workstations. That is a fact about your estate which I cannot
> verify. I flagged it before the decision was accepted; the acceptance stands as your decision, and
> it is recorded here as an assumption rather than as a verified fact.
>
> **Verification action**: confirm with whoever owns workstation policy that FileVault, BitLocker or
> LUKS is enforced on every machine that will run TAAS.
>
> **If the assumption is wrong**: the repository pattern chosen at Application Design contains the
> change. Adding a SQLCipher backend touches A1 SqliteSchemaManager and A2 SqliteRepositories and
> nothing else — no service, no domain component, and no other unit.

| Requirement | Statement | Measurement |
|---|---|---|
| U1-NFR-ENC-01 | The database file is stored only within the workspace `.taas/` directory | No write outside the workspace |
| U1-NFR-ENC-02 | `.taas/` and `generated/` are gitignored so ingested content cannot reach version control | `.gitignore` verified; a clean-clone check finds neither |
| U1-NFR-ENC-03 | No network transport is used by the MCP server | stdio only; no listener opened |
| U1-NFR-ENC-04 | External traffic uses TLS 1.2 or above | Inherited from the MCP servers called |

---

## 2. Resiliency Decision Points — All Answered

The Resiliency Baseline reserves eight decisions to the user. Every one now has an explicit answer.

| Decision | Rule | Answer | Rationale |
|---|---|---|---|
| RTO/RPO and DR strategy | RESILIENCY-02, -11 | Unit-level recovery point (OD-01) | No region to fail to; the question is re-generation cost |
| Change management | RESILIENCY-03 | **N/A — exempt as internal tooling** | Test-team tool, no production deployment, no external users; governed by code review. The rule itself offers this option for internal tooling |
| CI/CD tooling | RESILIENCY-04 | git plus `uv sync` (OD-02) | No pipeline needed for a workstation-local tool |
| Rollback mechanism | RESILIENCY-04 | Version-pinned: `git checkout` plus `uv sync` | With reverse migrations per U1-NFR-DIST-04 |
| Deployment style | RESILIENCY-04 | **Direct / in-place** | Blast radius is one workstation; rolling, blue/green and canary all presuppose a fleet serving traffic |
| Regional topology | RESILIENCY-08 | **N/A — no cloud deployment** | NFR-POR-02 requires local-only operation. A statement of architectural fact |
| Resiliency testing | RESILIENCY-14 | Rehearsal at defined triggers (OD-03) | |
| Incident response | RESILIENCY-15 | **N/A as a production process** | No running service, no on-call, no affected user. Failures surface in-session with run state preserved |

**Three N/A answers, each explicitly chosen rather than assumed.** The extension is clear that the
model must ask rather than decide on these points. Where N/A was plainly correct I said so and gave
my reasoning, but the answer came from you.

---

## 3. NFR Requirements by Category

### 3.1 Scalability

| ID | Requirement | Source | Measurement |
|---|---|---|---|
| U1-NFR-SCL-01 | Storage and indexing remain responsive at 10,000 test cases | NFR-SCL-03 | Benchmark suite |
| U1-NFR-SCL-02 | The corpus may reach the thousands without schema change | NFR-SCL-02 | Benchmark at 10,000 |
| U1-NFR-SCL-03 | No operation requires the whole corpus in memory | NFR-SCL-04 | Every query is filtered or paged; no unbounded list tool exists |
| U1-NFR-SCL-04 | Identifier sequences accommodate 99,999 per kind per feature | BR-6.2 | Overflow fails explicitly rather than wrapping |

### 3.2 Performance

| ID | Requirement | Budget | Measurement |
|---|---|---|---|
| U1-NFR-PRF-01 | Single-case operation | < 200 ms at 10,000 cases | Benchmark suite, asserted |
| U1-NFR-PRF-02 | Full report generation | < 30 s at 10,000 cases | Benchmark suite, asserted |
| U1-NFR-PRF-03 | Duplicate detection uses indexed candidate selection | No full scan | `EXPLAIN QUERY PLAN` confirms `idx_case_bucket` use |
| U1-NFR-PRF-04 | Content-hash lookup for skip-if-unchanged | < 10 ms | Indexed on `artefact.content_hash` |

**Verification is by a seeded benchmark suite** that generates a synthetic 10,000-case corpus and
asserts both budgets. It runs on demand and before any release.

A budget nobody measures is a comment. The synthetic corpus is cheap to generate from the domain
model, so there is no reason to leave these as aspirations.

### 3.3 Availability and Recovery

Covered by OD-01 and OD-03 above. No uptime target applies — U1 is a library and a local process,
not a service. It is available when the operator starts it.

### 3.4 Security

| ID | Requirement | Source | Measurement |
|---|---|---|---|
| U1-NFR-SEC-01 | No credential in source, database, logs or artefacts | NFR-SEC-01 | Secret scan in CI and pre-release |
| U1-NFR-SEC-02 | stdio transport only, no network listener | NFR-SEC-02 | No socket bind in the codebase |
| U1-NFR-SEC-03 | Every MCP tool input validated against a typed schema before any logic | NFR-SEC-03 | Pydantic model per tool; validation precedes the handler |
| U1-NFR-SEC-04 | All SQL parameterised | NFR-SEC-04 | No f-string or concatenation in any query module; enforced in review |
| U1-NFR-SEC-05 | Safe YAML and JSON loading only | NFR-SEC-05 | `yaml.safe_load`; no `pickle`, no `eval` |
| U1-NFR-SEC-06 | Structured logs with correlation id, no secrets or personal data | NFR-SEC-06 | Redaction filter; log inspection in tests |
| U1-NFR-SEC-07 | No exception crosses the MCP boundary | NFR-SEC-07 | Global handler; every tool returns `Result` |
| U1-NFR-SEC-08 | Error messages carry no path outside the workspace and no stack detail | NFR-SEC-08 | `sanitise()` applied to every message; asserted in tests |
| U1-NFR-SEC-09 | Dependencies pinned, scanned, and an SBOM produced | NFR-SEC-09 | `uv.lock` committed; `pip-audit` in the release check; CycloneDX SBOM |
| U1-NFR-SEC-10 | Audit trail on every case and coverage mutation | NFR-SEC-13 | Actor, timestamp and change recorded |
| U1-NFR-SEC-11 | No write tool against Atlassian or Bitbucket is reachable | NFR-SEC-14 | P2 protocols declare no write method |
| U1-NFR-SEC-12 | Database and generated artefacts excluded from version control | NFR-SEC-12 | `.gitignore`; clean-clone check |

**U1-NFR-SEC-11 is structural rather than procedural.** The source port protocols contain no write
method, so no component can call one. There is nothing to remember and nothing to review for.

### 3.5 Reliability

| ID | Requirement | Source | Measurement |
|---|---|---|---|
| U1-NFR-REL-01 | Every state change is transactional | NFR-REL-01 | Interrupted operation leaves a consistent database |
| U1-NFR-REL-02 | Bounded retry: 3 attempts, 1s/2s/4s with jitter, transient classes only | NFR-REL-03 | Retry policy asserted in tests |
| U1-NFR-REL-03 | Retries never applied to 4xx auth or validation failures | NFR-REL-03 | Asserted in tests |
| U1-NFR-REL-04 | A failed unit does not fail the run | NFR-REL-04 | Isolation asserted in tests |
| U1-NFR-REL-05 | A killed process leaves no partial output and the unit shows `in-progress` | FR-BAT-04, FR-BAT-05 | Kill-during-write test |
| U1-NFR-REL-06 | Stale locks are detected and reported with recovery guidance | US-BAT-03 AC4 | Asserted in tests |
| U1-NFR-REL-07 | Migrations are versioned and reversible | NFR-REL-07 | Every forward migration has a tested reverse |

### 3.6 Observability

| ID | Requirement | Source | Measurement |
|---|---|---|---|
| U1-NFR-OBS-01 | Every MCP tool invocation logged with correlation id and unit reference | NFR-OBS-01 | Log inspection |
| U1-NFR-OBS-02 | Health check reports database, schema version and per-server MCP reachability independently | NFR-OBS-02 | One unreachable server does not read as total failure |
| U1-NFR-OBS-03 | Per-unit metrics recorded on completion | NFR-OBS-03 | `unit_state.metrics` populated |

### 3.7 Maintainability

| ID | Requirement | Source | Measurement |
|---|---|---|---|
| U1-NFR-MNT-01 | Module separation per the hexagonal structure | NFR-MNT-01 | Import-linter rule: `domain` imports nothing outside stdlib and `domain` |
| U1-NFR-MNT-02 | Example-based tests cover documented behaviour | NFR-MNT-02 | Coverage report |
| U1-NFR-MNT-03 | Property-based tests cover the 16-property surface | NFR-MNT-03 to -07 | All 16 properties present and passing |
| U1-NFR-MNT-04 | Domain-specific Hypothesis generators, not primitives | PBT-07 | Strategies reviewed |
| U1-NFR-MNT-05 | Failing property seeds recorded for deterministic replay | PBT-08 | Seed in the test report |

**U1-NFR-MNT-01 is enforced mechanically.** An import-linter contract fails the build if a domain
module imports an adapter. The hexagonal boundary is the precondition for the property tests, so
letting it erode silently would quietly remove the ability to test the invariants at all.

### 3.8 Portability

| ID | Requirement | Source | Measurement |
|---|---|---|---|
| U1-NFR-POR-01 | Runs on macOS, Windows and Linux with Python 3.11+ | NFR-POR-01 | CI matrix across all three |
| U1-NFR-POR-02 | No cloud service, no hosted component | NFR-POR-02 | No network dependency beyond the MCP servers called |
| U1-NFR-POR-03 | `pathlib` throughout; no shell invocation | NFR-POR-01 | No `os.system`, no `subprocess` with a shell |

---

## 4. Project NFR Ownership

Which of the 47 project NFRs U1 owns, and which belong elsewhere.

| Group | Owned by U1 | Owned elsewhere |
|---|---|---|
| NFR-SCL (4) | -02, -03, -04 | -01 ingestion scale → U2 |
| NFR-PRF (4) | -01, -02, -03 | -04 content-hash caching → U2 uses the U1 mechanism |
| NFR-REL (7) | all 7 | — |
| NFR-SEC (16) | -01 to -09, -12 to -16 | -10, -11 confidentiality and synthetic data → U4, U5 |
| NFR-OBS (3) | all 3 | — |
| NFR-MNT (8) | -01 to -07 | -08 maintainable generated automation → U5 |
| NFR-USA (3) | — | -01, -03 → U7; -02 → U4 |
| NFR-POR (2) | both | — |

**U1 owns 37 of 47.** That concentration is the point of a foundation unit: the cross-cutting
qualities are decided and enforced once, and the other seven units inherit them rather than
re-deciding.

---

## 5. Extension Compliance

### Security Baseline (blocking)

| Rule | Status | Evidence |
|---|---|---|
| SECURITY-01 | Compliant, AS-02 stated | U1-NFR-ENC-01 to -04; full-disk encryption assumption recorded with verification action |
| SECURITY-02 | N/A | No network intermediary |
| SECURITY-03 | Compliant | U1-NFR-SEC-06 |
| SECURITY-04 | N/A | No HTML-serving endpoint |
| SECURITY-05 | Compliant | U1-NFR-SEC-03, -04 |
| SECURITY-06 | Compliant | U1-NFR-SEC-11 |
| SECURITY-07 | Compliant | U1-NFR-SEC-02 |
| SECURITY-08 | N/A | Single-operator local process |
| SECURITY-09 | Compliant | U1-NFR-SEC-08; no default credentials; config fails fast |
| SECURITY-10 | Compliant | U1-NFR-SEC-09 |
| SECURITY-11 | Compliant | Security logic isolated in X1, X3, D7; dual enforcement is defence in depth |
| SECURITY-12 | Compliant | U1-NFR-SEC-01 |
| SECURITY-13 | Compliant | U1-NFR-SEC-05, -10 |
| SECURITY-14 | Partially N/A | Audit logging and retention compliant; alerting N/A with no running service |
| SECURITY-15 | Compliant | U1-NFR-SEC-07; `Result` taxonomy; fail closed |

**No blocking security findings.**

### Resiliency Baseline

All eight decision points answered in §2. RESILIENCY-01 (critical workload identified: the corpus),
-05, -06, -07 (observability §3.6), -10 (isolation §3.5), -12 (backup OD-01) compliant. -03, -08,
-15 answered N/A by the user with rationale. -02, -04, -11, -13, -14 answered via OD-01 to OD-03.

**No blocking resiliency findings. No decision points remain open.**

### Property-Based Testing (partial)

PBT-02, -03 (16-property surface), -07 (domain generators), -08 (shrinking and seeds), -09
(Hypothesis) all compliant per §3.7.

**No blocking PBT findings.**

---

## 6. Open Items After This Stage

**None.** OD-01 through OD-04 are closed. Every Resiliency decision point is answered.

One assumption stands: **AS-02**, full-disk encryption enforcement. It carries a verification action
and a contained remediation path, and it does not block any downstream stage.
