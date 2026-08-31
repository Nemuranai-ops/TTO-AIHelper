# Functional Design Plan — U4 Test Case Generation

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U4 | **Stage**: Functional Design
**Created**: 2026-08-30T11:41:00Z
**Status**: APPROVED 2026-08-30T11:55:00Z - all recommendations accepted

---

## Unit Context

**Responsibility**: produce the corpus. Every rule that makes it trustworthy runs
here, in one transaction.

**Components**: S5 TestCaseService, A8 ViewEmitter.

**Stories** (7): US-TCG-01 to US-TCG-06, US-TRC-04.

**Depends on**: U1, U7, U2, U3 — all complete.

---

## Why this unit is different

Two components, seven stories, and the highest logical density in the project. S5
orchestrates **six** U1 domain components inside a single transaction:

```
D7 validate -> D3 resolve key -> D4 de-duplicate -> D6 classify -> D5 allocate -> commit
```

The unit decomposition called component count a poor proxy for size here, and this is
where that shows. Nothing new is invented; everything is sequenced, and the sequence
is what makes the corpus defensible.

**This is also where the 6,000 figure becomes real.** Every earlier unit prepared for
volume; U4 produces it.

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Business Rules: automatability signal gathering

BR-5's decision list needs ten signals per case. Some are derivable, some are not.

| Signal | Source |
|---|---|
| Is an API case, and its `shape_source` | **Derivable** from the case's coverage item and the API model |
| Every element has a locator / all verified | **Derivable** from the UI model U2 stored |
| Has a fragile locator with no alternative | **Derivable** |
| Requires visual judgement, an external step, unprovisionable data, is exploratory | **Not derivable** — the agent must say |

A) **Derive what the models hold; take the four judgement signals from the agent's
payload, defaulting each to false.** A case the agent says nothing about is judged on
its derivable signals alone, which lands it in rules 5-10. **(Recommended — the same
shape as U3's risk signals, and defaulting to false is safe here because it can only
move a case toward `automatable` or `needs-review`, never toward a wrong `manual-only`)**

B) **Require all ten explicitly.** Most accurate, and it makes every case payload
carry ten booleans the agent must reason about individually.

C) **Derive what is possible and mark the rest `needs-review`.** Conservative, and it
would send most of the corpus to review.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 2 — Business Rules: what the agent supplies per case

FR-TCG-01 lists the fields. What is the contract, and what does S5 derive?

A) **Agent supplies**: title, test type, priority, preconditions, ordered steps with
expected results, test data with equivalence classes, tags, the coverage item it
satisfies, and its trace links. **S5 derives**: the identifier, the normalised hash,
the bucket key, and the automatability verdict. **(Recommended — the agent supplies
meaning, the toolchain supplies identity and classification. A case whose identifier
the agent chose is one it can reuse or collide)**

B) The agent also supplies the automatability verdict, with S5 validating it.

C) The agent supplies only steps and data; S5 derives the rest including the title.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 3 — Business Rules: batch size

A feature's coverage model may plan hundreds of cases. `testcases_upsert` is atomic.

A) **Cap a batch at 200 cases, refusing a larger one with the count and guidance.**
The agent submits a feature's cases in several batches, each atomic. **(Recommended —
a 500-case batch that fails on case 499 wastes the whole thing, and 200 is already
more than a reviewer reads in one sitting)**

B) **No cap.** Whole features in one call, and a single fault discards all of it.

C) **Cap at 50** — smaller failure radius, and more round trips than the volume warrants.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 4 — Business Rules: duplicate detection scope

BR-1.5 checks against the existing corpus and within the batch. At 6,000 cases, what
does "the existing corpus" mean for a bucket lookup?

A) **The bucket only, and only non-obsolete cases.** `idx_case_bucket` narrows
10,000 cases to a handful; obsolete cases are excluded because a retired case should
not block a replacement. **(Recommended — U1's benchmark measured 8 candidates from
10,000, and including obsolete cases would make a delta run unable to regenerate what
it just retired)**

B) **The bucket including obsolete cases**, so history is respected.

C) **The whole feature**, not just the bucket. Safer against a bucketing error, and
it discards the index that makes the budget reachable.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 5 — Business Rules: view sharding and hand-edit detection

FR-TCG-08 emits Markdown and YAML per feature. US-TCG-06 AC4 requires hand-edits to be
detected before overwriting.

A) **One Markdown and one YAML file per feature, with the emitted content hash stored
per file. On re-emission, a file whose current hash differs from the stored one is
reported and skipped, not overwritten.** The operator resolves it. **(Recommended —
skipping rather than overwriting means an edit is never silently lost, and the corpus
is unaffected either way because the files are views)**

B) **Detect and overwrite anyway**, having reported it. Simpler, and the report
arrives after the loss.

C) **One file per case.** Finer diffs, and 6,000 files.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 6 — Business Rules: the traceability matrix

US-TRC-04 requires bidirectional traversal in Markdown and CSV.

A) **Built on demand from `trace_link`, never stored.** Requirements with no cases
appear with an empty set; derived links are counted separately from direct ones.
**(Recommended — a stored matrix is a second copy of the truth, and the first thing
that goes stale)**

B) **Materialised into a table** on each case batch. Fast reads, and a consistency
obligation on every write.

C) **Built on demand, cached per run.**

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 7 — Business Rules: the derived-volume report

FR-TCG-07 forbids padding and requires the total to be reported with its derivation.

A) **Every batch reports generated against planned for its coverage items, and a
feature-level summary states the variance with reasons — duplicates rejected,
boundaries undetermined, cases the agent could not derive.** **(Recommended — "40
cases from 12 coverage items" can be checked; "40 cases" cannot)**

B) **Report the count only**, leaving derivation to the coverage report.

C) **Report generated against planned, without explaining variance.**

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

# Execution Checklist

## Phase 1: Business Rules

- [x] 1.1 Specify automatability signal gathering per Question 1
- [x] 1.2 Specify the case payload contract per Question 2
- [x] 1.3 Specify batch limits per Question 3
- [x] 1.4 Specify duplicate scope per Question 4
- [x] 1.5 Specify view emission and hand-edit detection per Question 5
- [x] 1.6 Specify matrix construction per Question 6
- [x] 1.7 Specify volume reporting per Question 7
- [x] 1.8 Specify the full validation sequence and its ordering
- [x] 1.9 Write `business-rules.md`

## Phase 2: Domain Entities

- [x] 2.1 Define the case payload and batch report types
- [x] 2.2 Define the view manifest and hand-edit record
- [x] 2.3 Define the matrix output shape
- [x] 2.4 Confirm whether a migration is needed
- [x] 2.5 Write `domain-entities.md`

## Phase 3: Business Logic Model

- [x] 3.1 Model the six-component orchestration and its ordering
- [x] 3.2 Model identifier stability across regeneration
- [x] 3.3 Model view emission and hand-edit detection
- [x] 3.4 Model matrix construction
- [x] 3.5 Model the interaction with U1, U3 and U7
- [x] 3.6 Identify the U4 property surface
- [x] 3.7 Write `business-logic-model.md`

## Phase 4: Validation

- [x] 4.1 Verify all 7 U4 stories are served
- [x] 4.2 Verify FR-TCG-01 to -10 and FR-TRC-05, -06 are covered
- [x] 4.3 Verify the gate and traceability rules are enforced, not restated
- [x] 4.4 Verify Security and Resiliency applicability
- [x] 4.5 Validate content per `common/content-validation.md`
- [x] 4.6 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `.../u4-test-case-generation/functional-design/domain-entities.md`
- [x] `.../u4-test-case-generation/functional-design/business-rules.md`
- [x] `.../u4-test-case-generation/functional-design/business-logic-model.md`

**No `frontend-components.md`**: U4 has no user interface. The emitted views are read
in the editor, and the operator reaches this stage through U7's `cases` chat mode.
