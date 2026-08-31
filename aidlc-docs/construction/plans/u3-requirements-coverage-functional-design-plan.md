# Functional Design Plan — U3 Requirements and Coverage

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U3 | **Stage**: Functional Design
**Created**: 2026-08-29T19:41:00Z
**Status**: APPROVED 2026-08-29T19:55:00Z - all recommendations accepted

---

## Unit Context

**Responsibility**: decide *what must be tested*. U3 derives atomic testable
requirements and builds the coverage baseline that gates everything downstream.

**Components**: S3 TestableRequirementService, S4 CoverageService.

**Stories** (10): US-TRQ-01 to US-TRQ-03, US-COV-01 to US-COV-05, US-TRC-02,
US-TRC-03. The largest unit in the project by story count.

**Depends on**: U1, U7, U2 — all complete.

---

## What is already built

Unusually for a unit this size, most of U3's *logic* already exists. U1 built the
domain; U3 builds the services that orchestrate it.

| Already in U1 | What U3 adds |
|---|---|
| D2 CoverageModeller — ISTQB depth, yield, reduction | The service that feeds it and stores its output |
| D3 TraceabilityResolver — Jira key rules, commit derivation | The service that supplies commit records and routes gaps |
| D6 Classifier — risk weights, bands, partial ratings | The service that gathers the four risk signals |
| D7 IntegrityValidator | Requirement-level validation |
| L5 GateEvaluator (U7) | The approval that opens the gate |
| A4 BitbucketSourceAdapter (U2) | Supplies commit history for BR-3 |

**This unit is where the coverage baseline gate becomes real.** FR-COV-06 is the only
approval restricted to a single role, and US-COV-04 AC3 requires that modifying an
approved model invalidates the approval. U7 built the mechanism; U3 supplies the
content it binds to.

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Business Rules: where risk signals come from

BR-4 weights four factors. Three are derivable; one is not.

| Factor | Source |
|---|---|
| Complexity | Count of rules, conditions and transitions — **derivable** |
| Integration surface | Count of endpoints and external dependencies — **derivable** |
| Change frequency | Commits touching the files in 90 days — **derivable via A4** |
| **Business criticality** | **Not derivable from any artefact** |

A) **Derive the three, and take criticality from the agent's payload with its
evidence cited** — a Jira priority field, an epic label, or a stated judgement. Where
the agent supplies none, the factor is `unavailable` and the rating is flagged
partial. **(Recommended — BR-4.4 already handles a missing factor correctly, so the
honest path is to let it be missing rather than inventing a proxy)**

B) **Derive criticality from Jira priority alone**, defaulting to medium when absent.
Fully automatic, and "medium" would then be indistinguishable from "unknown".

C) **Require the operator to set criticality per feature** before requirements can be
derived. Most accurate, and it blocks the pipeline on a manual step per feature.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 2 — Business Rules: what the coverage approval hash covers

US-COV-04 AC3 requires that modifying an approved model invalidates its approval. The
hash decides what counts as a modification.

A) **The coverage items' identity and substance**: item id, requirement id, test type,
technique, planned count, and `is_required`. Not rationale text. **(Recommended —
rewording a rationale does not change what will be tested, and re-approval for a typo
fix would train the Test Lead to approve without reading)**

B) **Everything, including rationale text.** Strictest, and it fires on cosmetic edits.

C) **Planned counts only.** Cheapest, and a test type silently switching from required
to not-required would keep its approval.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 3 — Business Rules: coverage model versioning

A model version identifies what was approved. When does it change?

A) **A monotonic integer per feature, incremented whenever the content hash changes.**
Approval records the version and the hash; a later build that produces identical
content reuses the version. **(Recommended — an unchanged rebuild should not
invalidate an approval, and the hash is what tells us it is unchanged)**

B) **A new version on every build**, whether or not content changed. Simple, and every
rebuild forces re-approval.

C) **A timestamp rather than an integer.** Equivalent, and harder to read in a report.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 4 — Business Rules: what a testable requirement must satisfy

FR-TRQ-01 requires atomic, independently verifiable statements. What does S3 enforce?

A) **Four checks**: a single expected behaviour (rejected if it contains " and " or
" or " joining two verbs), a category from the defined set, at least one source
artefact, and a resolvable Jira key. Anything failing is rejected with the reason.
**(Recommended — atomicity is the one property nothing downstream can recover if it
is wrong: a bundled requirement produces bundled cases that cannot be individually
traced)**

B) **Traceability only.** Trust the agent on atomicity.

C) **Traceability plus category**, with atomicity advisory.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 5 — Business Rules: routing a behaviour to the gap set

BR-3.4 and FR-TRC-04 send untraceable behaviour to the gap report rather than the
corpus. Where does the gap set live?

A) **A `gap` table, written by S3, holding the behaviour, its source, what was
attempted, and the category.** Queryable, survives the run, and feeds U8's gap report
directly. **(Recommended — a gap held only in a run report is lost the moment the run
ends, and the operator's question "what is still untraceable?" arrives weeks later)**

B) **In the ingestion or analysis report only**, not persisted.

C) **As a `testable_requirement` row flagged `is_gap`.** Avoids a table, and it puts
non-requirements in the requirements table where every downstream query must exclude
them.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 6 — Business Rules: applying a coverage reduction

FR-COV-07 lets the Test Lead mark a feature reduced-depth. US-COV-05 AC3 requires an
explicit override when the feature is high-risk.

A) **Reduction is a recorded decision, not a recomputation.** The operator names the
feature and the reason; the model recomputes with the reduction applied, stores both
the full and reduced yields, and invalidates any prior approval. A high-risk feature
requires `override=true`, and the contradiction between the rating and the decision is
recorded. **(Recommended — storing both yields is what makes the gap report able to
say how much coverage was given up)**

B) **Reduction rewrites the model in place**, keeping only the reduced yield.

C) **Reduction is a report-time filter** that does not change the stored model.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 7 — Error Handling: partial requirement batches

The agent submits requirements for a feature. Some are valid, some are not.

A) **All-or-nothing per feature, reporting every failure at once** — the same shape as
`testcases_upsert`. **(Recommended — a half-populated requirement set produces a
coverage model missing items nobody knows are missing, and the operator would approve
a baseline that silently omits them)**

B) **Accept the valid ones and report the rest**, so progress is not lost.

C) **Stop at the first failure.**

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

# Execution Checklist

## Phase 1: Business Rules

- [x] 1.1 Specify risk signal gathering per Question 1
- [x] 1.2 Specify the approval hash per Question 2
- [x] 1.3 Specify model versioning per Question 3
- [x] 1.4 Specify requirement validation per Question 4
- [x] 1.5 Specify gap routing per Question 5
- [x] 1.6 Specify reduction per Question 6
- [x] 1.7 Specify batch semantics per Question 7
- [x] 1.8 Specify commit-derived key resolution using U2's A4
- [x] 1.9 Write `business-rules.md`

## Phase 2: Domain Entities

- [x] 2.1 Define the `gap` entity and its migration
- [x] 2.2 Define the coverage model version record
- [x] 2.3 Define the reduction decision record
- [x] 2.4 Define the agent payload contracts for requirements and edge cases
- [x] 2.5 Write `domain-entities.md`

## Phase 3: Business Logic Model

- [x] 3.1 Model requirement derivation and validation
- [x] 3.2 Model risk signal gathering across three sources
- [x] 3.3 Model coverage build, yield forecast and approval binding
- [x] 3.4 Model gap routing
- [x] 3.5 Model the interaction with U1's domain, U2's adapter and U7's gate
- [x] 3.6 Identify the U3 property surface
- [x] 3.7 Write `business-logic-model.md`

## Phase 4: Validation

- [x] 4.1 Verify all 10 U3 stories are served
- [x] 4.2 Verify FR-TRQ-01 to -05, FR-COV-01 to -07, FR-TRC-02 to -04 are covered
- [x] 4.3 Verify the Test Lead restriction is preserved
- [x] 4.4 Verify Security and Resiliency applicability
- [x] 4.5 Validate content per `common/content-validation.md`
- [x] 4.6 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `.../u3-requirements-coverage/functional-design/domain-entities.md`
- [x] `.../u3-requirements-coverage/functional-design/business-rules.md`
- [x] `.../u3-requirements-coverage/functional-design/business-logic-model.md`

**No `frontend-components.md`**: U3 has no user interface. The operator reaches these
stages through U7's `requirements` and `coverage` chat modes.
