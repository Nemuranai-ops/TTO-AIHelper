# Functional Design Plan — U1 Core Platform

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION
**Unit**: U1 Core Platform
**Stage**: Functional Design
**Created**: 2026-08-29T09:01:00Z
**Status**: APPROVED 2026-08-29T09:15:00Z - all recommendations accepted

---

## Unit Context

**Responsibility**: the domain kernel, port protocols, SQLite schema and repositories, platform
services, and the MCP server. Everything the other seven units stand on.

**Components** (20): D1-D8 domain, P1-P3 ports, A1-A2 SQLite, X1-X5 platform, M1-M2 MCP.

**Stories** (7): US-ENB-01 through US-ENB-06, US-TRC-01.

**Boundary**: U1 knows what a test case *is* and what makes one valid. It does not know how one is
produced.

---

## Why this stage matters more for U1 than for any other unit

Application Design deliberately deferred **five business rules** to Functional Design
(`application-design.md` §8). All five live in domain components, and all five domain components
are in U1. They are:

| Rule | Component | Why it was deferred |
|---|---|---|
| Similarity threshold and normalisation | D4 | Determines what counts as a duplicate — a policy question, not a structural one |
| Coverage depth policy per technique | D2 | Determines how many cases each requirement yields |
| Commit-to-key selection when candidates conflict | D3 | Determines the strength of derived traceability |
| Risk rating factors and weights | D6 | Determines where coverage effort concentrates |
| Automatability classification criteria | D6 | Determines the manual/automated split |

**These five rules set the character of the whole corpus.** The similarity threshold alone is the
difference between 4,000 cases and 8,000. They are decided here, once, and every other unit inherits
them.

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis. Tell me when done.

## Question 1 — Business Rules: duplicate detection (D4)
Two things must be decided: what is compared, and how similar is too similar.

A) **Normalise to lowercase, collapse whitespace, strip terminal punctuation, keep step order,
compare the concatenated action-plus-expected text as token shingles. Exact match (1.0) rejects as
identical; 0.90 or above rejects as near-duplicate; a differing equivalence class always counts as
material regardless of score.** **(Recommended — 0.90 catches genuine restatements while leaving
room for cases that differ only in one meaningful word, such as "rejects" versus "accepts")**

B) Same normalisation, **stricter threshold of 0.95** — fewer false rejections, more near-duplicates
survive into the corpus.

C) Same normalisation, **looser threshold of 0.85** — a tighter corpus, at the risk of rejecting
cases that genuinely differ.

D) **Compare structure rather than text** — same step count, same action verbs, same assertion
types. Robust to wording, but blind to two cases that differ only in the value being asserted.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 2 — Business Rules: coverage depth per technique (D2)
How many cases should each test design technique yield?

A) **ISTQB-standard depth**: equivalence partitioning yields one case per valid class and one per
invalid class; boundary value analysis yields three values per boundary (just below, at, just
above); decision tables yield one case per rule; state transitions yield 0-switch coverage, every
valid transition once, plus every explicitly forbidden transition. **(Recommended — it is the
defensible default, and "we applied ISTQB-standard depth" is an answer that survives an audit)**

B) **Reduced depth**: two values per boundary (at, and just outside); decision tables collapsed by
condition significance; 0-switch on valid transitions only. Roughly 30-40% fewer cases.

C) **Deep**: three values per boundary plus pairwise combination across independent parameters;
1-switch state coverage. Substantially more cases, and the combinatorial growth needs watching.

D) **Risk-tiered**: deep for high-risk requirements, standard for medium, reduced for low — with the
tier taken from the D6 risk rating.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 3 — Business Rules: commit-to-key selection (D3)
When several commits touching a file carry different Jira keys, which key wins?

A) **The most recent commit that both carries a key and whose key is in the ingested set. Tie-break
by lines changed in that file, then by commit recency. Retain every alternative, record the
selection basis, and search back no further than a configurable window (default 180 days).**
**(Recommended — recency is the best available proxy for current intent, and the window stops a
five-year-old refactor from becoming the provenance of today's behaviour)**

B) **The commit that changed the most lines in that file**, regardless of age — provenance by
contribution rather than recency.

C) **The oldest key**, on the reasoning that it represents the story that introduced the behaviour.

D) **Refuse to choose.** If more than one candidate exists, route the behaviour to the gap report
for a human to resolve.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 4 — Business Rules: risk rating (D6)
How should the four risk factors combine?

A) **Each factor scored 1-5, weighted: business criticality x3, complexity x2, integration surface
x2, change frequency x1. Normalise to 0-100 and band as Low (0-25), Medium (26-50), High (51-75),
Critical (76-100). An unavailable factor is removed from the denominator and the rating is flagged
as partial — never scored zero.** **(Recommended — criticality dominating is correct, and the
partial-rating rule prevents a missing input from reading as a low risk)**

B) **Equal weighting** across all four factors — simpler, but treats a change-frequency signal as
equal to business criticality.

C) **Criticality-dominant**: criticality alone sets the band, with the other three able to shift it
one band up or down.

D) **Highest-factor-wins**: the band is set by whichever factor scores highest. Conservative, and
tends to rate everything High.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 5 — Business Rules: automatability classification (D6)
How should a case be judged automatable?

A) **An ordered decision list, first match wins.** Manual-only if it requires visual or aesthetic
judgement, an external manual step, data that cannot be provisioned, or is exploratory by nature.
Automatable if it is an API case with a known contract, or a UI case whose every referenced element
has a verified locator. Needs-review otherwise. **(Recommended — an ordered list is auditable and
reproducible; every verdict traces to the rule that produced it)**

B) **Score-based** — weight the same signals and threshold the total. Handles mixed cases more
smoothly, at the cost of a verdict nobody can explain in one sentence.

C) **Automatable by default**, manual only when explicitly excluded — maximises the automated share
and pushes the judgement to review.

D) **Manual by default**, automatable only when explicitly qualified — conservative, and would leave
much of the corpus unautomated.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 6 — Domain Model: identifier scheme (D5)
What form should test case identifiers take?

A) **`TC-<FEATURE_SLUG>-<00001>`, sequenced per feature.** Readable, sorts sensibly, and a
identifier tells you where the case belongs. Requirements use `TR-`, coverage items `CI-`,
automated tests `AT-`. **(Recommended — at 6,000 cases, an identifier that carries its feature is
worth a great deal during review)**

B) **`TC-000001` globally sequential** — simplest allocation, no feature coupling, but an identifier
tells you nothing.

C) **UUIDs** — no allocation coordination at all, at the cost of being unreadable and unsortable.

D) **Content-derived hash identifiers** — stable across regeneration by construction, but they
change when the case is edited, which breaks the stability requirement in FR-TCG-04.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 7 — Error Handling: code taxonomy (X1)
How granular should the error code set be?

A) **Two families, roughly 15 codes.** `REJECTED_*` for agent-fixable input problems
(`REJECTED_NO_STEPS`, `REJECTED_NO_JIRA_KEY`, `REJECTED_DUPLICATE`, `REJECTED_GATE_CLOSED`,
`REJECTED_UNKNOWN_JIRA_KEY`, `REJECTED_SELF_SUPPLIED_ID`, `REJECTED_ALREADY_COMPLETE`,
`REJECTED_ROLE_NOT_PERMITTED`) and `FAILED_*` for system problems (`FAILED_DB_UNAVAILABLE`,
`FAILED_MCP_UNREACHABLE`, `FAILED_MIGRATION`, `FAILED_TIMEOUT`, `FAILED_LOCKED`,
`FAILED_TEMPLATE_RENDER`, `FAILED_INTERNAL`). **(Recommended — specific enough that the agent can
act on the code alone, without a message-parsing step)**

B) **Minimal — four codes**: `REJECTED`, `FAILED`, `NOT_FOUND`, `UNAUTHORISED`. The agent reads the
message to understand what happened, which makes its behaviour depend on prose.

C) **Fine-grained — one code per validation rule**, 40 or more. Maximum precision, at a maintenance
cost every time a rule changes.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 8 — Integration Points: retry policy (X4)
How should transient external failures be handled?

A) **Three attempts, exponential backoff at 1s, 2s and 4s with jitter, only for transient classes —
connection error, timeout, HTTP 429, HTTP 5xx. Never retry 4xx authentication or validation
failures. On exhaustion, fail the unit and continue the run.** **(Recommended — a 429 that is
retried immediately makes the situation worse, and jitter matters because ingestion runs many
requests in a burst)**

B) **Five attempts with longer backoff** (1s to 16s) — better for a flaky network, slower to
surface a genuine outage.

C) **Single retry** — fastest failure surfacing, least tolerance for ordinary transient errors.

D) **No retry** — every failure surfaces immediately for the operator to judge.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

# Execution Checklist

Executed after this plan is approved.

## Phase 1: Domain Entities

- [x] 1.1 Define all 18 entities with attributes, types and cardinalities
- [x] 1.2 Define value objects and their construction-time invariants
- [x] 1.3 Define entity relationships and the referential rules between them
- [x] 1.4 Define the identifier scheme per the Question 6 answer
- [x] 1.5 Define soft-delete and audit semantics
- [x] 1.6 Map each §10.3 integrity rule to its enforcing SQLite constraint
- [x] 1.7 Write `domain-entities.md`

## Phase 2: Business Rules

- [x] 2.1 Specify duplicate detection: normalisation steps and threshold, per Question 1
- [x] 2.2 Specify coverage depth per technique, per Question 2
- [x] 2.3 Specify commit-to-key selection, per Question 3
- [x] 2.4 Specify risk rating factors, weights and bands, per Question 4
- [x] 2.5 Specify automatability classification, per Question 5
- [x] 2.6 Specify identifier allocation and stability rules
- [x] 2.7 Specify integrity validation rules and their rejection codes
- [x] 2.8 Specify traceability link typing and Jira key resolution
- [x] 2.9 Specify impact classification rules for delta runs
- [x] 2.10 Write `business-rules.md`

## Phase 3: Business Logic Model

- [x] 3.1 Model the domain kernel's algorithms: derivation, resolution, comparison, allocation
- [x] 3.2 Model the validation pipeline and its ordering
- [x] 3.3 Model transaction and unit-of-work semantics
- [x] 3.4 Model the error taxonomy per Question 7 and the retry policy per Question 8
- [x] 3.5 Model data flow through the domain kernel
- [x] 3.6 Identify the property-based test surface with the specific properties per component
- [x] 3.7 Write `business-logic-model.md`

## Phase 4: Validation

- [x] 4.1 Verify all 7 U1 stories are served by the design
- [x] 4.2 Verify all five deferred business rules from `application-design.md` §8 are now specified
- [x] 4.3 Verify every §10.3 integrity rule has an enforcement point
- [x] 4.4 Verify the design remains technology-agnostic — no infrastructure concerns
- [x] 4.5 Verify Security and Resiliency extension applicability at this stage
- [x] 4.6 Validate content per `common/content-validation.md`
- [x] 4.7 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `aidlc-docs/construction/u1-core-platform/functional-design/domain-entities.md`
- [x] `aidlc-docs/construction/u1-core-platform/functional-design/business-rules.md`
- [x] `aidlc-docs/construction/u1-core-platform/functional-design/business-logic-model.md`

**No `frontend-components.md`**: U1 has no UI. The system's only user interface is the VS Code
Copilot chat surface, which is configuration in U7 rather than frontend code in any unit.
