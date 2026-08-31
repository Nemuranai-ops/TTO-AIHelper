# Business Rules — U4 Test Case Generation

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U4 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-30

U4 produces the corpus. Every rule that makes it trustworthy already exists in U1;
these rules govern the sequence in which they run and what the service does around
them.

---

# BR-U4-1: The Case Payload Contract

## BR-U4-1.1 What the agent supplies

| Field | Notes |
|---|---|
| `coverage_item_id` | Which planned item this case satisfies |
| `title` | |
| `test_type` | Must match the coverage item's type |
| `priority` | |
| `preconditions` | May be empty |
| `steps` | Ordered, each with an action and an expected result |
| `test_data` | Each with a field, value and equivalence class |
| `tags` | Suite, type, feature, priority |
| `trace_links` | At least one resolving to a Jira key |
| Four judgement signals | Visual, external step, unprovisionable data, exploratory |

## BR-U4-1.2 What S5 derives

| Field | Derived from |
|---|---|
| `id` | D5, per BR-6 |
| `normalised_hash` | D4 |
| `bucket_key` | D4 |
| `automatability` and its reason | D6, from derived plus supplied signals |

**The agent supplies meaning; the toolchain supplies identity and classification.**
A case whose identifier the agent chose is one it can reuse, collide or reformat, and
6,000 cases cannot be reconciled after that.

## BR-U4-1.3 The test type must match its coverage item

A case claiming to satisfy a `boundary` item must be a `boundary` case. A mismatch is
rejected with `REJECTED_INVALID_STEPS`.

Without this, the generated-against-planned figures in BR-U4-7 would be meaningless:
five cases could satisfy one item while another went uncovered, and the totals would
still balance.

---

# BR-U4-2: Automatability Signals

## BR-U4-2.1 Derived from the models

| Signal | Source |
|---|---|
| `is_api_case` | The coverage item's test type is `api-contract` |
| `api_shape_source` | The endpoint's `shape_source`, via the requirement's feature |
| `is_ui_case` | Test type is `ui-behaviour` |
| `all_elements_have_locators` | Every referenced screen element has a non-empty locator chain |
| `all_locators_verified` | Every referenced element has `is_verified = true` |
| `has_fragile_locator_without_alternative` | Any element has `is_fragile` and a chain of length 1 |

## BR-U4-2.2 Supplied by the agent, defaulting to false

`requires_visual_judgement`, `requires_external_step`,
`requires_unprovisionable_data`, `is_exploratory`.

**Defaulting to false is safe in one direction only, and that is the safe one.** A
case the agent says nothing about is judged on its derivable signals, landing it in
rules 5-10 — `automatable` or `needs-review`. It can never land in `manual-only`
through omission, which is the outcome that would quietly remove a case from
automation without anyone deciding to.

The reverse default would be unsafe: an unmarked case silently excluded from
automation is a coverage loss nobody sees.

## BR-U4-2.3 Ordered evaluation is D6's

S5 gathers signals; D6 applies the ten-rule list. The verdict cites its rule number,
so every classification traces to the rule that produced it.

---

# BR-U4-3: Batch Limits

## BR-U4-3.1 200 cases per batch

A larger batch is refused with the count and guidance to split it. The cap is
configurable.

**A 500-case batch that fails on case 499 wastes the whole thing.** All-or-nothing is
what makes a partial corpus impossible, and it is also what makes a large batch
expensive to get wrong. 200 is already more than a reviewer reads in one sitting, so
the cap costs nothing the operator wanted.

## BR-U4-3.2 A feature spans several batches

Each batch is independently atomic. A feature with 600 planned cases takes three
calls, and a failure in the second leaves the first committed.

That is correct: the batches are separate units of work, and the coverage report shows
generated against planned so a partial feature is visible rather than assumed
complete.

---

# BR-U4-4: Duplicate Detection Scope

## BR-U4-4.1 The bucket, excluding obsolete

Candidates come from `idx_case_bucket` where `is_obsolete = 0`.

**Obsolete cases are excluded deliberately.** A delta run that retires a case and then
regenerates a replacement would otherwise find the retired case blocking its own
replacement — the corpus would be unable to recover from a retirement.

## BR-U4-4.2 Intra-batch as well as corpus

Two identical cases arriving in the same payload must not both be accepted. Checked
against the corpus bucket and against cases already accepted in this batch.

## BR-U4-4.3 A rejection names the existing case

The report gives the existing case id and the similarity score, so a reviewer can see
what it matched rather than being told only that it matched.

## BR-U4-4.4 Rejections are recorded as gaps

Category `rejected-duplicate`, which migration 004 already permits. A suppressed case
is never invisible (US-TCG-03 AC5).

---

# BR-U4-5: View Emission

## BR-U4-5.1 One Markdown and one YAML per feature

`generated/views/<feature>.md` and `<feature>.yaml`. Deterministic ordering by case
id, so re-emission of unchanged content produces an identical file.

## BR-U4-5.2 Hand-edits are skipped, not overwritten

The content hash of each emitted file is stored. On re-emission, a file whose current
hash differs from the stored one is **reported and skipped**.

**Reporting after overwriting arrives too late.** Skipping means an edit is never
silently lost, and the corpus is unaffected either way because these are views, not
the record. The operator resolves it — usually by discarding the edit, having been
reminded that the corpus is elsewhere.

## BR-U4-5.3 The views say they are views

Each file carries a header stating that it is generated, that edits do not change the
corpus, and which tool does.

---

# BR-U4-6: The Traceability Matrix

## BR-U4-6.1 Built on demand, never stored

From `trace_link` at request time.

**A stored matrix is a second copy of the truth**, and the first thing to go stale.
The links are the truth; the matrix is a view of them.

## BR-U4-6.2 Requirements with no cases appear

With an empty set. An absent row hides exactly what the matrix exists to reveal
(US-TRC-04 AC4).

## BR-U4-6.3 Derived links are counted separately

Direct and `derived-from-commit` links are reported apart. Provenance is weaker
evidence than specification, and a matrix that merged them would overstate how well
the corpus is grounded.

## BR-U4-6.4 Both directions, both formats

Forward: requirement → coverage item → case → automated test. Reverse: the same
backwards. Markdown and CSV.

---

# BR-U4-7: Volume Reporting

## BR-U4-7.1 Per batch

Generated against planned for the coverage items the batch touched, plus counts of
rejections by reason.

## BR-U4-7.2 Per feature

A summary stating the variance and its reasons: duplicates rejected, boundaries
undetermined, coverage items the agent produced no case for.

**"40 cases from 12 coverage items, ISTQB-standard depth" can be checked.
"40 cases" cannot.** FR-TCG-07 forbids padding, and the way to make that verifiable is
to state where every case came from.

## BR-U4-7.3 A shortfall is reported, never closed by padding

If a feature yields fewer cases than planned, the variance and its reasons are
reported. Nothing generates filler to reach the figure.

---

# BR-U4-8: The Validation Sequence

Ordering is a design decision. Cheap checks first, expensive lookups last, and the
gate before any of it.

| Stage | Check | Component |
|---|---|---|
| A | Coverage baseline approved and unchanged | U7 L5 |
| A | Batch size within the cap | S5 |
| B | Identifier not caller-supplied | D7 |
| B | At least one step, each with an expected result | D1 construction, D7 |
| B | Ordinals unique and gapless | D7 |
| B | Test type matches the coverage item | S5 |
| B | Data-dependent steps carry an equivalence class | D7 |
| C | At least one link resolves to a known Jira key | D3, D7 |
| D | Not a duplicate of the corpus bucket or the batch | D4 |
| E | Automatability classified | D6 |
| F | Identifiers allocated | D5 |

**Stage A stops the batch; B through D collect.** A closed gate or an oversized batch
makes every case in it moot. A malformed case does not invalidate its neighbours, so
all faults are reported together and one correction pass fixes them.

**E and F run only after everything passes**, because classification and allocation
have side effects on the sequence state that a rollback would have to unwind.

---

# Rule-to-Requirement Traceability

| Rule | Requirements | Stories |
|---|---|---|
| BR-U4-1 Payload contract | FR-TCG-01, FR-TCG-04 | US-TCG-01 |
| BR-U4-2 Automatability signals | FR-TCG-06, FR-AUT-10 | US-TCG-04 |
| BR-U4-3 Batch limits | FR-TCG-01 | US-TCG-01 |
| BR-U4-4 Duplicate scope | FR-TCG-05, NFR-PRF-03 | US-TCG-03 |
| BR-U4-5 View emission | FR-TCG-08, FR-TCG-10, NFR-USA-02 | US-TCG-06 |
| BR-U4-6 Matrix | FR-TRC-05, FR-TRC-06, FR-RPT-03 | US-TRC-04 |
| BR-U4-7 Volume reporting | FR-TCG-07 | US-TCG-05 |
| BR-U4-8 Validation sequence | FR-TCG-02, FR-TCG-03, FR-TCG-09, FR-TRC-01 | US-TCG-01, US-TCG-02 |
