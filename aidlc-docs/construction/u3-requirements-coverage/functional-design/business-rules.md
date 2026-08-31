# Business Rules — U3 Requirements and Coverage

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U3 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-29

U3 decides what must be tested. Most of the *logic* lives in U1's domain; these rules
govern how the services feed it and what they do with its output.

---

# BR-U3-1: Risk Signal Gathering

BR-4 weights four factors. Three are derivable from stored artefacts; one is not.

## BR-U3-1.1 The three derivable factors

| Factor | Derived from | Scale 1-5 |
|---|---|---|
| Complexity | Count of business rules, conditions and state transitions for the requirement | 0-1 rules → 1; 2-3 → 2; 4-6 → 3; 7-10 → 4; 11+ → 5 |
| Integration surface | Count of endpoints and external dependencies touched | 0 → 1; 1 → 2; 2-3 → 3; 4-6 → 4; 7+ → 5 |
| Change frequency | Commits touching the relevant files in the last 90 days, via A4 | 0 → 1; 1-2 → 2; 3-5 → 3; 6-10 → 4; 11+ → 5 |

## BR-U3-1.2 Business criticality is supplied, not derived

**No artefact states it.** A Jira priority is a scheduling signal, an epic label is a
grouping, and neither says what a defect here would cost.

The agent supplies it with **evidence cited** — the field, label or judgement it rests
on. Where the agent supplies none, the factor is `unavailable` and the rating is
flagged partial.

**Why not default it.** BR-4.4 already handles a missing factor correctly: it leaves
the denominator, preserving the ratio among what is known. Defaulting to "medium"
would make an unassessed requirement indistinguishable from one assessed as moderate —
and the second is a judgement while the first is an absence.

## BR-U3-1.3 Change frequency when history is unavailable

A repository that could not be reached, or a requirement not traceable to a file,
yields `unavailable` — never 0. Zero commits and no commit data are different facts,
and scoring the second as the first would read as "stable" when it means "unknown"
(US-TRQ-02 AC3).

## BR-U3-1.4 Every factor is recorded

`risk_factors` stores each factor with its value or `unavailable`, plus the evidence
for criticality. Two requirements with the same band are then distinguishable by
cause, which matters because a high rating driven by criticality calls for a different
response than one driven by churn (US-TRQ-02 AC4).

---

# BR-U3-2: Testable Requirement Validation

Four checks. A requirement failing any is rejected with the reason.

| # | Check | Rejection |
|---|---|---|
| 1 | States a single expected behaviour | `REJECTED_INVALID_STEPS` |
| 2 | Category is one of the defined set | `REJECTED_INVALID_STEPS` |
| 3 | Cites at least one source artefact | `REJECTED_NO_JIRA_KEY` |
| 4 | Resolves to a Jira key in the ingested set | `REJECTED_NO_JIRA_KEY` or `REJECTED_UNKNOWN_JIRA_KEY` |

## BR-U3-2.1 Atomicity

A statement is non-atomic when it joins two verb phrases with " and " or " or " such
that each half is independently verifiable.

Detection is a heuristic, so a rejection names the suspected split and the agent may
resubmit as two requirements or restate the sentence.

**Atomicity is the one property nothing downstream can recover.** A bundled
requirement produces bundled cases: a case that verifies two behaviours cannot be
traced to either alone, and a coverage report counting it once overstates coverage of
both. Every later stage inherits the error and none can detect it.

## BR-U3-2.2 The heuristic is deliberately conservative

Only " and " / " or " joining two *verb* phrases triggers rejection. "the order total
and tax are recalculated" is one behaviour with a compound subject and passes.

A false rejection costs one resubmission. A false acceptance costs a permanently
untraceable case, so the asymmetry justifies erring toward acceptance and letting
review catch what the heuristic misses.

---

# BR-U3-3: Gap Routing

A behaviour that cannot resolve to a Jira key becomes a gap, never a requirement
(FR-TRC-04).

## BR-U3-3.1 The gap record

| Field | Content |
|---|---|
| `category` | `untraceable-behaviour`, `uncovered-requirement`, `boundaries-undetermined`, `reduced-depth` |
| `subject` | The behaviour or requirement |
| `source_ref` | Where it was found |
| `attempted` | What was tried — direct link, commit derivation with its window |
| `feature_slug` | Where known |
| `detected_at`, `run_id` | |

## BR-U3-3.2 Persisted, not merely reported

A gap held only in a run report is lost when the run ends. The operator's question —
*what is still untraceable?* — arrives weeks later, when the report has scrolled away.

Persisting also lets a gap **close**: when a Jira story is later created covering a
gapped behaviour, the delta run finds it and the behaviour becomes eligible for
requirement derivation (US-TRC-03 AC4). A transient report cannot support that.

## BR-U3-3.3 Gaps are not requirements

They live in their own table. Putting them in `testable_requirement` with a flag would
oblige every downstream query to exclude them, and the first query that forgets would
generate test cases for behaviour that was explicitly ruled untestable.

---

# BR-U3-4: Coverage Model Versioning

## BR-U3-4.1 Version and hash

A version is a **monotonic integer per feature**, incremented only when the content
hash changes. A rebuild producing identical content reuses the version.

An unchanged rebuild must not invalidate an approval. The operator re-running coverage
to check something should not cost the Test Lead a second approval of the same model.

## BR-U3-4.2 What the hash covers

Per coverage item, in id order: item id, requirement id, test type, technique,
planned count, `is_required`.

**Not rationale text.** Rewording a rationale does not change what will be tested, and
requiring re-approval for a typo fix trains the Test Lead to approve without reading —
which defeats the gate more thoroughly than a loose hash ever could.

**`is_required` is in the hash** because a test type flipping from required to
not-required changes coverage materially while leaving the planned total unchanged. A
counts-only hash would miss it.

## BR-U3-4.3 Approval binding

`stage_approve` records the version and the hash. U7's gate compares the recorded hash
against the current one. Any difference in the hashed fields closes the gate with
`content-changed`.

---

# BR-U3-5: Coverage Reduction

## BR-U3-5.1 A recorded decision

The operator names the feature and the reason. The model recomputes with the reduction
applied and stores **both** yields.

Storing both is what lets the gap report state how much coverage was given up. A model
holding only the reduced figure can say a feature is reduced but not by how much, and
"reduced" without a magnitude is not a fact anyone can weigh.

## BR-U3-5.2 High-risk features require an override

A feature rated `high` or `critical` requires `override=true`. The contradiction
between the rating and the decision is recorded with the actor and reason
(US-COV-05 AC3).

Not forbidden — a Test Lead may have context the rating lacks. But it must be
deliberate, and the disagreement must be visible afterwards.

## BR-U3-5.3 Reduction invalidates approval

It changes the content hash, so any prior approval no longer applies. Correct and
automatic: the Test Lead approved the fuller model, not this one.

## BR-U3-5.4 Every reduction is a gap

Recorded with category `reduced-depth`. Reduced coverage is a gap that was chosen
rather than missed, and the gap report should not distinguish them by omission
(US-COV-05 AC4).

---

# BR-U3-6: Batch Semantics

## BR-U3-6.1 All-or-nothing per feature

A requirement batch for one feature is accepted entirely or not at all, with every
failure reported together — the same shape as `testcases_upsert`.

**A half-populated requirement set is the dangerous outcome.** The coverage model
built from it would be missing items nobody knows are missing, and the Test Lead would
approve a baseline that silently omits them. Unlike a rejected batch, which is
obviously incomplete, a partially accepted one looks finished.

## BR-U3-6.2 Every failure at once

At batch sizes of twenty or more, failing on the first fault forces as many correction
rounds as there are faults.

---

# BR-U3-7: Commit-Derived Key Resolution

## BR-U3-7.1 The sequence

1. Direct story link from the agent's payload, if present
2. Otherwise, commit derivation via D3 using history from A4
3. Otherwise, a gap

## BR-U3-7.2 Which files

The requirement's `source_artefact_ids` are resolved to artefacts; those of kind
`source-file` or `endpoint` yield file paths. A requirement citing only Jira artefacts
has no file to derive from, so it goes straight to a gap if it has no direct link.

## BR-U3-7.3 History is fetched once per file, per run

Commit history is requested from A4 once per distinct file path and reused across
requirements. At 500 requirements over 50 files, per-requirement fetching would make
490 redundant calls.

## BR-U3-7.4 Derived links are marked and counted separately

`link_type = derived-from-commit`, with the selection basis and alternatives retained.
Coverage reporting counts them apart from direct links (BR-3.6): provenance is weaker
evidence than specification and must not be presented as equivalent.

---

# Rule-to-Requirement Traceability

| Rule | Requirements | Stories |
|---|---|---|
| BR-U3-1 Risk signals | FR-TRQ-03 | US-TRQ-02 |
| BR-U3-2 Requirement validation | FR-TRQ-01, FR-TRQ-02, FR-TRQ-04 | US-TRQ-01 |
| BR-U3-3 Gap routing | FR-TRC-04, FR-COV-05, FR-TRQ-05 | US-TRC-03, US-TRQ-03 |
| BR-U3-4 Model versioning | FR-COV-01, FR-COV-06 | US-COV-01, US-COV-04 |
| BR-U3-5 Reduction | FR-COV-07 | US-COV-05 |
| BR-U3-6 Batch semantics | FR-TRQ-01 | US-TRQ-01 |
| BR-U3-7 Commit derivation | FR-TRC-02, FR-TRC-03 | US-TRC-02 |
| (U1 D2, orchestrated here) | FR-COV-02, FR-COV-03, FR-COV-04 | US-COV-01 to US-COV-03 |
