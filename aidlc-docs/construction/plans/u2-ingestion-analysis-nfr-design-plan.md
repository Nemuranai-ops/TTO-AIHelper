# NFR Design Plan — U2 Ingestion and Analysis

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U2 | **Stage**: NFR Design
**Created**: 2026-08-29T17:46:00Z
**Status**: APPROVED 2026-08-29T17:55:00Z - all recommendations accepted

---

## What U2 inherits

U1's 20 patterns and U7's 6. Two of U1's are exercised for the first time here:
P-RES-02 bounded retry and P-RES-03 per-resource isolation, both written for this unit.

Also inherited: the twelve patterns U1 and U7 deliberately declined. One of them —
**in-memory caching** — is worth re-examining, because U2 is the first unit where the
thing being cached is a network round trip rather than a local index lookup. Question
3 puts that decision back on the table rather than assuming it carries.

**Four questions.**

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Reliability: MCP client session lifecycle

The toolchain spawns the Atlassian and Bitbucket MCP servers as child processes.

A) **One session per ingestion run, opened at the start and closed in a `finally`.**
A spawn failure becomes `FAILED_MCP_UNREACHABLE` before any resource is attempted, so
the operator learns immediately rather than after nine resources fail one at a time.
**(Recommended)**

B) **One session per resource.** Better isolation between resources, and it pays the
spawn cost ten times while making a systemic credential problem look like ten
unrelated failures.

C) **A long-lived session** reused across runs. Fastest, and a server that dies
between runs leaves a broken client nobody notices until the next ingestion.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 2 — Scalability: where the ceiling is enforced

U2-NFR-SCL-03 caps a resource at 2,000 artefacts, and U2-NFR-SCL-04 requires the cap
to be reported.

A) **In the adapter, as it pages.** It stops requesting pages once the count is
reached and returns a flag with the records. **(Recommended — the adapter is the only
place that knows a further page exists, and stopping there means the excess is never
fetched, transferred or held)**

B) **In the service**, after the adapter returns everything. Simpler adapter, and it
fetches 8,000 issues in order to discard 6,000.

C) **In the manifest parser**, by refusing broad queries up front. Cannot work — the
result size is unknown until the query runs.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 3 — Performance: revisiting the in-memory cache

U1 declined in-memory caching because an indexed SQLite lookup is already
sub-millisecond. In U2 the equivalent saving is a network round trip, which is three
to four orders of magnitude larger. Does the decision still hold?

A) **Yes, and for a different reason than U1's.** The content hash already prevents
re-fetching *unchanged* artefacts across runs, which is the expensive case. Within a
single run each artefact is fetched once anyway, so a cache would have nothing to
serve. **(Recommended — the caching problem was already solved by the hash, and a
second mechanism would have invalidation without benefit)**

B) **No — add a session-scoped response cache** keyed by request, so a repeated fetch
within one run is free.

C) **No — add a persistent on-disk response cache** with a time-to-live.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 4 — Logical Components: what U2 needs

U1 added four supporting components, U7 added one. What does U2 need?

A) **Two: an `McpClientSession`** managing the child-process lifecycle and turning
transport failures into `Result`, and a **`PagedFetcher`** encapsulating page-by-page
retrieval with the ceiling and its report. **(Recommended — the session is a resource
with a lifetime, and paging-with-a-ceiling is logic four adapters would otherwise
each reimplement slightly differently)**

B) **One** — just the session; let each adapter page for itself.

C) **Three** — the above plus a `DiscrepancyDetector` as a component rather than
functions on the service.

D) **None** — put both concerns directly in the adapters.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

# Execution Checklist

## Phase 1: Pattern Selection

- [x] 1.1 Record which inherited patterns U2 uses, and which are exercised first here
- [x] 1.2 Specify the session lifecycle pattern per Question 1
- [x] 1.3 Specify the bounded paging pattern per Question 2
- [x] 1.4 Specify the hash-skip pattern and its relationship to caching per Question 3
- [x] 1.5 Specify the untrusted-input parsing pattern
- [x] 1.6 Specify the discrepancy recording pattern
- [x] 1.7 Record patterns re-examined and still declined, with reasons
- [x] 1.8 Map every pattern to the U2 NFR it delivers
- [x] 1.9 Write `nfr-design-patterns.md`

## Phase 2: Logical Components

- [x] 2.1 Define the components chosen in Question 4
- [x] 2.2 Define responsibilities and interfaces
- [x] 2.3 Place them within the hexagonal rings
- [x] 2.4 Define interaction with the four source adapters and with U1
- [x] 2.5 Define configuration additions
- [x] 2.6 Verify no new component violates the dependency rule or the read-only posture
- [x] 2.7 Write `logical-components.md`

## Phase 3: Validation

- [x] 3.1 Verify all 26 U2 NFR requirements have a delivering pattern or component
- [x] 3.2 Verify the read-only posture remains structural
- [x] 3.3 Verify Security and Resiliency compliance at design level
- [x] 3.4 Validate content per `common/content-validation.md`
- [x] 3.5 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `.../u2-ingestion-analysis/nfr-design/nfr-design-patterns.md`
- [x] `.../u2-ingestion-analysis/nfr-design/logical-components.md`
