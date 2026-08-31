# NFR Design Plan — U4 Test Case Generation

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U4 | **Stage**: NFR Design
**Created**: 2026-08-30T12:26:00Z
**Status**: COMPLETE — all recommendations accepted 2026-08-30

---

## What U4 inherits

35 patterns across four units. U4 uses more of them than any unit so far and adds few,
because its job is sequencing.

| Inherited | Use in U4 |
|---|---|
| P-RES-01 Unit of Work | The batch transaction, and the strictest use of it in the system |
| P-PRF-01 Bucketed candidate selection | Finally exercised on generated data |
| P-SCL-01 Capped pagination | Case queries |
| P-SEC-01 Two-level validation | Pydantic, then D7 |
| P-U3-02 Informational result field | The planned-vs-generated variance |
| P-U7-02 Read-only gate evaluation | Before the batch |

**Three questions.**

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Reliability: where the personal-data check sits

U4-NFR-SEC-01 rejects test data matching a personal-data pattern.

A) **In the domain, as a pure function, called from D7's validation stage B.** It
becomes one more structural check alongside "has steps" and "has an equivalence
class", running before any database lookup. **(Recommended — the check is a property
of the case, not of the corpus, and putting it in the domain makes it property-testable
against generated values without a database)**

B) **In the service**, after construction. Simpler to wire, and it separates one
validation rule from the nine beside it.

C) **In the MCP boundary schema**, as a Pydantic validator. Earliest possible
rejection, and Pydantic would then own a domain rule.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — domain pure function, called from D7 validation stage B (accepted via "Accept all recommendations")

## Question 2 — Performance: how the batch commits

A 200-case batch is roughly 1,600 inserts inside one transaction.

A) **`executemany` per table, ordered so foreign keys are satisfied, with the
integrity sentinel last.** One transaction, five statements, no per-row Python
round-trip. **(Recommended — `executemany` is where SQLite's insert performance
actually lives, and the ordering constraint is what makes it safe)**

B) **Per-row `execute` in a loop.** Simplest, and it pays Python overhead 1,600 times.

C) **Batched `executemany` in chunks of 50**, committing between chunks. Faster
failure recovery, and it abandons the all-or-nothing guarantee.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — `executemany` per table, foreign-key ordered, integrity sentinel last (accepted via "Accept all recommendations")

## Question 3 — Logical Components: what U4 needs

A) **Two: a `PersonalDataDetector`** (pure, five patterns plus the synthetic
allow-list) and a **`ViewRenderer`** (deterministic Markdown and YAML, hand-edit
detection). **(Recommended — the detector holds the pattern set and the allow-list,
which is policy; the renderer holds format decisions and the emitted-hash comparison,
which is state)**

B) **One** — the renderer only, with detection as a function in the domain.

C) **Three** — add a `BatchValidator`, though the sequencing already lives in S5 and
the checks already live in D7.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — two components: L9 `PersonalDataDetector`, L10 `ViewRenderer` (accepted via "Accept all recommendations")

---

# Execution Checklist

## Phase 1: Pattern Selection

- [x] 1.1 Record which inherited patterns U4 uses
- [x] 1.2 Specify the validation-stage placement per Question 1
- [x] 1.3 Specify the bulk-insert pattern per Question 2
- [x] 1.4 Specify the deferred-allocation pattern
- [x] 1.5 Specify the three-outcome emission pattern
- [x] 1.6 Record patterns considered and declined
- [x] 1.7 Map every pattern to the U4 NFR it delivers
- [x] 1.8 Write `nfr-design-patterns.md`

## Phase 2: Logical Components

- [x] 2.1 Define the components chosen in Question 3
- [x] 2.2 Define responsibilities, interfaces and the pattern set
- [x] 2.3 Place them within the hexagonal rings
- [x] 2.4 Define configuration additions
- [x] 2.5 Verify no new component violates the dependency rule
- [x] 2.6 Write `logical-components.md`

## Phase 3: Validation

- [x] 3.1 Verify all 25 U4 NFR requirements have a delivering pattern or component
- [x] 3.2 Verify U4 holds no copy of a domain algorithm
- [x] 3.3 Verify Security and Resiliency compliance at design level
- [x] 3.4 Validate content per `common/content-validation.md`
- [x] 3.5 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `.../u4-test-case-generation/nfr-design/nfr-design-patterns.md`
- [x] `.../u4-test-case-generation/nfr-design/logical-components.md`
