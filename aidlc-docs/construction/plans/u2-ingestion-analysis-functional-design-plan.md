# Functional Design Plan — U2 Ingestion and Analysis

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U2 | **Stage**: Functional Design
**Created**: 2026-08-29T16:41:00Z
**Status**: APPROVED 2026-08-29T16:55:00Z - all recommendations accepted

---

## Unit Context

**Responsibility**: turn declared resources into stored artefacts, and artefacts into
the application model. U2 owns everything that reads from outside the workspace — no
other unit touches an external MCP server.

**Components**: S1 IngestionService, S2 AnalysisService, A3 AtlassianSourceAdapter,
A4 BitbucketSourceAdapter, A5 DesignAssetAdapter, A6 ResourceManifestAdapter.

**Stories** (8): US-ING-01 to US-ING-04, US-ANA-01 to US-ANA-04.

**Depends on**: U1 (complete). Uses the ports, `unit_of_work`, `Result`, retry and
isolation. U7's gates apply.

---

## The decision that shapes this unit

Application Design Q3 put bulk ingestion in the toolchain rather than the agent: at
100-500 Jira stories, routing every issue body through the model's context window is
slow, expensive, and adds a transcription step between source and storage.

That splits U2's work in two, and the split runs through every question below.

| Produced by the toolchain (deterministic) | Produced by the agent (needs judgement) |
|---|---|
| Fetching, normalising, hashing every artefact | What constitutes a feature |
| Extracting HTTP endpoints and OpenAPI specs | Which screens belong to which journey |
| Parsing the Figma filename convention | Reading a business rule out of prose |
| Detecting that two sources disagree | Deciding what a screen's states mean |
| The entire API model | Everything about the UI model |

**Detecting a discrepancy is mechanical; resolving one is not.** U2 records
disagreements and never settles them.

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Business Rules: `resources.md` type inference

Q14 chose a plain link list, with type inferred from the URL or path pattern. What
should the inference rules be?

A) **Ordered pattern rules, first match wins, each recording which rule fired.**
Jira browse and REST URLs, Confluence page and space URLs, Bitbucket repository URLs,
`.yaml`/`.json` paths ending in a recognisable OpenAPI name, and local directory
paths. Anything unmatched is `unclassified` and reported. **(Recommended — recording
which rule fired makes a wrong inference diagnosable rather than mysterious)**

B) **Same rules, but without recording which matched.** Simpler storage, and a
misclassified link becomes guesswork to debug.

C) **Require an explicit type prefix** in `resources.md` — `jira: PROJ-1`. Removes
inference entirely, and contradicts Q14's plain-link-list decision.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 2 — Business Rules: detecting a thin Jira story

FR-ING-03 stores `detail_level` as `full` or `low`. A thin story is worth flagging at
ingestion, because otherwise it resurfaces later as thin coverage nobody can explain.

A) **Low when the description is under 200 characters and there are no acceptance
criteria.** Both conditions, so a short story with clear criteria is not penalised.
**(Recommended — acceptance criteria are what requirements are actually derived from;
a long description without them is still thin for our purposes)**

B) **Low when acceptance criteria are absent**, regardless of description length.

C) **Low when the description is under 200 characters**, regardless of criteria.

D) **Do not classify** — store everything as `full` and let the analyst notice.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 3 — Business Rules: what the content hash covers

FR-ING-08 and FR-ING-10 use a content hash to skip unchanged artefacts. What goes
into it?

A) **Content only, not metadata.** A Jira issue whose label changed but whose text did
not is unchanged for our purposes. **(Recommended — including metadata means a
harmless field update re-ingests and re-analyses everything downstream, and the delta
pipeline would report churn that changed nothing testable)**

B) **Content plus metadata.** Any field change is a change. Safest, and noisy.

C) **Content plus only the metadata that affects testing** — status, acceptance
criteria fields, parent. Precise, and the list needs maintaining as Jira configuration
changes.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 4 — Business Rules: Figma filename parsing

Q15 chose `<feature>__<screen>__<state>.png` with an optional sidecar manifest.

A) **Split on double underscore. Two segments means feature and screen with state
defaulting to `default`; three means all present; anything else is unassociated and
reported. The manifest overrides any parsed value, field by field.**
**(Recommended — field-by-field override lets the manifest correct one attribute
without restating the others)**

B) **Require exactly three segments.** Stricter, and it rejects the common
`feature__screen.png` for no benefit.

C) **Manifest wins wholesale** where an entry exists, ignoring the filename entirely.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 5 — Business Rules: API model derivation

FR-ANA-04 builds the API model from `bitbucket_endpoints` and any OpenAPI spec. The
two can disagree.

A) **Merge, preferring the spec for shapes and the code for existence.** An endpoint
in code but not the spec is recorded with `shape_source=inferred`; one in the spec but
not the code is recorded as a discrepancy and **not** treated as existing.
**(Recommended — code is what runs. A spec entry with no implementation would
generate tests for an endpoint that returns 404)**

B) **Prefer the spec entirely.** Cleaner shapes, and it fabricates endpoints.

C) **Prefer the code entirely.** Never wrong about existence, and it discards
request/response shapes the spec provides.

D) **Keep both models separately** and let later stages decide.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 6 — Business Rules: what counts as a discrepancy

FR-ANA-08 records disagreements between sources rather than resolving them. Recording
everything would bury the signal.

A) **Record when two sources make incompatible claims about the same testable
thing**: an endpoint in the spec but not the code, a screen in Figma absent from the
live application, a rule stated in Jira that contradicts the implementation, a status
code documented but not returned. Not: wording differences, formatting, or ordering.
**(Recommended — the test is whether a tester would write a different test depending
on which source they believed)**

B) **Record any difference between sources**, including wording. Exhaustive and
unreadable.

C) **Record only code-versus-documentation conflicts**, ignoring design-versus-live.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 7 — Error Handling: partial ingestion

NFR-REL-04 isolates per-resource failures. What should a partially failed ingestion
report, and may downstream stages proceed?

A) **Report successes, skips, failures and unclassified entries together, and let the
operator decide whether to proceed.** The ingest gate is theirs to approve; a partial
ingestion is a fact for them to weigh, not a verdict for the system to issue.
**(Recommended — the system cannot know whether the missing repository mattered)**

B) **Refuse to complete the unit** if any resource failed, forcing a clean run.

C) **Complete silently**, reporting only successes.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

# Execution Checklist

## Phase 1: Business Rules

- [x] 1.1 Specify resource type inference per Question 1
- [x] 1.2 Specify Jira and Confluence normalisation, including `detail_level` per Question 2
- [x] 1.3 Specify content hashing per Question 3
- [x] 1.4 Specify Figma filename and manifest handling per Question 4
- [x] 1.5 Specify API model derivation and merge per Question 5
- [x] 1.6 Specify discrepancy detection per Question 6
- [x] 1.7 Specify the agent payload contracts for feature model, journeys, rules and UI model
- [x] 1.8 Specify partial-failure reporting per Question 7
- [x] 1.9 Write `business-rules.md`

## Phase 2: Domain Entities

- [x] 2.1 Define the normalised source record shape per source type
- [x] 2.2 Define the discrepancy record and its relationship to existing entities
- [x] 2.3 Define the ingestion report structure
- [x] 2.4 Confirm whether a schema migration is needed, and specify it if so
- [x] 2.5 Write `domain-entities.md`

## Phase 3: Business Logic Model

- [x] 3.1 Model the ingestion pipeline with its isolation boundaries
- [x] 3.2 Model the reasoned/derived split at method level
- [x] 3.3 Model the API derivation and merge algorithm
- [x] 3.4 Model the Figma parsing algorithm
- [x] 3.5 Model interaction with U1 ports and U7 gates
- [x] 3.6 Identify the U2 property-based test surface
- [x] 3.7 Write `business-logic-model.md`

## Phase 4: Validation

- [x] 4.1 Verify all 8 U2 stories are served
- [x] 4.2 Verify FR-ING-01 to FR-ING-10 and FR-ANA-01 to FR-ANA-08 are covered
- [x] 4.3 Verify the read-only posture is preserved structurally
- [x] 4.4 Verify Security and Resiliency applicability
- [x] 4.5 Validate content per `common/content-validation.md`
- [x] 4.6 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `.../u2-ingestion-analysis/functional-design/domain-entities.md`
- [x] `.../u2-ingestion-analysis/functional-design/business-rules.md`
- [x] `.../u2-ingestion-analysis/functional-design/business-logic-model.md`

**No `frontend-components.md`**: U2 has no user interface. The operator interacts with
ingestion through U7's chat modes, which are already designed.
