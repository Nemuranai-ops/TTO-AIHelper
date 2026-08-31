# NFR Design Plan — U3 Requirements and Coverage

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U3 | **Stage**: NFR Design
**Created**: 2026-08-30T09:26:00Z
**Status**: APPROVED 2026-08-30T09:35:00Z - all recommendations accepted

---

## What U3 inherits

31 patterns: 20 from U1, 6 from U7, 5 from U2. U3 uses many and adds few, because it
orchestrates logic that already carries its own patterns.

| Inherited | Use in U3 |
|---|---|
| P-RES-01 Unit of Work | One transaction per requirement batch, per coverage build |
| P-SCL-01 Capped pagination | Requirement queries inherit the 200-record cap |
| P-SEC-01 Two-level validation | Pydantic at the boundary, D7 beneath |
| P-U2-02 Bounded paging | The pattern the commit index bound follows |
| P-U7-01 Request-scoped cache | The shape the commit index takes |
| P-MNT-02 Import contracts | Enforce that U3 holds no coverage arithmetic |

**Three questions.** Fewer than any unit so far, and that is the honest consequence of
U3 adding orchestration rather than mechanism.

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Performance: where the commit index lives

`CommitIndex` caches history per file for one run. U7's `ReportContext` is
request-scoped; U2's hash-skip is database-resident. Which shape fits here?

A) **Run-scoped, held by the service for the duration of one `requirements_upsert`
call, discarded after.** The bounds from U3-NFR-IDX-01 and -02 apply to that scope.
**(Recommended — a requirement batch is the natural boundary: every requirement in it
draws on the same files, and holding the index beyond the call would mean deciding
when it goes stale, which is a question with no good answer)**

B) **Session-scoped**, surviving across calls within one operator session. Fewer
fetches across a multi-batch feature, and now the index can serve history that
changed since it was built.

C) **Database-resident**, storing commit records in a table. Survives restarts, and
adds a synchronisation obligation with a repository that moves.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 2 — Reliability: how `approval_invalidated` reaches the operator

U3-NFR-REL-05 requires a rebuild that changes the hash to report that a prior approval
no longer applies.

A) **A field on the successful result, plus a log line naming the previous approver
and date.** The rebuild succeeds — nothing is wrong — and the consequence is stated in
the same response. **(Recommended — this is information, not an error. Returning it as
a failure would be misleading, and burying it in a log the operator does not read
would be useless)**

B) **A distinct `REJECTED_*` code**, refusing the rebuild until acknowledged.

C) **A log line only.**

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 3 — Logical Components: what U3 needs

U1 added four supporting components, U7 one, U2 two.

A) **One: a `CommitIndex`** with its bounds and reporting. Everything else U3 needs
exists — D2, D3, D6, D7, L5, A4. **(Recommended — resisting the urge to wrap
orchestration in components is the right call when the components would hold no state
and no policy of their own)**

B) **Two**: `CommitIndex` plus a `CoverageHasher`. The hashing is eight lines and its
rules live in BR-U3-4.2.

C) **Three**: the above plus an `AtomicityChecker`. Also a pure function.

D) **None** — put the index in the service.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

# Execution Checklist

## Phase 1: Pattern Selection

- [x] 1.1 Record which inherited patterns U3 uses
- [x] 1.2 Specify the run-scoped index pattern per Question 1
- [x] 1.3 Specify the informational-result pattern per Question 2
- [x] 1.4 Specify the deterministic hashing pattern
- [x] 1.5 Specify the bounded-with-reporting pattern as applied to the index
- [x] 1.6 Record patterns considered and declined for U3
- [x] 1.7 Map every pattern to the U3 NFR it delivers
- [x] 1.8 Write `nfr-design-patterns.md`

## Phase 2: Logical Components

- [x] 2.1 Define the components chosen in Question 3
- [x] 2.2 Define responsibilities, interfaces and bounds
- [x] 2.3 Place them within the hexagonal rings
- [x] 2.4 Define configuration additions
- [x] 2.5 Verify no new component violates the dependency rule
- [x] 2.6 Write `logical-components.md`

## Phase 3: Validation

- [x] 3.1 Verify all 24 U3 NFR requirements have a delivering pattern or component
- [x] 3.2 Verify U3 holds no coverage arithmetic and no risk formula
- [x] 3.3 Verify Security and Resiliency compliance at design level
- [x] 3.4 Validate content per `common/content-validation.md`
- [x] 3.5 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `.../u3-requirements-coverage/nfr-design/nfr-design-patterns.md`
- [x] `.../u3-requirements-coverage/nfr-design/logical-components.md`
