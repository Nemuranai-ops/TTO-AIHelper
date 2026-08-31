# NFR Requirements — U8 Reporting and Re-baselining

**Phase**: CONSTRUCTION | **Unit**: U8 | **Stage**: NFR Requirements
**Version**: 1.0 | **Date**: 2026-08-31

---

## 1. Inherited, Unchanged

OD-01 to OD-04, the eight Resiliency decision points, the tech stack, and the project
NFRs owned by U1 through U7. **Nothing re-opened**, in the last unit as in every other.

**U8 owns NFR-PRF-02 outright** — "a full report at 6,000 cases in under 30 seconds" —
and shares NFR-SEC-10 with U4, U5 and U6.

### The budget that has waited since U1

NFR-PRF-02 was provisioned for at U1 and measured against one synthetic aggregation
(0.003 s). U8 assembles the whole report over a real corpus for the first time.

| Budget | Before U8 | After |
|---|---|---|
| NFR-PRF-02 full report | One aggregation, synthetic | **The whole report, real corpus** |
| NFR-SCL-03 corpus-wide queries | Provisioned | Exercised |
| NFR-REL-04 per-source isolation | Used in ingestion | Used where losing a source is permanent |

---

## 2. Performance

| ID | Requirement | Budget | Measurement |
|---|---|---|---|
| U8-NFR-PRF-01 | The full report set at 6,000 cases, **end to end** | < 30 s | Benchmark |
| U8-NFR-PRF-02 | Any single report at 6,000 cases | < 5 s | Benchmark |
| U8-NFR-PRF-03 | Delta impact mapping at 6,000 cases and 500 changes | < 10 s | Benchmark |
| U8-NFR-PRF-04 | Baseline lookup | < 100 ms | Single indexed query |
| U8-NFR-PRF-05 | Change detection is bounded by U1's retry and timeout | Inherited | Asserted |

**End to end means query, render and write.** Measuring the query alone would let a
slow renderer pass a budget it does not meet — and the operator is waiting for the
file, not for the `SELECT`.

**Five seconds per report is the figure that matters day to day.** Thirty seconds is
the project NFR for the whole set, which an operator runs before a review; a single
report is run repeatedly while the baseline is being built.

---

## 3. Scalability

| ID | Requirement | Measurement |
|---|---|---|
| U8-NFR-SCL-01 | 6,000 cases, 150 features, ~1,200 coverage items | Benchmark |
| U8-NFR-SCL-02 | Remain within budget at 10,000 cases | Benchmark headroom |
| U8-NFR-SCL-03 | Aggregation happens in SQL, never by counting in Python | Source inspection |
| U8-NFR-SCL-04 | Report rows are streamed to the file, never wholly materialised | Streamed write |
| U8-NFR-SCL-05 | Delta detection is bounded by the commit and issue caps U3 set | Inherited |

**U8-NFR-SCL-03 is the requirement that makes the budget reachable.** Counting in
Python would read the whole corpus to produce 150 rows — the same objection that shaped
U4's volume query, restated because U8 has more places to get it wrong.

---

## 4. Reliability

| ID | Requirement | Measurement |
|---|---|---|
| U8-NFR-REL-01 | A section that cannot be computed never fails the report | Property |
| U8-NFR-REL-02 | A `not_available` section always carries a reason and a producing stage | Property |
| U8-NFR-REL-03 | Per-source isolation in delta detection | Asserted |
| U8-NFR-REL-04 | **A partial delta run does not advance the baseline** | Asserted |
| U8-NFR-REL-05 | Retirement changes only the three obsolete columns | Property |
| U8-NFR-REL-06 | A `requires-update` case is never modified by a delta run | Property |
| U8-NFR-REL-07 | Report rendering is byte-stable for an unchanged corpus | Property |
| U8-NFR-REL-08 | Migration 007 ships a tested reverse | `verify_reversibility` |

### U8-NFR-REL-04 is the most consequential requirement in this unit

Advancing the baseline after a partial detection would make the undetected changes
**invisible for ever**: the next run compares from the newer head, so everything in the
window the failed source covered is silently skipped.

That is not a degraded run — it is a permanently wrong corpus, and **nothing downstream
would ever reveal it**. Every other failure in this system announces itself; this one
would not, which is why it gets its own requirement rather than being folded into
isolation.

The rule is simple to state and easy to lose: **the baseline advances only when every
source was reached.**

---

## 5. Security

| ID | Requirement | Source | Measurement |
|---|---|---|---|
| U8-NFR-SEC-01 | Reports carry behaviour and identifiers, not verbatim source documentation | NFR-SEC-10 | Review, asserted for length |
| U8-NFR-SEC-02 | Reports are written under `generated/reports/`, which is gitignored | NFR-SEC-12 | Path assertion |
| U8-NFR-SEC-03 | A report never contains a credential or personal-data literal | NFR-SEC-10, -11 | L9 and L13 over rendered output |
| U8-NFR-SEC-04 | Delta detection is read-only against Bitbucket and Jira | C-05, C-06 | **The source ports declare no write method** |
| U8-NFR-SEC-05 | Report content is stored verbatim and never executed | NFR-SEC-13 | No `eval`, no template execution |

### Why reports are the artefact most worth restricting

**A report is the thing most likely to be forwarded.** A coverage report goes to a Test
Lead, who sends it to a programme manager, who attaches it to a status pack. A generated
view stays in a repository; a report travels.

So the rule U4 applied to its views applies here with more force: state the behaviour
and the identifier, not three paragraphs of the internal Confluence page the requirement
came from.

Redacting all source text was the alternative and would be safe and useless — a gap
report listing thirty requirement identifiers with no statements is one nobody can act
on, and an unusable report is not a security control, it is a report nobody reads.

### U8-NFR-SEC-03 runs both scanners over the output

L9 for personal data, L13 for credentials, over the rendered report rather than the
corpus. Both refused their respective content upstream; this catches anything that
arrived by a path neither covers — a requirement statement ingested before L9 existed,
or a gap subject quoting a Jira comment.

**Last line, same as U6's re-scan**: it costs one pass over text already in memory.

---

## 6. Maintainability

| ID | Requirement | Measurement |
|---|---|---|
| U8-NFR-MNT-01 | U8 contains no impact-classification logic | Import contracts |
| U8-NFR-MNT-02 | U8 does not rebuild the traceability matrix | Source inspection |
| U8-NFR-MNT-03 | Every rendered figure carries its derivation | Property |
| U8-NFR-MNT-04 | No figure is composed by the model | FR-RPT-05, source inspection |
| U8-NFR-MNT-05 | S9 has no method creating a requirement or a case | Source inspection |

**U8-NFR-MNT-01 matters because this is the eighth unit.** Seven have now resisted
copying a domain algorithm for local convenience, and the eighth has the strongest
excuse — D8's classification is four booleans and a decision list, and reimplementing
it in the delta service would look like clarity.

It would drift, and the drift would show up as a case the report calls obsolete and the
corpus calls active.

---

## 7. Project NFR Ownership

| Project NFR | Owner | How U8 serves it |
|---|---|---|
| NFR-PRF-02 Full report < 30 s | **U8** | U8-NFR-PRF-01 |
| NFR-SEC-10 Confidentiality | Shared with U4, U5, U6 | U8-NFR-SEC-01, -02 |
| NFR-REL-04 Per-source isolation | Shared with U2 | U8-NFR-REL-03, -04 |

---

## 8. Extension Compliance

**Security Baseline**: SECURITY-11 via U8-NFR-SEC-01 and -03; SECURITY-12 via -SEC-02.
**No blocking findings.**

**Resiliency Baseline**: RESILIENCY-07 (degrade rather than fail) served by U8-NFR-REL-01
— its third use, after U6's skipped tier and U2's partial ingestion. RESILIENCY-12 via
migration 007's reverse. **No blocking findings.**

**Property-Based Testing (partial)**: PBT-03 extended with the 9 U8 properties, two of
which pin the unit boundary. **No blocking findings.**

---

## 9. Open Items

**None.** AS-02 remains outstanding from U1, unaffected, and unchanged since — it is a
verification action for the operator, not a design question.
