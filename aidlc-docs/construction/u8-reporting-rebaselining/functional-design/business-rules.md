# Business Rules — U8 Reporting and Re-baselining

**Phase**: CONSTRUCTION | **Unit**: U8 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-31

U8 reads the corpus and reports on it, and detects when the world has moved. It
changes nothing except which cases are marked obsolete.

---

# BR-U8-1: The Four Reports

## BR-U8-1.1 What each states

| Report | Sections |
|---|---|
| **Coverage** | Per feature: requirements, coverage items, planned, generated, variance. Per test type across the corpus. Every figure with its derivation |
| **Gap** | Uncovered requirements, untraceable behaviours, manual-only cases, reduced-depth features, rejected duplicates, boundaries undetermined |
| **Automation** | Automated, deferred with the reason for each, at-risk tests and why |
| **Traceability matrix** | Forward and reverse, Markdown and CSV |

## BR-U8-1.2 Every figure carries its derivation

"40 cases" is not a report. "40 cases from 12 coverage items at ISTQB-standard depth,
against 47 planned" can be checked (FR-RPT-01).

The same rule U4 applied to its volume report, applied to every number U8 renders.
**A figure without its derivation cannot be audited**, and an unauditable coverage
report is exactly the false confidence this system exists to remove.

## BR-U8-1.3 The gap report includes empty categories

All six `gap` categories appear, including those with no entries. An absent category
is indistinguishable from a category nobody checked (FR-RPT-02), and U1's `gap_query`
already returns empty categories for this reason.

## BR-U8-1.4 The matrix is U4's, rendered

U8 calls U4's matrix construction and renders the result. It does not rebuild it. Two
implementations would give two answers to one question, and the one in the report would
be the one nobody tested.

---

# BR-U8-2: Sections That Cannot Be Computed

**Decision**: render what is available, state what is not and why.

## BR-U8-2.1 Three states, not two

| State | Meaning |
|---|---|
| `computed`, with rows | The section was calculated and has data |
| `computed`, empty | The section was calculated and there is nothing in it |
| **`not_available`** | **The section could not be calculated** |

## BR-U8-2.2 Why the distinction matters

A coverage section with no rows means **every requirement is uncovered** — an alarming
finding. A section that could not be computed means **the coverage model has not been
approved yet** — an ordinary state early in a baseline.

Those call for opposite responses. Omitting an uncomputable section silently makes them
look identical, which is the one outcome a coverage report must never produce.

## BR-U8-2.3 The reason names the stage

"Not available: no approved coverage model for this feature. Run the coverage stage."
The report becomes an instruction rather than an absence.

## BR-U8-2.4 A missing section never fails the report

This is U6's degrade-and-report pattern in its second use. A report that fails whole
because one section is empty is useless during the period it would be most useful —
while the baseline is being built and the Test Lead wants to see how far it has got.

---

# BR-U8-3: Reports Come From SQLite

**Decision**: every figure is a query result. The model composes no number.

## BR-U8-3.1 The rule

FR-RPT-05. The agent may explain a report; it may not produce one. Every count, every
percentage and every list in a rendered report is the output of SQL over the corpus.

## BR-U8-3.2 Why this is a hard rule and not a preference

The system's entire claim is that its coverage figures are defensible. **A number the
model composed is a number nobody can reproduce**, and one wrong figure in a report the
Test Lead signs off makes every other figure in it suspect.

It is also the rule that makes the toolchain worth having: if the model could assemble
reports, the deterministic layer would be optional.

## BR-U8-3.3 The organising principle, stated once more

The model reasons about meaning; deterministic code guarantees the rest. Reporting is
where that division is most visible, because a report is nothing *but* the facts.

---

# BR-U8-4: The Delta Baseline

**Decision**: recorded on the run that established it.

## BR-U8-4.1 What is recorded

Per repository, the head commit the run saw. Plus the latest Jira `updated` timestamp
it ingested.

## BR-U8-4.2 Which run is the baseline

The most recent run with `ended_at` set, of either kind. A delta run that completes
becomes the baseline for the next one.

## BR-U8-4.3 No baseline is a reported state, not an error

A first delta run with no completed run before it has nothing to compare against. It
says so and stops.

**Treating "no baseline" as "everything changed" would be worse than useless**: it
would classify the entire corpus as affected, which is both true and unhelpful, and it
would obscure the real answer, which is that the baseline run has not finished.

## BR-U8-4.4 A failed run sets no baseline

`ended_at` is set on completion. A run that failed partway leaves it null and is not
eligible — so the next delta compares against the last run that actually finished,
which is the only head the system can vouch for having fully ingested.

---

# BR-U8-5: Change Detection

**Decision**: two sources, and anything untraceable is reported.

## BR-U8-5.1 The sources

| Source | Mechanism | Requirement |
|---|---|---|
| Bitbucket | `bitbucket_changes` and `bitbucket_diff` between the recorded head and the current head | FR-DLT-01 |
| Jira | JQL over `updated >= <watermark>` | FR-DLT-02 |

## BR-U8-5.2 An unreachable source does not fail the run

Under U1's `isolate`. A Bitbucket outage produces a delta run that reports Jira changes
and states that repository changes could not be detected — the same degrade-and-report
shape as everywhere else in this system.

**A partial delta is honest; a failed one leaves the operator with nothing.**

## BR-U8-5.3 Unmapped changes are reported, never assumed harmless

D8's `map_impact` already enforces this: a change reaching nothing traceable goes to
`unmapped` rather than being dropped.

Its own comment states the reason, and it is worth repeating here because U8 is where
it takes effect: **"we found no link" and "there is no impact" are different
statements, and conflating them is how an untested change ships.**

## BR-U8-5.4 Unmapped is a finding, not a failure

It usually means a change in code no test traces to — which is either a genuine
coverage gap or a change in something untestable. The report says which changes, and
the operator decides.

---

# BR-U8-6: Impact Classification

**Decision**: delegated to D8 entirely.

## BR-U8-6.1 U8 supplies edges; D8 classifies

S9 builds `TraceEdge`s from the traceability graph and calls `classify_edge`. It
contains no classification logic of its own.

The classification rules — deleted requirement and removed target are `obsolete`,
changed statement and changed rule are `requires-update`, everything else is
`unchanged` — live in `domain/impact.py` and were reviewed at U1.

## BR-U8-6.2 Why this matters more here than elsewhere

U8 is the last unit, and by now six units have resisted the same temptation to copy a
domain algorithm for convenience. **A local classification "just for the delta report"
would drift**, and the drift would show up as a case the report calls obsolete and the
corpus calls active.

The import contracts make it structural rather than remembered.

---

# BR-U8-7: Retirement and the Boundary

**Decision**: retire the obsolete, report the rest, create nothing.

## BR-U8-7.1 What a delta run does

| Classification | Action |
|---|---|
| `obsolete` | **Retired** — marked, with the reason and the change event |
| `requires-update` | **Reported, untouched** |
| `unchanged` | Recorded in the report; nothing done |

## BR-U8-7.2 Retirement never deletes

`is_obsolete = 1`, the reason, and the `change_event` id. Steps, data, links and the
automated test all remain and stay readable (FR-DLT-05).

The case leaves coverage counts, generated views and duplicate candidate selection
automatically, because U3's and U4's queries already filter on `is_obsolete`.

## BR-U8-7.3 A retired identifier is never reissued

Already guaranteed: D5's `stable_id_for` skips obsolete cases, so a new case matching a
retired one on coverage item and title gets a fresh number rather than reclaiming the
old one. Two cases sharing a number could not both be traced.

## BR-U8-7.4 `requires-update` is not regenerated here

S9 has **no method** that creates a requirement or a case. A delta run that regenerated
would bypass every gate the baseline had to pass, which FR-DLT-06 forbids explicitly.

The operator re-runs U3 and U4 for the affected scope, through the normal gates. Fourth
use of enforcement-by-absence, after P2's source protocols, `next_unit()` and S7's
missing `push`.

## BR-U8-7.5 The automated test of a retired case is not deleted

It is reported in the automation report as belonging to a retired case. **U5's hand-edit
protection would not have applied**, because U8 would be the one deleting it — so an
engineer's edited spec could be destroyed by a delta run they did not initiate.

---

# BR-U8-8: Run History

**Decision**: every case traces to the run that created or last modified it.

## BR-U8-8.1 Already recorded

`created_run_id` and `last_modified_run_id` on `test_case`, written since U4. U8's
contribution is to make them readable: the coverage report can state which run produced
each figure, and a retired case names the delta run that retired it (FR-DLT-07).

## BR-U8-8.2 The business-rule fingerprint

`run.business_rules` holds the tunables in force — similarity threshold, commit
lookback, batch cap, privacy patterns, Playwright version. **Two runs under different
thresholds are not comparable**, and the report says which was in force rather than
leaving a reader to assume they match.

---

# Rule-to-Requirement Traceability

| Rule | Requirements | Stories |
|---|---|---|
| BR-U8-1 The four reports | FR-RPT-01 to FR-RPT-04 | US-RPT-01 to -03 |
| BR-U8-2 Uncomputable sections | FR-RPT-01, FR-RPT-02 | US-RPT-01, US-RPT-02 |
| BR-U8-3 Reports from SQLite | FR-RPT-05 | US-RPT-01 to -03 |
| BR-U8-4 The delta baseline | FR-DLT-01, FR-DLT-02 | US-DLT-01 |
| BR-U8-5 Change detection | FR-DLT-01, FR-DLT-02, FR-DLT-03 | US-DLT-01, US-DLT-02 |
| BR-U8-6 Classification | FR-DLT-04 | US-DLT-02 |
| BR-U8-7 Retirement | FR-DLT-05, FR-DLT-06 | US-DLT-03 |
| BR-U8-8 Run history | FR-DLT-07 | US-DLT-01, US-DLT-03 |
