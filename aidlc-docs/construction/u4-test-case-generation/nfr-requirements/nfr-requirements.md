# NFR Requirements — U4 Test Case Generation

**Phase**: CONSTRUCTION | **Unit**: U4 | **Stage**: NFR Requirements
**Version**: 1.0 | **Date**: 2026-08-30

---

## 1. Inherited, Unchanged

OD-01 to OD-04, the eight Resiliency decision points, the tech stack, and the project
NFRs owned by U1, U2, U3 and U7. **Nothing re-opened.**

**Three inherited budgets are first genuinely exercised here.** U1 benchmarked them on
a synthetic corpus; U4 is where real generation populates the buckets and the indexes:

| Budget | Status before U4 | Status after |
|---|---|---|
| NFR-PRF-01 single-case operation | Measured on synthetic data | Measured on generated data |
| NFR-PRF-03 indexed de-duplication | 8 candidates from 10,000, synthetic | Real bucket distribution |
| NFR-SCL-02 thousands of cases | Provisioned for | Produced |

**U4 owns two project NFRs**, shared with U5: NFR-SEC-10 (confidentiality) and
NFR-SEC-11 (synthetic test data). Both are about what test data may contain, and U4 is
where test data is first written.

---

## 2. Performance

| ID | Requirement | Budget | Measurement |
|---|---|---|---|
| U4-NFR-PRF-01 | A 200-case batch commits at a 6,000-case corpus | < 10 s | Benchmark |
| U4-NFR-PRF-02 | Duplicate candidate selection per case | < 50 ms | Benchmark, index asserted |
| U4-NFR-PRF-03 | View emission for one feature at 100 cases | < 2 s | Benchmark |
| U4-NFR-PRF-04 | Full view re-emission, 150 features | < 60 s | Benchmark |
| U4-NFR-PRF-05 | Matrix construction at 6,000 cases | < 30 s | Benchmark |
| U4-NFR-PRF-06 | Only features a batch touched are re-emitted | Call counting |

**Ten seconds, not thirty.** The operator waits for a batch interactively, and ten
seconds is roughly where a wait stops feeling like a response and starts feeling like a
hang. Thirty would be comfortable for the implementation and uncomfortable for the
person.

**Not two seconds.** Reaching it would mean batching inserts in ways that complicate
the all-or-nothing guarantee — and the guarantee is worth more than eight seconds.

**U4-NFR-PRF-06 exists because the obvious implementation is wrong.** Re-emitting all
150 features after every batch would dominate the batch time and rewrite 148 files
that did not change, which also defeats hand-edit detection by touching files the
operator never asked about.

---

## 3. Scalability

| ID | Requirement | Measurement |
|---|---|---|
| U4-NFR-SCL-01 | A corpus of 6,000 cases across 150 features | Benchmark |
| U4-NFR-SCL-02 | Remain within budget at 10,000 cases | Benchmark headroom |
| U4-NFR-SCL-03 | A batch is capped at 200 cases, configurable | Asserted |
| U4-NFR-SCL-04 | No operation holds the whole corpus in memory | Streamed queries |
| U4-NFR-SCL-05 | Matrix construction streams rather than building a graph | Memory flat with corpus size |

---

## 4. Reliability

| ID | Requirement | Measurement |
|---|---|---|
| U4-NFR-REL-01 | A batch commits entirely or not at all | Asserted |
| U4-NFR-REL-02 | No identifier is allocated when a batch is rejected | Asserted |
| U4-NFR-REL-03 | Every failure in a rejected batch is reported together | Asserted |
| U4-NFR-REL-04 | A hand-edited view is never overwritten | Asserted |
| U4-NFR-REL-05 | Regeneration of an unchanged case keeps its identifier | Asserted |
| U4-NFR-REL-06 | An obsolete case never yields its identifier to a replacement | Asserted |
| U4-NFR-REL-07 | Migration 005 ships a tested reverse | `verify_reversibility` |

**U4-NFR-REL-02 guards a rule that is easy to break for convenience.** Allocating
identifiers before validation would simplify the code slightly. It would also mean an
identifier allocated and then released on rollback — and a released identifier might
be reissued, which BR-6.2 forbids because two cases sharing a number cannot both be
traced.

---

## 5. Security

| ID | Requirement | Source | Measurement |
|---|---|---|---|
| U4-NFR-SEC-01 | Test data matching a personal-data pattern is **rejected** unless drawn from a documented synthetic set | NFR-SEC-11 | Asserted per pattern |
| U4-NFR-SEC-02 | The rejection names the field and the pattern matched | NFR-SEC-11 | Asserted |
| U4-NFR-SEC-03 | Emitted views carry behaviour and expectations, not verbatim source documentation | NFR-SEC-10 | Review, asserted for length |
| U4-NFR-SEC-04 | Case and step content is stored verbatim and never executed | NFR-SEC-13 | No `eval` or `exec` in U4 |
| U4-NFR-SEC-05 | Views are written under `generated/`, which is gitignored | NFR-SEC-12 | Path assertion |

### Why rejection rather than a warning

The agent reads real Jira stories. A story citing a customer's actual email address is
exactly how real personal data reaches a test corpus — and that corpus is then
**pushed to a different repository**, which is where a confidentiality problem becomes
a disclosure.

The patterns checked are email addresses, phone numbers, national insurance and social
security formats, and card numbers. A value matching one is refused with the field and
the pattern named, so the agent can substitute a synthetic equivalent.

"Trust the agent, the instructions already say synthetic data only" is precisely the
class of rule this system exists to distrust: one the model is asked to follow, over
6,000 cases, across many sessions. The traceability rule is enforced by the schema for
the same reason.

**The false-positive cost is one substitution.** The false-negative cost is a real
person's data in a repository the test team pushes to CI.

---

## 6. Maintainability

| ID | Requirement | Measurement |
|---|---|---|
| U4-NFR-MNT-01 | The view format is stable, so re-emission produces byte-identical output for unchanged content | Asserted |
| U4-NFR-MNT-02 | Views state that they are generated and that edits do not change the corpus | Asserted |
| U4-NFR-MNT-03 | U4 contains no de-duplication algorithm, no classification list and no identifier scheme | Source inspection |

**U4-NFR-MNT-03 matters more here than anywhere.** U4 touches six domain components,
and every one of them is a candidate for a convenience copy. A local similarity check
"just for the batch", a quick automatability guess before calling D6 — either would
drift, and both would produce plausible results while doing so.

---

## 7. Project NFR Ownership

| Project NFR | Owner | How U4 serves it |
|---|---|---|
| NFR-SEC-10 Confidentiality | **U4**, with U5 | U4-NFR-SEC-03, -05 |
| NFR-SEC-11 Synthetic test data | **U4**, with U5 | U4-NFR-SEC-01, -02 |

---

## 8. Extension Compliance

**Security Baseline**: SECURITY-11 (secure design) served by U4-NFR-SEC-01 and -03;
SECURITY-13 by -SEC-04. **No blocking findings.**

**Resiliency Baseline**: RESILIENCY-12 inherited; migration 005 triggers the existing
rehearsal requirement. **No blocking findings.**

**Property-Based Testing (partial)**: PBT-03 extended with the 10 U4 properties,
including "nothing is allocated when a batch is rejected". **No blocking findings.**

---

## 9. Open Items

**None.** AS-02 remains outstanding from U1 and is unaffected.
