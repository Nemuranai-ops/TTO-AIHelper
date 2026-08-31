# NFR Requirements Plan — U3 Requirements and Coverage

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U3 | **Stage**: NFR Requirements
**Created**: 2026-08-30T09:01:00Z
**Status**: APPROVED 2026-08-30T09:15:00Z - all recommendations accepted

---

## What U3 inherits

Everything U1 settled, plus U2's ingestion scale figures. None is re-opened.

**U3 owns no project NFR outright.** It is the first unit for which that is true —
U7 owned two usability requirements, U2 owned scale and caching. U3's requirements are
all unit-level, which is a consequence of it being pure orchestration over logic that
already exists.

**Where U3 does introduce risk is volume.** At the upper end of NFR-SCL-01 — 500
stories — requirement derivation could produce 500-1500 testable requirements, and
D2 generates a coverage item per test type per requirement. Nine test types means the
`coverage_item` table reaches five figures before a single test case exists. That is
the subject of Questions 1 and 2.

**Four questions.**

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Scalability: coverage items at full volume

D2 creates one `coverage_item` per test type per requirement, including
`is_required=false` rows. At 1,500 requirements and 9 test types that is **13,500
rows**, most of them not-required.

A) **Accept the volume; it is the price of BR-2.6.** Not-required rows exist so a
deliberate exclusion stays distinguishable from an oversight, and dropping them to
save rows would discard exactly that. Index `coverage_item(requirement_id)` and
`(is_required)`, and let reports aggregate in SQL. **(Recommended — 13,500 rows is
small for SQLite, and the alternative trades a real property for an imagined problem)**

B) **Store only required items**, and infer exclusions from absence. Fewer rows, and
BR-2.6 is lost: an absent row and a deliberate exclusion become identical again.

C) **Store not-required rows in a separate table.** Keeps the main table small, and
splits one concept across two places for a saving nothing needs.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 2 — Performance: coverage build budget

Building the model for one feature means loading its requirements, deriving items,
hashing, and forecasting.

A) **Under 5 seconds per feature at 100 requirements; under 60 seconds for a
whole-project rebuild at 1,500.** Measured by a benchmark alongside U1's.
**(Recommended — a per-feature build happens interactively while the operator waits,
so seconds matter; a whole-project rebuild is rare and a minute is tolerable)**

B) **Under 1 second per feature** — tighter, and it would push the design toward
caching the derivation, which is the kind of complexity U1 declined for good reason.

C) **No stated budget** — measure if it becomes a problem.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 3 — Performance: the commit index

`CommitIndex` fetches history once per distinct file per run. At 50 files with 180
days of history, that is 50 calls and potentially thousands of commit records held in
memory for the duration of the run.

A) **Bound it: cap at 200 distinct files per run and 500 commits per file, reporting
when either is hit.** Beyond that, key derivation for the remaining files is skipped
and those behaviours route to gaps with the reason stated. **(Recommended — an
unbounded index on a large monorepo would hold the whole history in memory, and a gap
that says "commit index limit reached" is honest where a silent slowdown is not)**

B) **Unbounded.** Simplest, and it fails on the repository most in need of the feature.

C) **Fetch per requirement, no index.** Bounded memory, 490 redundant calls at the
volumes BR-U3-7.3 describes.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 4 — Maintainability: the atomicity heuristic

BR-U3-2.1 rejects a requirement when " and " or " or " joins two verb phrases. The
heuristic will be wrong sometimes.

A) **Ship it with a documented escape: a `force_atomic=true` flag on the payload that
records the override and its actor.** The agent uses it when the heuristic is wrong,
and the overrides are reviewable — if they cluster, the heuristic needs work.
**(Recommended — a heuristic with no escape becomes a wall, and one with an
unrecorded escape becomes a habit)**

B) **No escape.** The agent must restate the requirement. Cleanest, and it blocks
legitimate wording the heuristic cannot parse.

C) **Advisory only** — warn but accept. No wall, and no enforcement either.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

# Execution Checklist

## Phase 1: NFR Determination

- [x] 1.1 Record scalability requirements: coverage item volume, gap table growth
- [x] 1.2 Record performance requirements: build budget, hashing, commit index
- [x] 1.3 Record reliability requirements: batch atomicity, approval invalidation
- [x] 1.4 Record security requirements specific to U3
- [x] 1.5 Record maintainability requirements: the atomicity escape and its review
- [x] 1.6 Confirm every inherited decision applies unchanged
- [x] 1.7 Write `nfr-requirements.md`

## Phase 2: Tech Stack

- [x] 2.1 Confirm the U1 stack applies with no addition
- [x] 2.2 Record the hashing approach for coverage content
- [x] 2.3 Write `tech-stack-decisions.md`

## Phase 3: Validation

- [x] 3.1 Verify every U3 NFR requirement is measurable
- [x] 3.2 Verify no inherited decision is silently re-opened
- [x] 3.3 Verify Security and Resiliency applicability
- [x] 3.4 Validate content per `common/content-validation.md`
- [x] 3.5 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `.../u3-requirements-coverage/nfr-requirements/nfr-requirements.md`
- [x] `.../u3-requirements-coverage/nfr-requirements/tech-stack-decisions.md`
