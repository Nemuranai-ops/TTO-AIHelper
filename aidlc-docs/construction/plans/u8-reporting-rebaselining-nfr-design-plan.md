# NFR Design Plan — U8 Reporting and Re-baselining

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U8 | **Stage**: NFR Design
**Created**: 2026-08-31T09:44:00Z
**Status**: APPROVED 2026-08-31 — all recommendations accepted

---

## What U8 inherits

49 patterns across seven units. U8 is the last, and it adds the fewest — which is the
right shape for a unit that reads what seven others wrote.

| Inherited | Use in U8 |
|---|---|
| P-U6-03 Degrade and report | Every uncomputable section; its third use |
| P-RES-03 Isolate per source | Bitbucket and Jira detected independently |
| P-U5-03 Deterministic rendering | Reports are committed and diffed |
| P-U4-04 Three-outcome emission | The shape `not_available` follows |
| P-SEC-03 Message sanitisation | Report content before it is written |
| P-U7-02 Read-only gate evaluation | Before a delta run — FR-DLT-06 |
| P-MNT-02 Import contracts | Enforce that U8 holds no classification logic |

**Three questions.**

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Reliability: how the baseline-advance guard is shaped

U8-NFR-REL-04 is the requirement whose violation would be permanent and silent.

A) **The baseline is advanced by a single function that takes the detection result and
refuses unless every source reported success. The delta service never writes
`head_commits` or `jira_watermark` directly, and a property test asserts the refusal
across every combination of source outcomes.**
**(Recommended — one place to get it right, and a property rather than an example,
because the failure is invisible and would not surface in any later test)**

B) **A conditional at the end of the delta run.** Direct, and it is one `if` that a
later refactor can move, invert, or lose in a branch.

C) **Advance in the repository layer** when the run completes. Symmetric with how the
run row is written, and it puts a correctness rule where nothing about the detection
result is visible.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — a single guarded `advance_baseline` function, with a property over every combination of source outcomes (accepted via "Accept all recommendations")

## Question 2 — Maintainability: how report sections are composed

Four reports, roughly a dozen sections between them, each with a precondition, a query
and a renderer.

A) **A declarative section registry: name, precondition, query, producing stage. The
service iterates it; adding a section is adding a row.**
**(Recommended — it makes "every section has a precondition and a producing stage" a
structural fact rather than a convention, which is what U8-NFR-REL-02 needs; and the
property test can then enumerate the registry rather than trusting a list someone
maintained by hand)**

B) **A method per section.** Familiar, and each new section is a new opportunity to
forget the `not_available` path.

C) **A base class with subclasses per section.** Extensible, and it is twelve files for
what is a name, a callable and two strings.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — a declarative section registry the property test enumerates (accepted via "Accept all recommendations")

## Question 3 — Logical Components: what U8 needs

A) **Two: `ReportRenderer`** (Markdown and CSV, deterministic, derivation strings) and
**`ChangeDetector`** (per-source detection under isolation, returning what succeeded and
what did not). **(Recommended — the renderer holds format decisions and byte-stability;
the detector holds the per-source outcome that Question 1's guard depends on, and
keeping them separate is what lets the guard be tested without a network)**

B) **One** — the renderer only, with detection inline in S9.

C) **Three** — add an `EdgeBuilder`, though building `TraceEdge`s is a query and four
boolean lookups that S9 already has the repositories for.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — two components: L16 ReportRenderer, L17 ChangeDetector (accepted via "Accept all recommendations")

---

# Execution Checklist

## Phase 1: Pattern Selection

- [x] 1.1 Record which inherited patterns U8 uses
- [x] 1.2 Specify the baseline guard pattern per Question 1
- [x] 1.3 Specify the section registry pattern per Question 2
- [x] 1.4 Specify the derivation-carrying pattern
- [x] 1.5 Record patterns considered and declined
- [x] 1.6 Map every pattern to the U8 NFR it delivers
- [x] 1.7 Write `nfr-design-patterns.md`

## Phase 2: Logical Components

- [x] 2.1 Define the components chosen in Question 3
- [x] 2.2 Define responsibilities, interfaces and the pattern set
- [x] 2.3 Place them within the hexagonal rings
- [x] 2.4 Define configuration additions
- [x] 2.5 Verify no new component violates the dependency rule
- [x] 2.6 Write `logical-components.md`

## Phase 3: Validation

- [x] 3.1 Verify all 28 U8 NFR requirements have a delivering pattern or component
- [x] 3.2 Verify U8 holds no copy of D8's classification logic
- [x] 3.3 Verify Security and Resiliency compliance at design level
- [x] 3.4 Validate content per `common/content-validation.md`
- [x] 3.5 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `.../u8-reporting-rebaselining/nfr-design/nfr-design-patterns.md`
- [x] `.../u8-reporting-rebaselining/nfr-design/logical-components.md`
