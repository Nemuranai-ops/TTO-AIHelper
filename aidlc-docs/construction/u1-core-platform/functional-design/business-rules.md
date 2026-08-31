# Business Rules — U1 Core Platform

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U1 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-29

The five rules deferred from `application-design.md` §8 are settled here, plus the rules governing
identifiers, integrity and traceability. Every other unit inherits these.

---

# BR-1: Duplicate Detection (D4)

**Decision**: normalise, then compare token shingles. Reject at 1.0 as identical and at 0.90 or above
as near-duplicate. A differing equivalence class is always material.

## BR-1.1 Normalisation

Applied in order:

1. Concatenate each step as `action + " || " + expected`, joined across steps in ordinal order
2. Lowercase
3. Collapse all whitespace runs to a single space
4. Strip terminal punctuation from each segment
5. **Exclude test data values**; **retain equivalence class labels**
6. Trim

**Step order is preserved, not sorted.** Two cases performing the same actions in different orders
are different tests — one may be checking that order matters.

**Why values are excluded but class labels retained**: two boundary cases differ only in their
value, and comparing values would make every boundary case unique, defeating the check. Comparing
class labels keeps "just below minimum" distinct from "just above maximum" while collapsing two
cases that both test "valid mid-range".

## BR-1.2 Comparison

- Token shingles of size 3 over the normalised string
- Jaccard similarity of the shingle sets
- Score in [0.0, 1.0]

## BR-1.3 Thresholds

| Score | Verdict | Action |
|---|---|---|
| 1.0 | `identical` | Reject, name the existing case |
| >= 0.90 | `near-duplicate` | Reject, show the comparison |
| < 0.90 | `distinct` | Accept |

## BR-1.4 Material difference override

**A differing equivalence class makes two cases distinct regardless of score.** Checked before the
threshold, and it overrides it.

Rationale: two boundary cases at opposite ends of a range may share almost every word. They are not
duplicates; they are the two halves of boundary analysis. A pure text threshold would reject one and
silently halve the boundary coverage.

## BR-1.5 Scope

- Candidates selected by `bucket_key`, never by full scan (NFR-PRF-03)
- `bucket_key` = feature slug + test type + step count
- Comparison runs against the existing corpus **and** within the submitted batch
- Rejections are recorded and appear in the gap report (US-TCG-03 AC5)

## BR-1.6 Properties (PBT-03)

- Reflexive: `similarity(a, a) == 1.0`
- Symmetric: `similarity(a, b) == similarity(b, a)`
- Bounded: `0.0 <= similarity(a, b) <= 1.0`
- Deterministic: repeated evaluation yields an identical result

---

# BR-2: Coverage Depth (D2)

**Decision**: ISTQB-standard depth.

## BR-2.1 Equivalence Partitioning

| Rule | Yield |
|---|---|
| One case per valid equivalence class | 1 per class |
| One case per invalid equivalence class | 1 per class |

Each case records its class in `test_data.equivalence_class`.

## BR-2.2 Boundary Value Analysis

**Three values per boundary**: just below, at, just above.

For a range with a minimum and a maximum, that is 6 cases: `min-1`, `min`, `min+1`, `max-1`, `max`,
`max+1`. Each records its `boundary_relation`.

**Where boundaries are undetermined**, no boundary cases are generated. The requirement is flagged
`boundaries-undetermined` and appears in the gap report. Inventing plausible limits would produce
tests that assert a fiction (US-TRQ-03 AC4).

## BR-2.3 Decision Tables

- One case per rule in the table
- Conditions and their combination recorded in the rationale
- Where rules exceed 16, apply reduction per BR-2.5

## BR-2.4 State Transitions

| Rule | Yield |
|---|---|
| 0-switch coverage — every valid transition exercised once | 1 per valid transition |
| Every explicitly forbidden transition | 1 per forbidden transition |

1-switch coverage is not applied by default. Forbidden transitions are included because an
unenforced prohibition is a common and high-consequence defect.

## BR-2.5 Reduction

Triggered when a single requirement's combinatorial expansion exceeds **50 planned cases**.

| Technique | When |
|---|---|
| Pairwise (all-pairs) | Three or more independent parameters |
| Each-choice | Parameters are genuinely independent and pairwise still exceeds the threshold |
| Risk-based pruning | Requirement risk band is `low` |

The technique used is recorded in `coverage_item.reduction_applied`, and the reduction appears in
the gap report. A reduction that nobody can see is indistinguishable from an oversight.

## BR-2.6 Not-required decisions

When a test type adds nothing for a requirement, a `coverage_item` is created with
`is_required = false` and a rationale. **The row exists.** Omitting it makes a deliberate exclusion
look identical to an oversight.

## BR-2.7 Properties (PBT-03)

- Total planned yield equals the sum of per-feature yields
- Per-feature yield equals the sum of its coverage items' `planned_count`
- Reduction never increases planned count
- Every requirement has at least one coverage item, required or not

---

# BR-3: Commit-to-Key Selection (D3)

**Decision**: most recent commit carrying a known key, within a bounded window.

## BR-3.1 Candidate gathering

1. Retrieve commit history for the file via `bitbucket_log`
2. Restrict to commits within the **lookback window**, default **180 days**, configurable
3. Extract Jira keys from each commit message
4. Discard keys absent from the ingested artefact set — an invented key cannot satisfy the rule
   (US-TRC-01 AC4)

## BR-3.2 Selection

Applied in order:

1. **Most recent** commit carrying a surviving key
2. Tie-break: **most lines changed** in that file
3. Tie-break: **commit recency** by timestamp
4. Still tied: lowest key lexicographically, purely for determinism

## BR-3.3 Recording

| Field | Content |
|---|---|
| `link_type` | `derived-from-commit` — never `direct-story` |
| `evidence` | Commit sha and message excerpt |
| `selection_basis` | Which rule decided, e.g. "most recent within window; 3 candidates" |
| `alternatives` | Every candidate not chosen, with its commit |

## BR-3.4 Failure

No surviving candidate means **no key is derived**. The behaviour routes to the gap report with
what was attempted. No test case is created (FR-TRC-04).

## BR-3.5 Rationale for the window

Recency is the best available proxy for current intent. The 180-day window prevents a five-year-old
refactor from becoming the recorded provenance of today's behaviour — a link that is technically
present and substantively meaningless is worse than an honest gap, because it satisfies the rule
while defeating its purpose.

## BR-3.6 Reporting distinction

Derived links are **counted separately** from direct links in every coverage report (US-TRC-02 AC3).
Provenance is weaker evidence than specification and must not be presented as equivalent.

---

# BR-4: Risk Rating (D6)

**Decision**: four weighted factors, banded, with partial ratings flagged.

## BR-4.1 Factors

Each scored 1-5.

| Factor | Weight | Signals |
|---|---|---|
| Business criticality | **3** | Jira priority, epic labels, whether the requirement is on a revenue or auth path |
| Complexity | **2** | Number of business rules, conditions, and state transitions involved |
| Integration surface | **2** | Count of external dependencies and endpoints touched |
| Change frequency | **1** | Commits touching the relevant files in the last 90 days |

## BR-4.2 Computation

```
weighted_sum   = sum(score_i * weight_i)  for available factors
max_possible   = sum(5 * weight_i)        for available factors
risk_score     = round(weighted_sum / max_possible * 100)
```

## BR-4.3 Bands

| Score | Band |
|---|---|
| 0-25 | `low` |
| 26-50 | `medium` |
| 51-75 | `high` |
| 76-100 | `critical` |

## BR-4.4 Unavailable factors

An unavailable factor is **removed from both numerator and denominator**, and
`risk_is_partial = true`. It is never scored zero.

Rationale: scoring an unknown as zero makes an unmeasured requirement look safe. Removing it from
the denominator preserves the ratio among what is actually known, and the flag tells the reader the
rating rests on less evidence (US-TRQ-02 AC3).

## BR-4.5 Factor transparency

`risk_factors` stores every factor with its score, or `unavailable`. Two requirements with identical
bands can therefore be distinguished by cause — a high rating driven by criticality calls for a
different response than one driven by churn (US-TRQ-02 AC4).

---

# BR-5: Automatability Classification (D6)

**Decision**: an ordered decision list, first match wins.

## BR-5.1 The list

Evaluated top to bottom; the first matching rule decides.

| # | Condition | Verdict |
|---|---|---|
| 1 | Requires visual or aesthetic judgement (layout, colour, "looks correct") | `manual-only` |
| 2 | Requires a step outside the application (email, SMS, physical device, third-party console) | `manual-only` |
| 3 | Requires data that cannot be provisioned programmatically | `manual-only` |
| 4 | Is exploratory or usability-oriented by nature | `manual-only` |
| 5 | Is an API case whose endpoint `shape_source` is `specified` | `automatable` |
| 6 | Is an API case whose endpoint `shape_source` is `inferred` | `automatable`, annotated contract-inferred |
| 7 | Is a UI case where every referenced element has `is_verified = true` | `automatable` |
| 8 | Is a UI case where every referenced element has a locator but some are unverified | `automatable`, annotated unverified-locator |
| 9 | Is a UI case where a referenced element has `is_fragile = true` and no alternative | `needs-review` |
| 10 | Anything else | `needs-review` |

## BR-5.2 Recording

Every verdict stores the **rule number and its text** in `automatability_reason`. A verdict always
traces to the rule that produced it.

## BR-5.3 Override

A human may override any verdict. The override records actor, timestamp and reason, and is never
recomputed away by a later classification run.

## BR-5.4 Why an ordered list rather than a score

The list is auditable and reproducible: the same case always yields the same verdict, and anyone can
see why in one line. A weighted score handles mixed cases more smoothly but produces verdicts nobody
can explain, and "the classifier said 0.63" is not an answer to an automation engineer asking why a
test exists.

---

# BR-6: Identifier Allocation (D5)

## BR-6.1 Format

| Entity | Format |
|---|---|
| Test case | `TC-<FEATURE_SLUG>-<00001>` |
| Testable requirement | `TR-<FEATURE_SLUG>-<00001>` |
| Coverage item | `CI-<FEATURE_SLUG>-<00001>` |
| Automated test | `AT-<FEATURE_SLUG>-<00001>` |

Sequence is **per feature per kind**, zero-padded to 5 digits, starting at 1.

## BR-6.2 Rules

- Allocation is by the toolchain only. A supplied identifier is rejected with
  `REJECTED_SELF_SUPPLIED_ID`
- Monotonic within (kind, feature); a number is never reissued, including after a case is obsoleted
- Stable across regeneration: a case whose `coverage_item_id` and `title` match an existing
  non-obsolete case retains that case's identifier
- Overflow past 99999 in one feature per kind fails with `FAILED_INTERNAL` rather than wrapping

## BR-6.3 Properties (PBT-02, PBT-03)

- Round-trip: `decode(encode(id)) == id`
- Uniqueness: no identifier is issued twice within a (kind, feature)
- Monotonicity: successive allocations strictly increase

---

# BR-7: Integrity Validation (D7)

Order matters — cheap structural checks run before expensive lookups.

| # | Check | Rejection code |
|---|---|---|
| 1 | Identifier not supplied by the caller | `REJECTED_SELF_SUPPLIED_ID` |
| 2 | At least one step present | `REJECTED_NO_STEPS` |
| 3 | Every step has a non-blank expected result | `REJECTED_NO_STEPS` |
| 4 | Step ordinals unique and gapless from 1 | `REJECTED_INVALID_STEPS` |
| 5 | Data-dependent steps carry an equivalence class | `REJECTED_MISSING_EQUIVALENCE_CLASS` |
| 6 | At least one trace link present | `REJECTED_NO_JIRA_KEY` |
| 7 | At least one link resolves to a Jira key | `REJECTED_NO_JIRA_KEY` |
| 8 | Every referenced key exists in the ingested set | `REJECTED_UNKNOWN_JIRA_KEY` |
| 9 | Coverage baseline approved for this feature | `REJECTED_GATE_CLOSED` |
| 10 | Not a duplicate (BR-1) | `REJECTED_DUPLICATE` |

**Batch validation reports every failure, not the first.** At batch sizes of forty or more, failing
on the first problem would force the agent through as many correction rounds as there are faults
(US-TCG-01 AC2, and the S5 sequence in `services.md`).

---

# BR-8: Traceability (D3)

## BR-8.1 Link type precedence

When multiple link types are available for the same target, the strongest is recorded as primary:

`direct-story` > `derived-from-commit` > `confluence` > `code-symbol` > `screenshot`

All links are retained; precedence affects which is presented as primary and how the link is counted
in reporting.

## BR-8.2 Jira key resolution

1. Direct story link, if present
2. Otherwise, commit derivation per BR-3
3. Otherwise, gap report — no case is created

## BR-8.3 Matrix construction

- Forward: requirement → coverage items → cases → automated tests
- Reverse: automated test → case → coverage item → requirement → source artefact
- **Requirements with zero cases appear with an empty set**, never omitted. An absent row hides
  exactly what the matrix exists to reveal (US-TRC-04 AC4)

## BR-8.4 Properties (PBT-03)

- Bidirectional consistency: every forward edge has a corresponding reverse edge
- Every non-obsolete case reaches at least one Jira key
- The matrix contains every requirement, including those with no cases

---

# BR-9: Impact Classification (D8)

Applied when a delta run maps a change to existing artefacts.

| Condition | Classification |
|---|---|
| Source artefact hash unchanged | `unchanged` |
| Source changed, but the requirement statement is unaffected | `unchanged` |
| Requirement statement changed, or its business rule changed | `requires-update` |
| Requirement deleted, or its feature removed | `obsolete` |
| Endpoint removed and the case targets it | `obsolete` |
| Screen removed and the case targets it | `obsolete` |
| Change maps to no traceable artefact | recorded as **unmapped**, never assumed harmless |

**Scale is reported before regeneration.** When impact exceeds **20% of the active corpus**, the
proportion is stated and confirmation is required before any regeneration proceeds (US-DLT-02 AC5).

---

# Rule-to-Requirement Traceability

| Rule | Requirements | Stories |
|---|---|---|
| BR-1 Duplicate detection | FR-TCG-05, NFR-PRF-03 | US-TCG-03 |
| BR-2 Coverage depth | FR-COV-01 to FR-COV-03, FR-COV-07 | US-COV-01, US-COV-02, US-COV-05 |
| BR-3 Commit-to-key | FR-TRC-02, FR-TRC-03, FR-TRC-04 | US-TRC-02, US-TRC-03 |
| BR-4 Risk rating | FR-TRQ-03 | US-TRQ-02 |
| BR-5 Automatability | FR-TCG-06, FR-AUT-10 | US-TCG-04 |
| BR-6 Identifiers | FR-TCG-04 | US-TCG-01 |
| BR-7 Integrity validation | FR-TCG-01, FR-TCG-02, FR-TRC-01, §10.3 | US-TCG-01, US-TRC-01 |
| BR-8 Traceability | FR-TRC-01 to FR-TRC-06 | US-TRC-01, US-TRC-04 |
| BR-9 Impact classification | FR-DLT-03, FR-DLT-04, FR-DLT-05 | US-DLT-02, US-DLT-03 |

All five business rules deferred in `application-design.md` §8 are now specified: BR-1 (similarity),
BR-2 (coverage depth), BR-3 (commit-to-key), BR-4 (risk weights), BR-5 (automatability).
