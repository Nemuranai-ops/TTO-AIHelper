# NFR Requirements Plan — U8 Reporting and Re-baselining

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U8 | **Stage**: NFR Requirements
**Created**: 2026-08-31T09:27:00Z
**Status**: APPROVED 2026-08-31 — all recommendations accepted

---

## What U8 inherits

OD-01 to OD-04, the eight Resiliency decision points, the tech stack, and the project
NFRs owned by every prior unit. **Nothing re-opened.**

**No new dependency expected.** Reports are SQL plus string building; CSV is stdlib.

---

## The last unit, and the budget that has been waiting since U1

**NFR-PRF-02 has never been exercised**: "a full report at 6,000 cases in under 30
seconds". U1 benchmarked an aggregation against synthetic rows and measured 0.003 s;
U8 is where a real report is actually assembled, over a corpus that U4 produced and U5
and U6 read.

| Budget | Status before U8 | After |
|---|---|---|
| NFR-PRF-02 full report < 30 s | Measured on one aggregation | **Measured on the whole report** |
| NFR-SCL-03 corpus-wide queries | Provisioned for | Exercised |

**Three questions.**

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Performance: the report budget, and what it covers

A) **Under 30 seconds for the full report set at 6,000 cases; under 5 seconds for any
single report. Measured end to end — query, render and write — not query alone.**
**(Recommended — the project NFR says "a full report", and measuring only the query
would let a slow renderer pass a budget it does not meet; the per-report figure is what
an operator actually waits for)**

B) **Query time only.** Easier to measure, and it excludes the part that writes the
file the operator is waiting for.

C) **No per-report budget**, only the 30-second total. Simpler, and a single pathological
report could consume the whole budget unnoticed.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — under 30 s for the full set, under 5 s per report, measured end to end (accepted via "Accept all recommendations")

## Question 2 — Reliability: what a partially-failed delta run produces

Bitbucket and Jira are separate sources, and either can be unreachable.

A) **Per-source isolation. A delta run reports the changes it could detect, names the
sources it could not reach, and does not update the baseline.**
**(Recommended — the last clause is the important one: advancing the baseline after a
partial detection would make the undetected changes invisible for ever, because the
next run would compare from the newer head)**

B) **Fail the whole run** if any source is unreachable. Simple, and one flaky source
then blocks re-baselining entirely.

C) **Report partially and advance the baseline.** Keeps the run history tidy, and it
permanently loses every change in the window the failed source covered.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — per-source isolation, and a partial run does not advance the baseline (accepted via "Accept all recommendations")

## Question 3 — Security: what reports may contain, and where they go

Reports quote requirement statements, case titles and gap subjects — text that came
from Jira and Confluence.

A) **Reports state behaviour and identifiers, not verbatim source documentation, and
are written under `generated/reports/` which is gitignored. The same rule U4 applied to
its views.** **(Recommended — a report quoting three paragraphs of an internal
Confluence page moves that page somewhere with a different access list, and reports are
the artefact most likely to be forwarded to someone outside the team)**

B) **No restriction.** Most informative, and it makes the confidentiality of every
report depend on where the reader sends it.

C) **Redact all source text**, showing only identifiers. Safest, and a gap report
listing thirty requirement identifiers with no statements is one nobody can act on.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — behaviour and identifiers, not verbatim source documentation; written under gitignored `generated/reports/` (accepted via "Accept all recommendations")

---

# Execution Checklist

## Phase 1: Assessment

- [x] 1.1 Record what U8 inherits unchanged
- [x] 1.2 Identify the inherited budgets U8 first exercises
- [x] 1.3 Confirm which project NFRs U8 owns

## Phase 2: Requirements

- [x] 2.1 Performance requirements per Question 1
- [x] 2.2 Scalability requirements
- [x] 2.3 Reliability requirements per Question 2
- [x] 2.4 Security requirements per Question 3
- [x] 2.5 Maintainability requirements
- [x] 2.6 Extension compliance: Security, Resiliency, PBT
- [x] 2.7 Write `nfr-requirements.md`

## Phase 3: Tech Stack

- [x] 3.1 Confirm no new dependency
- [x] 3.2 Record the CSV and Markdown rendering decisions
- [x] 3.3 Write `tech-stack-decisions.md`

---

# Mandatory Artifacts

- [x] `.../u8-reporting-rebaselining/nfr-requirements/nfr-requirements.md`
- [x] `.../u8-reporting-rebaselining/nfr-requirements/tech-stack-decisions.md`
