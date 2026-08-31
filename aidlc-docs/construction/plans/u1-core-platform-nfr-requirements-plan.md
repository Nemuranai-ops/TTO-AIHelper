# NFR Requirements Plan — U1 Core Platform

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U1 | **Stage**: NFR Requirements
**Created**: 2026-08-29T09:46:00Z
**Status**: APPROVED 2026-08-29T10:00:00Z - all recommendations accepted

---

## Why this stage carries extra weight

Two sets of decisions land here and nowhere else.

**The four open decisions** deferred from `application-design.md` §11.9 — OD-01 to OD-04. All four
concern the SQLite database, the toolchain's distribution, and recovery. All three of those live in
U1, so the decisions are settled once here rather than revisited per unit.

**The Resiliency Baseline's User Decision Points.** The extension explicitly states that the model
*MUST ask, NOT decide* on eight decisions. Most of them assume a deployed cloud workload, and this
system is a local developer tool — but the extension is clear that N/A is your call to make, not
mine to assume. Where I believe N/A is correct I have said so and explained why, and left the
choice with you.

**Everything U1 decides, the other seven units inherit.** U1 is the only unit whose NFR Requirements
stage answers OD-01 to OD-04; U2 through U8 will inherit these and address only what is specific to
them.

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis. Tell me when done.

---

## Section A — Open Decisions from Application Design

### Question 1 — OD-01: Corpus recovery point (RESILIENCY-02, RESILIENCY-11)

The SQLite database is the system of record for a corpus that may represent weeks of generation
work. How much of that work is it acceptable to lose?

Note this is not the cloud DR question it resembles. There is no region to fail over to — the
question is how often the database is backed up and exported, and therefore how much re-generation
a lost file costs.

A) **Backup before every destructive or schema-changing operation, plus an automatic export after
every completed unit of work. Recovery point is effectively one unit — at most one feature's
generation is at risk.** **(Recommended — a unit is the natural checkpoint because it is already
transactional, and re-generating one feature is an afternoon rather than a week)**

B) **Backup before destructive operations only** (the current NFR-REL-05 baseline), with export on
operator request. Recovery point is the last manual export.

C) **Time-based**: automatic backup every 30 minutes regardless of activity.

D) **Every write**: backup after every committed transaction. Safest, and the most I/O overhead.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

### Question 2 — OD-04: Encryption at rest (SECURITY-01)

The database holds ingested Jira, Confluence and Bitbucket content — proprietary material — on
operator workstations.

A) **Rely on organisational full-disk encryption** (FileVault, BitLocker, LUKS), which is mandatory
on our machines. No file-level encryption; SQLCipher is not a dependency. **(Recommended if
full-disk encryption is genuinely enforced — it is the standard corporate control and adding
SQLCipher on top buys little)**

B) **Full-disk encryption is not guaranteed** — use SQLCipher for file-level database encryption,
with the key from the OS credential store.

C) **Belt and braces** — SQLCipher regardless of disk encryption, because the corpus is sensitive
enough to warrant defence in depth.

D) **Not sure whether full-disk encryption is enforced** — design for A but make the SQLCipher
backend a configuration switch so it can be turned on without a code change.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

### Question 3 — OD-02: Toolchain distribution and rollback (RESILIENCY-04)

How does `tto-testgen-mcp` reach each test-team workstation, and how is a bad version backed out?

A) **Git clone plus `uv sync` from the pinned lockfile.** Operators pull to update; rollback is
`git checkout` of a previous tag. No packaging infrastructure needed, and the lockfile guarantees
identical dependencies. **(Recommended — you already have a test-team Bitbucket repository, and
this is the lowest-ceremony option that still pins everything)**

B) **Internal package index** — publish wheels to a corporate PyPI mirror; operators
`pip install --upgrade`. Cleaner for non-technical users, requires index infrastructure.

C) **Use our existing organisational distribution mechanism** — please name it and I will conform
the design to it rather than proposing a new one.

D) **Single-machine install** — only one operator runs the toolchain; distribution is not a concern.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

### Question 4 — OD-03: Recovery rehearsal (RESILIENCY-13, RESILIENCY-14)

A backup nobody has restored is a hypothesis rather than a control.

A) **Document a restore procedure and a rehearsal scenario now; execute the rehearsal once before
the corpus first exceeds 1,000 cases, and after any schema migration.** **(Recommended — tying the
rehearsal to a corpus milestone and to migrations puts it exactly where the risk actually rises)**

B) **Use our existing DR testing or game-day practice** — please name it and I will document
scenarios that fit it.

C) **Defer to the Operations phase** — capture the scenarios now, execute later.

D) **No rehearsal** — accept the backup as untested. Document the residual risk.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

## Section B — Resiliency Extension Decision Points

These are reserved to you by the Resiliency Baseline. I have given my reading of each, but the
decision is yours.

### Question 5 — Change management process (RESILIENCY-03)

How should changes to the TAAS toolchain itself be governed?

A) **N/A — exempt as internal tooling.** TAAS is a test-team tool with no production deployment and
no external users; changes are governed by ordinary code review on the repository.
**(Recommended — the rule itself offers this option for internal tooling, and the exemption
rationale is recorded rather than assumed)**

B) **Use our existing organisational change management process** — please name it (ServiceNow, Jira
Change, internal CAB) and I will make the artefacts fit it.

C) **No formal process exists** — propose a lightweight one (change record, approval, rollback note)
for the team to adopt.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

### Question 6 — Deployment style (RESILIENCY-04)

What deployment strategy applies to the toolchain?

A) **Direct / in-place.** Operators update their own workstation install. Blast radius is one
machine, and the previous version is a `git checkout` away. **(Recommended — rolling, blue/green
and canary all presuppose a fleet serving traffic, which this is not)**

B) **Staged** — one operator updates first and confirms before the rest follow.

C) **N/A** — deployment is not a meaningful concept for this workload.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

### Question 7 — Regional topology (RESILIENCY-08)

What fault-isolation topology applies?

A) **N/A — no cloud deployment.** TAAS runs as a local process on operator workstations. There is no
region, no availability zone, and no traffic to isolate. NFR-POR-02 requires exactly this.
**(Recommended — this is a statement of fact about the architecture rather than a preference)**

B) Single-region multi-zone — applicable only if you intend to host the toolchain centrally.

C) Multi-region — applicable only if you intend to host it centrally with cross-region redundancy.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

### Question 8 — Incident response (RESILIENCY-15)

How are failures in TAAS handled?

A) **N/A as a production incident process; failures surface in-session to the operator.** There is
no running service, no on-call, and no user affected by an outage. The operator sees the failure,
the run state is preserved, and work resumes. **(Recommended — but I want your explicit agreement
rather than my assumption, because the extension reserves this decision to you)**

B) **Use our existing incident response process** — please name it and I will align logging and any
alerting to it.

C) **No formal process exists** — propose a lightweight incident and correction-of-errors process.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

## Section C — Tech Stack

### Question 9 — Dependency management and packaging

A) **`uv` with `uv.lock`.** Fast, produces a committed lockfile satisfying NFR-SEC-09, handles
Python version pinning, and works identically on macOS, Windows and Linux.
**(Recommended — the repository layout in `unit-of-work.md` already assumes `uv.lock`)**

B) **Poetry with `poetry.lock`** — mature and widely known, slower.

C) **pip-tools with `requirements.txt` plus a hash-pinned lock** — simplest, least tooling, most
manual.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

### Question 10 — Core libraries

A) **Official `mcp` Python SDK for the server; Pydantic v2 for tool schemas and validation;
`sqlite3` from the standard library; Jinja2 for templates; pytest plus Hypothesis for tests.**
**(Recommended — Pydantic v2 gives NFR-SEC-03's typed input validation and the MCP tool schemas from
one definition, which removes a class of drift between what is declared and what is checked)**

B) Same, but **dataclasses plus manual validation** instead of Pydantic — fewer dependencies, more
validation code to write and keep in step with the schemas.

C) Same, but **attrs plus cattrs** for serialisation.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

### Question 11 — Similarity implementation (BR-1)

A) **Standard library only** — shingles as a `set` of string slices, Jaccard as set arithmetic. No
dependency, fully deterministic, trivially property-testable. **(Recommended — the algorithm is a
dozen lines and a library would add a dependency and a version to pin for no gain)**

B) **`rapidfuzz`** — C-backed string similarity, faster on large comparisons, adds a binary
dependency.

C) **`datasketch` MinHash/LSH** — sublinear candidate selection, valuable well beyond 10,000 cases
and more machinery than the current budget requires.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

## Section D — Verification

### Question 12 — Performance budget verification

NFR-PRF-01 sets 200 ms for single-case operations and NFR-PRF-02 sets 30 seconds for full reports,
both at 10,000 cases. How should those be proven rather than asserted?

A) **A seeded benchmark suite** that generates a synthetic 10,000-case corpus and asserts both
budgets, run on demand and before any release. **(Recommended — a budget nobody measures is a
comment, and the synthetic corpus is cheap to generate from the domain model)**

B) **Manual measurement** during Build and Test, recorded once.

C) **Continuous benchmarking** with regression detection against a stored baseline.

D) **Defer** — treat the budgets as design targets and measure only if a problem appears.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

# Execution Checklist

## Phase 1: NFR Determination

- [x] 1.1 Record scalability requirements for U1 with their measurement points
- [x] 1.2 Record performance requirements and the verification approach from Question 12
- [x] 1.3 Record availability and recovery requirements from Questions 1 and 4
- [x] 1.4 Record security requirements including the Question 2 encryption decision
- [x] 1.5 Record reliability requirements: transactions, retry, isolation
- [x] 1.6 Record maintainability requirements including the PBT surface
- [x] 1.7 Record usability requirements applicable to U1
- [x] 1.8 Resolve OD-01 to OD-04 and mark them closed
- [x] 1.9 Record every Resiliency decision point with its answer and rationale
- [x] 1.10 Write `nfr-requirements.md`

## Phase 2: Tech Stack

- [x] 2.1 Record the language and runtime decision with its constraint source
- [x] 2.2 Record dependency management and packaging from Question 9
- [x] 2.3 Record core libraries from Question 10 with rationale per choice
- [x] 2.4 Record the similarity implementation from Question 11
- [x] 2.5 Record the testing stack
- [x] 2.6 Record rejected alternatives and why
- [x] 2.7 Verify every dependency is pinnable and available on all three platforms
- [x] 2.8 Record the supply chain approach: lockfile, vulnerability scanning, SBOM
- [x] 2.9 Write `tech-stack-decisions.md`

## Phase 3: Validation

- [x] 3.1 Verify all 47 project NFRs are addressed or explicitly out of U1's scope
- [x] 3.2 Verify Security Baseline compliance with no unresolved blocking finding
- [x] 3.3 Verify Resiliency Baseline compliance with every decision point answered
- [x] 3.4 Verify PBT partial-mode compliance
- [x] 3.5 Verify the tech stack satisfies NFR-POR-01 cross-platform support
- [x] 3.6 Validate content per `common/content-validation.md`
- [x] 3.7 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `aidlc-docs/construction/u1-core-platform/nfr-requirements/nfr-requirements.md`
- [x] `aidlc-docs/construction/u1-core-platform/nfr-requirements/tech-stack-decisions.md`
