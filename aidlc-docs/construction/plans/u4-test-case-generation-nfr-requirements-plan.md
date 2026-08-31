# NFR Requirements Plan — U4 Test Case Generation

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U4 | **Stage**: NFR Requirements
**Created**: 2026-08-30T12:06:00Z
**Status**: APPROVED 2026-08-30T12:15:00Z - all recommendations accepted

---

## Where the volume finally lands

Every unit so far has prepared for 6,000 cases. U4 produces them, which makes this the
stage where several inherited budgets are first genuinely exercised:

| Inherited budget | First real test |
|---|---|
| NFR-PRF-01 single-case operation < 200 ms | U1 benchmarked it on synthetic data; U4 generates the real thing |
| NFR-PRF-03 indexed de-duplication | U1 measured 8 candidates from 10,000; U4 is where the buckets are actually populated |
| NFR-SCL-02 thousands of cases | U4 is what makes it thousands |

**U4 owns two project NFRs**: NFR-SEC-10 and NFR-SEC-11 (confidentiality and synthetic
test data), shared with U5. Those are about what test data may contain, and U4 is where
test data is first written.

**Four questions.**

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Performance: the batch commit budget

A 200-case batch writes cases, steps, data, links and integrity sentinels — roughly
1,600 inserts — inside one transaction, after running six domain components over each
case.

A) **Under 10 seconds for a 200-case batch at a 6,000-case corpus.** The operator
waits for this interactively, and 10 seconds is the boundary at which a wait stops
feeling like a response. **(Recommended)**

B) **Under 30 seconds** — comfortable headroom, and long enough that an operator
starts wondering whether it has hung.

C) **Under 2 seconds** — would require batching the inserts in ways that complicate
the all-or-nothing guarantee, for a saving the operator will not notice.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 2 — Performance: view emission at full corpus

150 features, 6,000 cases, two files each.

A) **Emit only the features a batch touched, not the whole corpus.** A full re-emission
is available on request and budgeted at under 60 seconds. **(Recommended — re-emitting
150 features after every batch would dominate the batch time and rewrite 148 files that
did not change)**

B) **Emit everything after every batch.** Simplest, and it makes every batch pay for
the whole corpus.

C) **Emit on request only**, never automatically. Fewest writes, and the views drift
from the corpus between requests.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 3 — Security: what test data may contain

NFR-SEC-11 requires synthetic test data. U4 is where test data is first written.

A) **Reject a case whose test data matches a personal-data pattern — email address,
phone number, national insurance or social security format, card number — unless the
value is drawn from a documented synthetic set.** The rejection names the field and
the pattern. **(Recommended — the agent reads real Jira stories, and a story citing a
customer's actual email is exactly how real data reaches a test corpus that is then
pushed to another repository)**

B) **Warn but accept**, reporting the suspected values.

C) **Trust the agent**, since the instructions already say synthetic data only.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 4 — Scalability: matrix construction at full corpus

The traceability matrix traverses every link. At 6,000 cases there are at least 6,000
links, plus the requirement links U3 wrote.

A) **Build it in SQL, streaming rows into the output, budgeted under 30 seconds.** No
in-memory graph. **(Recommended — the same reasoning as U1's report generation:
aggregation is what SQLite is good at, and memory stays flat regardless of corpus size)**

B) **Build an in-memory graph**, which is simpler to reason about and holds the whole
link set.

C) **Materialise it into a table** on each batch. Fast reads, and a consistency
obligation the functional design already declined.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

# Execution Checklist

## Phase 1: NFR Determination

- [x] 1.1 Record performance requirements: batch commit, view emission, matrix
- [x] 1.2 Record scalability requirements at 6,000 cases
- [x] 1.3 Record reliability requirements: batch atomicity, allocation safety
- [x] 1.4 Record security requirements: synthetic data enforcement, confidentiality
- [x] 1.5 Record maintainability requirements for the view format
- [x] 1.6 Confirm every inherited decision applies unchanged
- [x] 1.7 Write `nfr-requirements.md`

## Phase 2: Tech Stack

- [x] 2.1 Confirm the U1 stack applies, and record any addition
- [x] 2.2 Record the view rendering approach
- [x] 2.3 Write `tech-stack-decisions.md`

## Phase 3: Validation

- [x] 3.1 Verify every U4 NFR requirement is measurable
- [x] 3.2 Verify the two U4-owned project NFRs are addressed
- [x] 3.3 Verify Security and Resiliency applicability
- [x] 3.4 Validate content per `common/content-validation.md`
- [x] 3.5 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `.../u4-test-case-generation/nfr-requirements/nfr-requirements.md`
- [x] `.../u4-test-case-generation/nfr-requirements/tech-stack-decisions.md`
