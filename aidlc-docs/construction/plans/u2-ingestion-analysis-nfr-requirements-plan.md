# NFR Requirements Plan — U2 Ingestion and Analysis

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U2 | **Stage**: NFR Requirements
**Created**: 2026-08-29T17:21:00Z
**Status**: APPROVED 2026-08-29T17:35:00Z - all recommendations accepted

---

## What U2 inherits

Everything U1 settled: OD-01 to OD-04, all eight Resiliency decision points, the tech
stack, and 37 of the 47 project NFRs. None is re-opened.

**U2 owns two project NFRs outright**: NFR-SCL-01 (3-10 repos, 100-500 stories,
30-150 screens) and NFR-PRF-04 (content-hash caching). It is also the only unit that
makes an external network call, which makes several inherited patterns real here for
the first time — U1's bounded retry and per-resource isolation were written for this
unit and never exercised in it or U7.

**Five questions.**

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Scalability: paging a large Jira project

NFR-SCL-01 assumes 100-500 stories. A JQL query against a live project can return far
more — a five-year-old project might hold 8,000 issues.

A) **Page through with a hard ceiling and report when it is hit.** Fetch in pages of
100 up to a configurable maximum of 2,000 issues per resource, then stop and tell the
operator the query is too broad. **(Recommended — silently ingesting 8,000 issues
would blow past the scale the whole system is designed for, and the operator can
narrow the JQL in a minute if they are told)**

B) **Page without a ceiling.** Ingest whatever the query returns.

C) **Refuse any query returning more than the ceiling**, ingesting nothing.

D) **Ceiling with no report** — take the first 2,000 quietly.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 2 — Performance: ingestion concurrency

Ten repositories fetched one after another is slow, and most of the time is spent
waiting on the network. U1 declined async for the toolchain as a whole.

A) **Sequential, with the content-hash skip doing the real work.** A second run
touches only what changed, so the slow case is the first run and it is slow once.
**(Recommended — U1 declined async because a single-operator local process gains
concurrency semantics and their bugs for no throughput that matters. Ingestion is the
one place that argument is weakest, but a first run taking minutes rather than seconds
is not a problem worth new failure modes)**

B) **A bounded thread pool** over resources — four at a time. Faster first run,
and per-resource isolation now has to be thread-safe.

C) **Async with `asyncio`** — fastest, and it makes the whole toolchain async.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 3 — Reliability: timeout budget per external call

U1's retry policy covers transient failures. It needs a timeout to classify one.

A) **30 seconds per call, configurable.** Long enough for a large Confluence page or
a slow JQL query, short enough that three retries plus backoff stay inside two
minutes. **(Recommended)**

B) **10 seconds** — fast failure detection, and a legitimately slow query gets
retried three times before failing anyway, which is slower than waiting once.

C) **120 seconds** — tolerant, and a hung connection blocks the run for six minutes
across retries.

D) **No timeout** — rely on the MCP server's own.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 4 — Reliability: resuming a partially ingested resource

A repository with 500 files fails at file 300. The resource's transaction rolls back,
so nothing from it was stored.

A) **Re-fetch the whole resource on retry, relying on the content-hash skip to make
it cheap.** Unchanged artefacts are recognised without a store. **(Recommended — a
resource is the transaction boundary, and sub-resource checkpointing would mean a
partially-ingested repository could be mistaken for a complete one)**

B) **Checkpoint within a resource**, committing every 100 artefacts. Faster recovery,
and a resource can now be half-ingested with nothing recording that.

C) **Mark the resource failed and require the operator to re-run it explicitly.**

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 5 — Security: credentials for the toolchain's MCP client

The toolchain acts as an MCP client to Atlassian and Bitbucket, so it needs the same
credentials the agent's MCP servers use.

A) **One credential per service, shared between the agent's MCP registration and the
toolchain, read from the environment or the OS credential store.** Both are the same
operator with the same access. **(Recommended — two credentials for one person and
one permission set is bookkeeping without a security benefit, and the second one gets
rotated late)**

B) **Separate credentials** for the toolchain, so its access can be revoked
independently.

C) **The toolchain reuses the agent's session** rather than holding a credential —
not available: MCP servers do not delegate credentials to other MCP servers.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

# Execution Checklist

## Phase 1: NFR Determination

- [x] 1.1 Record scalability requirements: input volume ceilings and paging
- [x] 1.2 Record performance requirements: ingestion throughput, hash-skip efficiency
- [x] 1.3 Record reliability requirements: timeouts, retry, isolation, resource-level atomicity
- [x] 1.4 Record security requirements: credential handling, read-only posture, untrusted input
- [x] 1.5 Record observability requirements specific to external calls
- [x] 1.6 Confirm every inherited U1 decision applies unchanged
- [x] 1.7 Write `nfr-requirements.md`

## Phase 2: Tech Stack

- [x] 2.1 Confirm the U1 stack applies, and record any U2-specific dependency
- [x] 2.2 Record how the toolchain acts as an MCP client
- [x] 2.3 Record the OpenAPI parsing approach
- [x] 2.4 Write `tech-stack-decisions.md`

## Phase 3: Validation

- [x] 3.1 Verify the two U2-owned project NFRs are addressed
- [x] 3.2 Verify the read-only posture holds structurally
- [x] 3.3 Verify Security and Resiliency applicability
- [x] 3.4 Validate content per `common/content-validation.md`
- [x] 3.5 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `.../u2-ingestion-analysis/nfr-requirements/nfr-requirements.md`
- [x] `.../u2-ingestion-analysis/nfr-requirements/tech-stack-decisions.md`
