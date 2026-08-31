# NFR Requirements Plan — U5 Automation Emission

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U5 | **Stage**: NFR Requirements
**Created**: 2026-08-30T13:56:00Z
**Status**: APPROVED 2026-08-30 — all recommendations accepted

---

## What U5 inherits

OD-01 to OD-04, the eight Resiliency decision points, the tech stack, and the project
NFRs owned by U1, U2, U3, U4 and U7. **Nothing re-opened.**

**U5 shares two project NFRs with U4**: NFR-SEC-10 (confidentiality) and NFR-SEC-11
(synthetic test data). U4 keeps them out of the corpus; U5 keeps them out of the
TypeScript, which is the copy that leaves the workspace.

**One new dependency arrives here**: Jinja2, declared in `pyproject.toml` since U1 and
unused until now.

---

## Why U5's non-functionals differ from every prior unit

| | Prior units | U5 |
|---|---|---|
| Correctness | Semantic — is the answer right? | **Byte-identical reproducibility** |
| Consumer | The system itself | **A person and a Jenkins agent** |
| Failure mode | A wrong record | **A suite nobody trusts** |

Determinism is not a nice property here; it is the acceptance criterion. If two runs of
an unchanged corpus produce different bytes, hand-edit detection collapses, every file
reports as edited, and the protection the engineer relies on becomes noise.

**Four questions.**

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Performance: the budget for a whole-project emission

An Automation Engineer regenerates the suite after a batch of new cases. At full scale
that is roughly 150 spec files, 150 page objects and 6,000 tests.

A) **Under 60 seconds for the whole project, under 5 seconds for one feature.**
Whole-project emission is an occasional operation; per-feature is the one that follows
every batch. **(Recommended — it puts the tight budget on the frequent operation and
leaves room for the rare one, which is the same split U3 used for coverage)**

B) **Under 10 seconds for the whole project.** Ambitious, and reaching it would mean
parallel rendering — which introduces non-deterministic file ordering, the one thing
this unit cannot afford.

C) **No whole-project budget**, per-feature only. Simpler, and it leaves the operation
an engineer runs before a handover unmeasured.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — under 5 s per feature, under 60 s whole-project (accepted via "Accept all recommendations")

## Question 2 — Reliability: how determinism is verified

FR-AUT-11 requires byte-identical regeneration. How is that proven rather than assumed?

A) **Three ways: a property test rendering twice and comparing bytes, an `input_hash`
stored per test so a mismatch is detectable in production, and a benchmark asserting
that a second whole-project emission writes zero files.**
**(Recommended — the property catches it in development, the stored hash catches a
drift that only appears at scale, and the zero-write assertion is the one an operator
can run themselves)**

B) **The property test alone.** Cheapest, and it exercises only the shapes Hypothesis
generates rather than the real corpus.

C) **A golden-file comparison** against committed expected output. Catches everything,
and every legitimate template change requires regenerating hundreds of fixtures — which
in practice means people regenerate them without reading the diff.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — property test, stored `input_hash`, and a zero-write benchmark (accepted via "Accept all recommendations")

## Question 3 — Security: what the credential check looks for

BR-U5-5 refuses an emission carrying a literal secret. What is the pattern set?

A) **Field-name signals plus value shapes**: a field named like a credential
(`password`, `token`, `secret`, `apikey`, `authorization`), a value shaped like a
bearer token, private key block or connection string, and any absolute URL with a host
that is not `localhost` or an example domain.
**(Recommended — field names catch the common case, value shapes catch the one where
the field is called something else, and both are cheap)**

B) **Value shapes only.** Fewer false positives, and it misses `password: "hunter2"` —
which is the most likely literal to appear.

C) **An entropy threshold** on every string. Catches novel formats, and it fires on
hashes, ids and base64 fixtures, which are ordinary test data.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — field-name signals plus value shapes (accepted via "Accept all recommendations")

## Question 4 — Maintainability: where the generated coding standard is asserted

The templates *are* the standard. What stops a template change from quietly degrading
it?

A) **Property tests over rendered output** — no fixed waits, no XPath, no literal
secrets, every test annotated — run against generated content rather than against the
templates. **(Recommended — it asserts the property that matters, which is what comes
out; a template can be rewritten freely as long as the output still holds)**

B) **Lint the templates themselves** for forbidden fragments. Direct, and it checks the
source rather than the result — a fragment assembled from two harmless halves passes.

C) **Run the generated project's own linter** in CI. Most faithful, and it makes the
Python test suite depend on a Node toolchain being installed.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — property tests over rendered output (accepted via "Accept all recommendations")

---

# Execution Checklist

## Phase 1: Assessment

- [x] 1.1 Record what U5 inherits unchanged
- [x] 1.2 Identify which inherited budgets U5 first exercises
- [x] 1.3 Confirm the two shared project NFRs and how U5 serves them

## Phase 2: Requirements

- [x] 2.1 Performance requirements per Question 1
- [x] 2.2 Scalability requirements
- [x] 2.3 Reliability and determinism requirements per Question 2
- [x] 2.4 Security requirements per Question 3
- [x] 2.5 Maintainability requirements per Question 4
- [x] 2.6 Extension compliance: Security, Resiliency, PBT
- [x] 2.7 Write `nfr-requirements.md`

## Phase 3: Tech Stack

- [x] 3.1 Confirm Jinja2 is a declared direct dependency, not a transitive one
- [x] 3.2 Record the pinned `@playwright/test` version the templates emit
- [x] 3.3 Verify no new Python dependency is required
- [x] 3.4 Write `tech-stack-decisions.md`

---

# Mandatory Artifacts

- [x] `.../u5-automation-emission/nfr-requirements/nfr-requirements.md`
- [x] `.../u5-automation-emission/nfr-requirements/tech-stack-decisions.md`
