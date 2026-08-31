# Functional Design Plan — U8 Reporting and Re-baselining

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U8 | **Stage**: Functional Design
**Created**: 2026-08-31T09:05:00Z
**Status**: APPROVED 2026-08-31 — all recommendations accepted

---

## Unit Context

**Responsibility**: turn the corpus into defensible reports, and keep it current as the
application moves.

**Boundary**: U8 reads the corpus and detects change. **It creates no requirement and
no case** — a delta run re-enters the pipeline at U3 for the affected scope.

**Components** (3): S8 ReportingService, S9 DeltaService, A9 ReportEmitter.

**Stories** (6): US-RPT-01 to -03, US-DLT-01 to -03.

**Depends on**: U1, U2, U4 — all complete. Also reads U3's coverage, U5's automation
and U6's manifest.

---

## The last unit, and what it inherits

Almost everything U8 needs already exists. **D8 `impact.py` is complete** — U1 built
`classify_edge` and `map_impact`, including the rule that a change touching nothing
traceable is reported as *unmapped* rather than assumed harmless. `change_event` and
`run` are in migration 001. U4 writes gaps; U5 writes automation rows; U3 writes
coverage.

U8's work is to **feed D8 the edges** and to render what the corpus already knows.

| Already built | Built by |
|---|---|
| Impact classification and mapping | U1, `domain/impact.py` |
| `change_event`, `run`, `gap`, `coverage_item` | U1, U3 |
| `mark_obsolete` on the case repository | U1 |
| Coverage, volume and automation aggregations | U3, U4, U5 |

**Four questions.**

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Business Rules: what a report does when a section cannot be computed

A coverage report needs an approved model; an automation report needs U5 to have run.
On a partial corpus, some sections have no data.

A) **Render every section that can be computed, and render the others as an explicit
"not available" with the reason and the stage that would produce it.**
**(Recommended — this is U6's degrade-and-report pattern applied to reports, and the
same argument holds: a report that fails whole because one section is empty is a
report the Test Lead cannot use to see how far the baseline has got)**

B) **Refuse to render an incomplete report.** Consistent, and it makes the reports
useless during the period they would be most useful — while the baseline is being
built.

C) **Omit empty sections silently.** Clean output, and a missing section is then
indistinguishable from a section with nothing in it, which is the difference that
matters.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — render what can be computed; mark the rest `not_available` with a reason and the producing stage (accepted via "Accept all recommendations")

## Question 2 — Data Model: how the delta baseline is recorded

FR-DLT-01 compares a recorded head commit against the current head; FR-DLT-02 uses a
Jira `updated` timestamp.

A) **On the `run` row. A completed run records, per repository, the head commit it saw,
and the ISO timestamp of the latest Jira update it ingested. The next delta run reads
the most recent completed run of either kind.**
**(Recommended — the baseline is a property of a run, `run` already exists with
`ended_at` to mark completion, and reading "the last completed run" is one query with
no separate state to fall out of step)**

B) **A dedicated `delta_baseline` table.** Explicit, and it introduces a second record
of when the system last looked at something, which can disagree with `run`.

C) **Derive it from `artefact.last_ingested_at`.** No new storage, and it answers
"when did we last fetch this artefact", not "what was the repository head when the run
completed" — which is the question `bitbucket_changes` actually needs.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — on the `run` row: `head_commits` per repository and a `jira_watermark` (accepted via "Accept all recommendations")

## Question 3 — Business Rules: what a delta run does with its findings

FR-DLT-04 classifies each affected case; FR-DLT-05 forbids silent deletion.

A) **Classify, record, retire the obsolete, and stop. Cases classified
`requires-update` are reported and left untouched; the operator re-runs U3 and U4 for
the affected scope through the normal gates.**
**(Recommended — U8's boundary says it creates no requirement and no case, and a delta
run that regenerated would bypass every gate the baseline had to pass)**

B) **Classify and regenerate automatically** for `requires-update`. Fewer steps, and
FR-DLT-06 requires delta runs to face the same human gates as the baseline.

C) **Classify and report only**, retiring nothing. Safest, and obsolete cases then
accumulate in the corpus and in every subsequent coverage report.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — classify, record, retire the obsolete, report `requires-update` untouched (accepted via "Accept all recommendations")

## Question 4 — Business Rules: what "retire" means

FR-DLT-05: never silently delete.

A) **Set `is_obsolete`, record the reason and the `change_event` that caused it, and
leave every row in place — steps, data, links and the automated test. The case stops
appearing in coverage counts and in generated views; it remains fully readable.**
**(Recommended — U1 built `mark_obsolete` with exactly these columns, and D5's
identifier rule already forbids an obsolete case's number being reissued; retiring is
the last piece that makes those two decisions pay off)**

B) **Move retired cases to an archive table.** Keeps the working set small, and it
splits the corpus in two so every query and every report must remember to check both.

C) **Mark obsolete and delete the automated test.** Tidier project, and the engineer
loses a spec they may have hand-edited — and U5's protection would not have applied,
because U8 deleted it.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — mark obsolete with the reason and the change event; delete nothing (accepted via "Accept all recommendations")

---

# Execution Checklist

## Phase 1: Domain Entities

- [x] 1.1 Define the report types and their sections
- [x] 1.2 Specify the delta baseline per Question 2
- [x] 1.3 Specify what retirement writes per Question 4
- [x] 1.4 Confirm D8's existing types are used unchanged
- [x] 1.5 Verify no U8 entity duplicates one another unit owns
- [x] 1.6 Write `domain-entities.md`

## Phase 2: Business Rules

- [x] 2.1 BR-U8-1 the four reports and what each states
- [x] 2.2 BR-U8-2 sections that cannot be computed (Question 1)
- [x] 2.3 BR-U8-3 reports are generated from SQLite, never assembled by the model
- [x] 2.4 BR-U8-4 the delta baseline (Question 2)
- [x] 2.5 BR-U8-5 change detection and the unmapped rule
- [x] 2.6 BR-U8-6 impact classification — delegated to D8
- [x] 2.7 BR-U8-7 retirement (Question 4) and the boundary (Question 3)
- [x] 2.8 BR-U8-8 run history and traceability of a case to its run
- [x] 2.9 Rule-to-requirement traceability
- [x] 2.10 Write `business-rules.md`

## Phase 3: Business Logic Model

- [x] 3.1 The reporting sequence
- [x] 3.2 The delta sequence, stage by stage
- [x] 3.3 Edge construction: how the traceability graph becomes `TraceEdge`s
- [x] 3.4 Retirement and what it does not touch
- [x] 3.5 Interaction with U1 through U6
- [x] 3.6 The property surface
- [x] 3.7 Story coverage
- [x] 3.8 Write `business-logic-model.md`

## Phase 4: Validation

- [x] 4.1 Verify all 6 U8 stories are covered by a rule
- [x] 4.2 Verify U8 holds no copy of D8's classification logic
- [x] 4.3 Verify Security and Resiliency compliance at design level
- [x] 4.4 Validate content per `common/content-validation.md`
- [x] 4.5 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `.../u8-reporting-rebaselining/functional-design/domain-entities.md`
- [x] `.../u8-reporting-rebaselining/functional-design/business-rules.md`
- [x] `.../u8-reporting-rebaselining/functional-design/business-logic-model.md`
