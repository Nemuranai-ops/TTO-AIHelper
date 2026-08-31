# User Stories

**Project**: TTO Test Analyst Agent System (TAAS)
**Stage**: INCEPTION - User Stories
**Version**: 1.0
**Date**: 2026-08-28
**Breakdown**: Epic-based, aligned to the 7 pipeline stages plus cross-cutting epics
**Prioritisation**: Release-based
**Acceptance criteria**: Given/When/Then, including negative and error paths

---

## Contents

| Epic | Name | Stories | Primary persona |
|---|---|---|---|
| E1 | Input Sources | 4 | P1 Test Analyst |
| E2 | Analyse and Understand | 4 | P1 Test Analyst |
| E3 | Identify Testable Requirements | 3 | P1 Test Analyst |
| E4 | Establish Coverage Baseline | 5 | P3 Test Lead |
| E5 | Generate Test Cases | 6 | P1 Test Analyst |
| E6 | Generate Automation | 6 | P2 Automation Engineer |
| E7 | Handover Package | 3 | P2 Automation Engineer |
| E8 | Traceability | 4 | P3 Test Lead |
| E9 | Batch, State and Resumability | 4 | P1 Test Analyst |
| E10 | Incremental Re-baselining | 3 | P1 Test Analyst |
| E11 | Reporting | 3 | P3 Test Lead |
| E12 | Agent Layer | 4 | P1 Test Analyst |
| E13 | Technical Enablers | 6 | Indirect |
| | **Total** | **55** | |

---

## Releases

Stories are sequenced into three releases rather than ranked. Each release is a coherent,
demonstrable state of the system.

### R1 — Walking Skeleton

**Goal**: one feature, end to end, through all seven stages. Thin but complete.

The value of doing this first is that it exercises every seam in the architecture — the SQLite
schema, the MCP boundary, the traceability enforcement, the resumability, the Playwright emitter —
while the corpus is still small enough that a mistake costs an afternoon rather than a month. If
the walking skeleton is wrong, everything built on it is wrong, and R1 is where that is cheapest
to discover.

**Contains**: 29 stories (some split across releases). Single Jira story ingest, feature and API model, testable requirements,
a coverage model for one feature, structured test cases with enforced traceability, one Playwright
spec, an assembled project, operator-driven batching with resumable state, and the agent layer
needed to drive it.

### R2 — Production Baseline

**Goal**: full-scale capability across all declared inputs, at the volume the requirements assume.

**Contains**: 25 stories. Confluence and Figma ingest, live Playwright selector derivation, risk
rating, coverage depth from test design techniques, yield forecasting, de-duplication,
automatability classification, commit-derived traceability, the complete reporting set, handover
verification, and the scale and durability enablers.

### R3 — Sustaining

**Goal**: keep the baseline current as the application moves.

**Contains**: 4 stories. Delta detection across Bitbucket and Jira, impact classification, soft
retirement of obsolete cases with run history, and risk-based coverage reduction.

---

## Story Format

Each story states its release, personas, the priority carried over from `requirements.md`, and the
requirement identifiers it serves. Acceptance criteria cover the happy path, at least one negative
or boundary path, and at least one error path — the same standard this system is being built to
apply to the application under test.

---

# E1: Input Sources

**Goal**: every declared artefact is resolved, ingested, and recorded with provenance.
**Requirements served**: FR-ING-01 to FR-ING-10, NFR-PRF-04

---

### US-ING-01: Declare inputs in a resources file

**Release**: R1 | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-ING-01, FR-ING-02, FR-ING-09

**Story**: As a Test Analyst, I want to list every input as a plain link in `resources.md`, so that
I can point the system at a new application without learning a configuration format.

**Acceptance criteria**

- **AC1 (happy)**: Given a `resources.md` containing Jira, Confluence and Bitbucket URLs and a
  local folder path, when I run ingestion, then each entry is classified by type and recorded as a
  resource with its inferred type shown back to me.
- **AC2 (negative)**: Given a link whose type cannot be inferred from its URL or path pattern, when
  ingestion runs, then the system lists that link as unclassified and continues with the rest —
  it does not guess a type and does not silently skip it.
- **AC3 (negative)**: Given a `resources.md` containing a duplicate link, when ingestion runs, then
  the duplicate is recognised and recorded once.
- **AC4 (error)**: Given `resources.md` does not exist at the expected path, when ingestion runs,
  then the system reports the expected path and stops without creating partial state.
- **AC5**: Given any ingested artefact, when I ask where it came from, then the system names the
  resource entry, the source identifier, and the ingestion timestamp.

---

### US-ING-02: Ingest Jira issues and Confluence pages

**Release**: R1 (Jira), R2 (Confluence) | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-ING-03, FR-ING-04

**Story**: As a Test Analyst, I want Jira issues and Confluence pages pulled in with their full
detail, so that the system reasons from what was actually written rather than from a summary.

**Acceptance criteria**

- **AC1 (happy)**: Given a Jira issue key, when it is ingested, then key, type, summary,
  description, acceptance criteria, status, labels, parent or epic, and comments are all stored.
- **AC2 (happy)**: Given a JQL query or project key, when it is ingested, then every matching issue
  is retrieved across pagination boundaries with none dropped.
- **AC3 (happy)**: Given a Confluence page containing a table, when it is ingested, then the table
  is preserved as structured rows rather than flattened into prose.
- **AC4 (negative)**: Given a Jira issue with an empty description and no acceptance criteria, when
  it is ingested, then it is stored and flagged as low-detail, so that a thin story is visible
  rather than silently producing thin coverage later.
- **AC5 (error)**: Given the Atlassian MCP is unreachable or returns an error, when ingestion runs,
  then the failure is recorded against that resource, previously ingested artefacts remain intact,
  and the run continues with the remaining resources.
- **AC6 (error)**: Given an issue key that does not exist or is not permitted, when ingestion runs,
  then the system distinguishes "not found" from "not authorised" in its report.

---

### US-ING-03: Ingest Bitbucket repositories and the API surface

**Release**: R1 | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-ING-05, FR-ING-06

**Story**: As a Test Analyst, I want the repositories enumerated and their HTTP endpoints
extracted, so that the API surface is derived from the code rather than from documentation that
may be stale.

**Acceptance criteria**

- **AC1 (happy)**: Given declared Bitbucket repositories, when they are ingested, then branch, head
  commit, project key and slug are recorded for each, giving delta detection a baseline to compare
  against later.
- **AC2 (happy)**: Given a repository containing HTTP handlers, when endpoints are extracted, then
  each endpoint's method, route, file, line and defining symbol are recorded.
- **AC3 (happy)**: Given a repository containing an OpenAPI specification, when it is ingested, then
  the specification is recorded and associated with the endpoints it describes.
- **AC4 (negative)**: Given an endpoint present in the OpenAPI specification but absent from the
  code, or present in code but absent from the specification, when ingestion completes, then the
  discrepancy is recorded rather than one source silently winning.
- **AC5 (error)**: Given a repository the MCP server cannot read, when ingestion runs, then the
  failure is recorded against that repository and other repositories still ingest.

---

### US-ING-04: Ingest UI designs from the screenshot folder

**Release**: R2 | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-ING-07, FR-ING-08, FR-ING-10

**Story**: As a Test Analyst, I want the Figma screenshots picked up and associated with features
and screens, so that UI states that exist only in design are still visible to the analysis.

**Acceptance criteria**

- **AC1 (happy)**: Given a screenshot named `<feature>__<screen>__<state>.png`, when it is ingested,
  then the feature, screen and state are parsed from the filename and recorded.
- **AC2 (happy)**: Given a `screens.manifest.yaml` sidecar, when it is present, then its entries
  merge with and take precedence over filename-derived values.
- **AC3 (negative)**: Given a screenshot whose filename does not match the convention and which the
  manifest does not cover, when it is ingested, then it is recorded as unassociated and listed for
  the analyst rather than being dropped or guessed at.
- **AC4 (happy)**: Given a set of screenshots ingested previously and unchanged, when ingestion runs
  again, then no duplicate records are created and unchanged files are skipped by content hash.
- **AC5 (error)**: Given the screenshot folder does not exist, when ingestion runs, then this is
  reported as a configuration problem and other resources still ingest.

---

# E2: Analyse and Understand

**Goal**: a model of the application that later stages reason against.
**Requirements served**: FR-ANA-01 to FR-ANA-08

---

### US-ANA-01: Build the feature model and user journeys

**Release**: R1 (features), R2 (journeys) | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-ANA-01, FR-ANA-02

**Story**: As a Test Analyst, I want the ingested artefacts organised into a feature hierarchy and
user journeys, so that I have a structure to name when I scope a batch.

**Acceptance criteria**

- **AC1 (happy)**: Given ingested Jira issues and code, when the feature model is built, then a
  hierarchy of features and sub-features exists and every feature links to the artefacts that
  evidence it.
- **AC2 (happy)**: Given features spanning multiple screens or endpoints, when journeys are derived,
  then each journey names its ordered steps and the features it traverses.
- **AC3 (negative)**: Given an ingested artefact that maps to no feature, when the model is built,
  then the artefact is listed as unassigned rather than being forced into the nearest feature.
- **AC4 (negative)**: Given two Jira epics describing overlapping functionality, when the model is
  built, then the overlap is reported rather than silently merged or duplicated.
- **AC5 (error)**: Given no artefacts have been ingested, when feature modelling is requested, then
  the system states the prerequisite rather than producing an empty model that looks like a result.

---

### US-ANA-02: Extract business rules and integration points

**Release**: R1 | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-ANA-03, FR-ANA-07

**Story**: As a Test Analyst, I want validation rules, state transitions, calculations, permissions
and external dependencies captured as discrete records, so that each one can be tested
individually instead of being buried in prose.

**Acceptance criteria**

- **AC1 (happy)**: Given a story or source file containing a validation rule, when rules are
  extracted, then the rule exists as its own record with its condition, its effect, and its source.
- **AC2 (happy)**: Given a state machine in code or documentation, when rules are extracted, then
  each valid transition and each explicitly forbidden transition is recorded.
- **AC3 (happy)**: Given calls to an external system, when integration points are extracted, then
  each dependency is recorded with what it is called for.
- **AC4 (negative)**: Given a rule stated in Jira that contradicts the rule implemented in code,
  when extraction runs, then both are recorded and the contradiction is flagged for the analyst.
- **AC5 (negative)**: Given a rule expressed only as an implicit code branch with no documentation,
  when extraction runs, then it is recorded with its code location and marked undocumented.

---

### US-ANA-03: Build the API model

**Release**: R1 | **Personas**: P1, P2 | **Priority**: Must
**Requirements**: FR-ANA-04

**Story**: As a Test Analyst, I want an API model carrying request and response shapes, status codes
and authentication requirements, so that API test cases can be derived from the contract rather
than guessed.

**Acceptance criteria**

- **AC1 (happy)**: Given extracted endpoints and an OpenAPI specification, when the API model is
  built, then each endpoint carries its request shape, response shapes, status codes and
  authentication requirement.
- **AC2 (happy)**: Given an endpoint with no specification, when the model is built, then the shape
  is inferred from the handler source and marked as inferred rather than specified.
- **AC3 (negative)**: Given an endpoint whose authentication requirement cannot be determined, when
  the model is built, then it is marked unknown rather than assumed public, so that a security-
  relevant gap is visible.
- **AC4 (negative)**: Given an endpoint that returns error status codes not described anywhere, when
  the model is built, then those codes are recorded from the source so that negative test cases can
  be derived from them.

---

### US-ANA-04: Build the UI model with verified selectors

**Release**: R2 | **Personas**: P1, P2 | **Priority**: Must
**Requirements**: FR-ANA-05, FR-ANA-06, FR-ANA-08

**Story**: As a Test Automation Engineer, I want the UI model built from the live application as
well as from designs and code, so that the selectors the generated tests use are known to work
rather than assumed to.

**Acceptance criteria**

- **AC1 (happy)**: Given a reachable test environment, when a screen is explored via Playwright MCP,
  then its components and states are recorded with a locator for each element.
- **AC2 (happy)**: Given an element with an accessible role and name, when its locator is derived,
  then a role- or label-based locator is preferred over CSS or XPath, and a fallback chain is
  recorded.
- **AC3 (negative)**: Given an element with no accessible name, no label and no test identifier,
  when its locator is derived, then the system records the weak locator, marks it fragile, and
  reports it as a testability improvement the application team could make.
- **AC4 (negative)**: Given a screen that exists in Figma but not in the live application, or that
  differs materially from its screenshot, when the UI model is built, then the discrepancy is
  recorded against both sources without either being silently preferred.
- **AC5 (error)**: Given the test environment is unreachable, when UI modelling runs, then the
  system falls back to designs and front-end source, marks every derived locator as unverified, and
  states plainly that verification did not happen.

---

# E3: Identify Testable Requirements

**Goal**: atomic, independently verifiable statements with risk and source.
**Requirements served**: FR-TRQ-01 to FR-TRQ-05

---

### US-TRQ-01: Derive atomic testable requirements

**Release**: R1 | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-TRQ-01, FR-TRQ-02, FR-TRQ-04

**Story**: As a Test Analyst, I want features, rules, endpoints and screens decomposed into atomic
testable statements, so that coverage is measured against something specific rather than against a
feature name.

**Acceptance criteria**

- **AC1 (happy)**: Given a feature with its rules and endpoints, when decomposition runs, then each
  resulting requirement is independently verifiable and states a single expected behaviour.
- **AC2 (happy)**: Given each testable requirement, when it is created, then it carries a
  functional or non-functional classification and a category from the defined set.
- **AC3 (negative)**: Given a candidate requirement that bundles two behaviours, when decomposition
  runs, then it is split rather than recorded as one.
- **AC4 (negative)**: Given a candidate requirement that restates another already recorded, when
  decomposition runs, then it is recognised as a duplicate and not recorded twice.
- **AC5 (error)**: Given a candidate requirement that resolves to no Jira key by any route, when it
  is created, then creation is refused and the behaviour is routed to the gap report.

---

### US-TRQ-02: Rate requirement risk

**Release**: R2 | **Personas**: P1, P3 | **Priority**: Must
**Requirements**: FR-TRQ-03

**Story**: As a Test Lead, I want each testable requirement carrying a risk rating with its
derivation, so that coverage depth can be argued from evidence rather than from instinct.

**Acceptance criteria**

- **AC1 (happy)**: Given a testable requirement, when it is rated, then the rating names the factors
  that produced it — business criticality, complexity, integration surface, and change frequency
  drawn from commit history.
- **AC2 (happy)**: Given a requirement covering code changed frequently in recent history, when it
  is rated, then the change frequency raises its risk and the commit evidence is cited.
- **AC3 (negative)**: Given a requirement for which no commit history is available, when it is
  rated, then the change-frequency factor is recorded as unavailable rather than defaulted to zero,
  so an unknown is not mistaken for a low value.
- **AC4**: Given two requirements with the same rating, when I inspect them, then I can see which
  factors drove each, because identical scores from different causes call for different responses.

---

### US-TRQ-03: Identify edge cases and failure scenarios

**Release**: R2 | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-TRQ-05

**Story**: As a Test Analyst, I want edge cases, boundaries and failure scenarios identified
alongside the main behaviour, so that the negative coverage is derived rather than left to whoever
remembers to think of it.

**Acceptance criteria**

- **AC1 (happy)**: Given a requirement with a bounded input, when edge cases are identified, then
  the boundaries and the values immediately inside and outside them are enumerated.
- **AC2 (happy)**: Given an error path present in code but absent from documentation, when failure
  scenarios are identified, then it is captured with its code location.
- **AC3 (happy)**: Given an endpoint with documented error status codes, when failure scenarios are
  identified, then each code has a corresponding scenario.
- **AC4 (negative)**: Given a requirement whose input constraints are not stated anywhere, when edge
  cases are identified, then the system records that boundaries are undetermined rather than
  inventing plausible limits.

---

# E4: Establish Coverage Baseline

**Goal**: a defensible statement of what must be tested, approved before generation begins.
**Requirements served**: FR-COV-01 to FR-COV-07

---

### US-COV-01: Build the coverage model

**Release**: R1 | **Personas**: P3, P1 | **Priority**: Must
**Requirements**: FR-COV-01, FR-COV-02

**Story**: As a Test Lead, I want a coverage model stating which test types each requirement needs
and why, so that coverage is a computed position I can defend rather than an opinion.

**Acceptance criteria**

- **AC1 (happy)**: Given the testable requirement set, when the coverage model is built, then every
  requirement has at least one required test type with a stated rationale.
- **AC2 (happy)**: Given the model as a whole, when I inspect it, then it spans functional positive,
  functional negative, boundary, validation, UI behaviour, API contract, integration, permissions
  and error handling.
- **AC3 (negative)**: Given a requirement for which a test type would add nothing, when the model is
  built, then that type is explicitly marked not-required with a reason rather than being absent
  without explanation.
- **AC4 (negative)**: Given a requirement with no required test type at all, when the model is
  built, then it is surfaced as a gap rather than passing silently.

---

### US-COV-02: Derive coverage depth from test design techniques

**Release**: R2 | **Personas**: P3 | **Priority**: Must
**Requirements**: FR-COV-03

**Story**: As a Test Lead, I want depth derived from equivalence partitioning, boundary value
analysis, decision tables and state transitions, so that the number of cases per requirement has a
reason behind it.

**Acceptance criteria**

- **AC1 (happy)**: Given a requirement with a partitionable input, when depth is derived, then the
  equivalence classes are enumerated and each contributes a planned case.
- **AC2 (happy)**: Given a requirement with a bounded value, when depth is derived, then the planned
  cases follow boundary value analysis and the boundary is named.
- **AC3 (happy)**: Given a requirement with multiple interacting conditions, when depth is derived,
  then a decision table is produced and the planned cases correspond to its rules.
- **AC4 (negative)**: Given a requirement whose combinatorial expansion would produce an
  unreasonable number of cases, when depth is derived, then a documented reduction technique is
  applied and the reduction is recorded, rather than the expansion being emitted in full or
  silently truncated.

---

### US-COV-03: Forecast the yield before generation

**Release**: R2 | **Personas**: P3, P1 | **Priority**: Must
**Requirements**: FR-COV-04

**Story**: As a Test Lead, I want to see the expected number of cases per feature before generation
starts, so that I can change the plan while changing it is still cheap.

**Acceptance criteria**

- **AC1 (happy)**: Given an approved coverage model, when I request the forecast, then it reports
  expected cases per feature and per test type, with a total and its derivation.
- **AC2 (happy)**: Given the forecast, when I inspect any figure, then I can see which coverage
  items produced it.
- **AC3 (negative)**: Given a feature whose forecast is disproportionate to its risk rating, when
  the forecast is produced, then that feature is flagged for review rather than merely listed.
- **AC4 (negative)**: Given a feature forecast at zero cases, when the forecast is produced, then it
  is flagged, since a testable feature with no planned coverage is a defect in the model.

---

### US-COV-04: Approve the baseline before generation

**Release**: R1 | **Personas**: P3 | **Priority**: Must
**Requirements**: FR-COV-06

**Story**: As a Test Lead, I want generation blocked until I have approved the coverage baseline, so
that a flawed model cannot be multiplied across thousands of cases before anyone notices.

**Acceptance criteria**

- **AC1 (happy)**: Given an unapproved coverage baseline, when test case generation is requested,
  then it is refused and the outstanding approval is named.
- **AC2 (happy)**: Given I approve the baseline, when the approval is recorded, then it captures who
  approved, when, and the exact model version approved.
- **AC3 (negative)**: Given an approved baseline that is subsequently modified, when generation is
  requested, then the prior approval no longer applies and re-approval is required.
- **AC4 (negative)**: Given a Test Analyst attempts to approve the baseline, when the approval is
  submitted, then the role restriction is enforced and the attempt is recorded.

---

### US-COV-05: Apply risk-based coverage reduction

**Release**: R3 | **Personas**: P3 | **Priority**: Should
**Requirements**: FR-COV-07

**Story**: As a Test Lead, I want to mark low-risk features for reduced depth with the decision
recorded, so that effort concentrates where the risk is and the choice is visible later.

**Acceptance criteria**

- **AC1 (happy)**: Given a feature I mark reduced-depth, when the model is recalculated, then the
  reduced yield is shown alongside the full yield and the difference is stated.
- **AC2 (happy)**: Given a reduction, when it is applied, then who decided, when, and the stated
  reason are recorded against the feature.
- **AC3 (negative)**: Given a feature with a high risk rating, when reduction is requested, then the
  system requires an explicit override and records the contradiction between the rating and the
  decision.
- **AC4**: Given any reduced feature, when the gap report is produced, then the reduction appears
  in it, because reduced coverage is a gap that was chosen rather than a gap that was missed.

---

# E5: Generate Test Cases

**Goal**: a corpus that is traceable, consistent, and free of padding.
**Requirements served**: FR-TCG-01 to FR-TCG-10

---

### US-TCG-01: Generate structured test cases with mandatory steps

**Release**: R1 | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-TCG-01, FR-TCG-02, FR-TCG-04

**Story**: As a Test Analyst, I want every test case to carry ordered, executable steps with an
expected result, so that a case is something a person or a machine can actually run rather than a
title describing an intention.

**Acceptance criteria**

- **AC1 (happy)**: Given an approved coverage item, when a case is generated, then it carries an
  identifier, title, feature, type, priority, preconditions, ordered steps, per-step expected
  results, an overall expected result, tags, and traceability links.
- **AC2 (negative)**: Given a generated case with an empty step list, when it is submitted for
  storage, then storage is refused with the reason, and the case does not enter the corpus.
- **AC3 (negative)**: Given a case whose steps have no expected results, when it is submitted, then
  storage is refused.
- **AC4 (happy)**: Given a case is stored, when its identifier is allocated, then the toolchain
  allocates it — the model never supplies one — and the identifier is unique across the corpus.
- **AC5 (happy)**: Given a case is regenerated after its source changes, when it is stored, then it
  retains its original identifier rather than being issued a new one.
- **AC6 (error)**: Given identifier allocation fails, when a case is submitted, then the whole
  submission rolls back and no partially stored case remains.

---

### US-TCG-02: Specify synthetic test data with equivalence classes

**Release**: R1 | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-TCG-03, FR-TCG-09

**Story**: As a Test Analyst, I want each data-dependent case to name its input values and the class
or boundary each represents, so that the reason a value was chosen survives into review.

**Acceptance criteria**

- **AC1 (happy)**: Given a case that depends on specific inputs, when it is generated, then the
  values are stated and each is labelled with the equivalence class or boundary it represents.
- **AC2 (happy)**: Given a boundary case, when its data is specified, then the boundary value and
  its relationship to the limit — at, just inside, just outside — are explicit.
- **AC3 (negative)**: Given source artefacts containing what appears to be real personal data, when
  cases are generated, then no such value is copied into a case; a synthetic equivalent is used.
- **AC4 (negative)**: Given a case whose required data cannot be determined from any source, when it
  is generated, then the data requirement is recorded as undetermined and the case is flagged for
  analyst input rather than being given invented values presented as derived.

---

### US-TCG-03: Detect duplicate and near-duplicate cases

**Release**: R2 | **Personas**: P1, P3 | **Priority**: Must
**Requirements**: FR-TCG-05

**Story**: As a Test Lead, I want near-duplicates rejected deterministically, so that the case count
reflects distinct scenarios rather than restatements of the same one.

**Acceptance criteria**

- **AC1 (happy)**: Given a case identical to one already stored, when it is submitted, then it is
  rejected and the existing case is named.
- **AC2 (happy)**: Given a case whose normalised steps and expected results exceed the similarity
  threshold against an existing case, when it is submitted, then it is rejected as a near-duplicate
  with the comparison shown.
- **AC3 (negative)**: Given two cases that differ only in their test data but represent different
  equivalence classes, when the second is submitted, then it is accepted — differing class is a
  material difference, not a restatement.
- **AC4 (happy)**: Given the same corpus and the same candidate, when the check runs repeatedly,
  then the outcome is identical every time.
- **AC5**: Given a rejection, when it is recorded, then the gap report can show what was rejected
  and why, so that a suppressed case is never invisible.

---

### US-TCG-04: Classify automatability

**Release**: R2 | **Personas**: P1, P2 | **Priority**: Must
**Requirements**: FR-TCG-06

**Story**: As a Test Automation Engineer, I want each case classified as automatable or manual-only
with a recorded reason, so that the argument about what to automate happens once per case against
stated criteria.

**Acceptance criteria**

- **AC1 (happy)**: Given a deterministic API or UI case, when it is classified, then it is marked
  automatable with the basis stated.
- **AC2 (happy)**: Given a case requiring visual judgement, exploratory investigation, or data that
  cannot be provisioned automatically, when it is classified, then it is marked manual-only with
  the reason.
- **AC3 (negative)**: Given a case whose automatability is genuinely unclear, when it is classified,
  then it is marked needs-review rather than being forced into either category.
- **AC4**: Given the classification, when I disagree with it, then I can override it, and the
  override is recorded with who made it and why.

---

### US-TCG-05: Derive corpus volume without padding

**Release**: R2 | **Personas**: P3 | **Priority**: Must
**Requirements**: FR-TCG-07

**Story**: As a Test Lead, I want the corpus size to follow from the coverage model, so that the
number I report means something.

**Acceptance criteria**

- **AC1 (happy)**: Given generation completes, when the total is reported, then it is accompanied by
  its derivation from the coverage model.
- **AC2 (negative)**: Given the total falls short of an externally expected figure, when generation
  completes, then the system reports the shortfall and its reasons and does not generate additional
  cases to close the difference.
- **AC3 (negative)**: Given a small story yielding only a handful of cases, when generation
  completes, then that yield is reported as correct rather than treated as a failure — yield
  follows the input.
- **AC4 (happy)**: Given the forecast from US-COV-03, when generation completes, then the actual is
  compared against the forecast and any material variance is explained.

---

### US-TCG-06: Publish reviewable sharded views with tags

**Release**: R1 | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-TCG-08, FR-TCG-10, NFR-USA-02

**Story**: As a Test Analyst, I want cases rendered to Markdown and YAML files split per feature and
tagged, so that I can review them in the editor and select suites later.

**Acceptance criteria**

- **AC1 (happy)**: Given stored cases, when views are generated, then one file per feature is
  produced, readable without special tooling, with steps and expected results legible.
- **AC2 (happy)**: Given the views are deleted, when generation is re-run, then they are rebuilt
  identically from the database, because they are views and not the record.
- **AC3 (happy)**: Given a case, when it is generated, then it carries tags for suite, type, feature
  and priority.
- **AC4 (negative)**: Given a view file that has been hand-edited, when views are regenerated, then
  the edit is detected and reported before it is overwritten, so that work is not lost silently
  even though the database remains authoritative.

---

# E6: Generate Automation

**Goal**: a Playwright project a human would be willing to maintain.
**Requirements served**: FR-AUT-01 to FR-AUT-11

---

### US-AUT-01: Generate a standard Playwright project with page objects

**Release**: R1 | **Personas**: P2 | **Priority**: Must
**Requirements**: FR-AUT-01, FR-AUT-02

**Story**: As a Test Automation Engineer, I want a conventional `@playwright/test` project using the
Page Object Model, so that I can maintain it with Playwright knowledge alone and no bespoke
framework to learn.

**Acceptance criteria**

- **AC1 (happy)**: Given automation generation runs, when the project is produced, then it uses
  `@playwright/test` directly with no custom runner or wrapper.
- **AC2 (happy)**: Given a screen in the UI model, when its page object is generated, then locators
  are defined centrally in that object and not repeated across specs.
- **AC3 (happy)**: Given a spec file, when it is generated, then it interacts with the application
  only through page objects.
- **AC4 (negative)**: Given a case referencing a screen with no page object, when generation runs,
  then generation of that case fails with a clear reason rather than emitting a spec with inline
  selectors.
- **AC5 (happy)**: Given the generated project, when a Playwright-experienced engineer opens it,
  then its structure is conventional enough to navigate without reading the generator.

---

### US-AUT-02: Generate resilient locators without fixed waits

**Release**: R2 | **Personas**: P2 | **Priority**: Must
**Requirements**: FR-AUT-03, FR-AUT-09

**Story**: As a Test Automation Engineer, I want locators built from roles and labels and waiting
handled by expectations, so that the suite survives ordinary UI change and does not trade
reliability for speed.

**Acceptance criteria**

- **AC1 (happy)**: Given an element with an accessible role and name, when its locator is generated,
  then `getByRole` or `getByLabel` is used in preference to CSS or XPath.
- **AC2 (happy)**: Given an element with a test identifier, when its locator is generated, then
  `getByTestId` is used where no better semantic locator exists.
- **AC3 (negative)**: Given generation would emit `waitForTimeout` or any fixed sleep, when the code
  is produced, then it is rejected and an expectation-based wait is emitted instead.
- **AC4 (negative)**: Given only a fragile locator is available, when it is generated, then the code
  carries a comment naming the fragility and the test is listed in the automation report as at risk.
- **AC5 (happy)**: Given locators derived from live exploration, when they are generated, then each
  has been verified against the running application, and any unverified locator is marked as such.

---

### US-AUT-03: Generate API tests in the same project

**Release**: R1 | **Personas**: P2 | **Priority**: Must
**Requirements**: FR-AUT-04

**Story**: As a Test Automation Engineer, I want API tests using Playwright's `APIRequestContext`
inside the same project, so that there is one repository, one runner, one report and one
authentication path.

**Acceptance criteria**

- **AC1 (happy)**: Given an automatable API case, when it is generated, then it uses
  `APIRequestContext` within the same project as the UI tests.
- **AC2 (happy)**: Given both UI and API tests need authentication, when they are generated, then
  they share a single fixture rather than duplicating the logic.
- **AC3 (happy)**: Given an API case asserting a status code and body shape, when it is generated,
  then both assertions are present.
- **AC4 (negative)**: Given an API case for an endpoint whose contract is marked inferred rather
  than specified, when it is generated, then the test is annotated as contract-inferred so a failure
  can be judged against a weaker source.

---

### US-AUT-04: Annotate tests with tags and traceability

**Release**: R1 | **Personas**: P2, P3 | **Priority**: Must
**Requirements**: FR-AUT-05, FR-AUT-06

**Story**: As a Test Automation Engineer, I want each generated test annotated with its tags, case
identifier and Jira key, so that a red test in Jenkins carries its own provenance.

**Acceptance criteria**

- **AC1 (happy)**: Given a generated test, when it is emitted, then its tag annotations match the
  tags of the case it came from.
- **AC2 (happy)**: Given a generated test, when it is emitted, then it references its case
  identifier and Jira key in an annotation that survives into the JUnit XML report.
- **AC3 (happy)**: Given a failing test in a CI report, when I inspect it, then I can reach its case
  and its Jira issue without consulting a separate mapping file.
- **AC4 (negative)**: Given a case somehow lacking a Jira key, when automation generation is
  attempted, then it is refused — the traceability rule holds at the automation boundary as well as
  at the case boundary.

---

### US-AUT-05: Externalise configuration and configure reporters

**Release**: R1 | **Personas**: P2 | **Priority**: Must
**Requirements**: FR-AUT-07, FR-AUT-08

**Story**: As a Test Automation Engineer, I want environments configured by variables and both
reporters set up, so that the suite runs in Jenkins without my editing it first.

**Acceptance criteria**

- **AC1 (happy)**: Given the generated project, when it is inspected, then base URL, credentials and
  timeouts come from environment variables and a `.env.example` documents every one.
- **AC2 (negative)**: Given generation would emit a credential, token or environment-specific URL
  as a literal, when the code is produced, then it is rejected.
- **AC3 (happy)**: Given `playwright.config.ts`, when it is inspected, then both the HTML reporter
  and the JUnit XML reporter are configured with defined output paths.
- **AC4 (error)**: Given a required environment variable is unset at run time, when the suite
  starts, then it fails immediately with a message naming the variable, rather than failing later
  as an obscure assertion error.

---

### US-AUT-06: Regenerate safely and automate only what qualifies

**Release**: R2 | **Personas**: P2 | **Priority**: Must
**Requirements**: FR-AUT-10, FR-AUT-11

**Story**: As a Test Automation Engineer, I want regeneration to be deterministic and to respect my
edits, so that the generated suite is a starting point rather than something I cannot touch.

**Acceptance criteria**

- **AC1 (happy)**: Given only automatable cases, when generation runs, then manual-only cases
  produce no test and are listed in the automation report with their reason.
- **AC2 (happy)**: Given unchanged inputs, when generation is re-run, then the output is byte-for-
  byte identical.
- **AC3 (negative)**: Given a generated file I have hand-edited, when regeneration would overwrite
  it, then the edit is detected and reported and I decide, rather than the change being discarded.
- **AC4 (error)**: Given generation fails partway through a batch, when it stops, then the files
  already written remain valid and the failure names the case that could not be generated.

---

# E7: Handover Package

**Goal**: a project the test team can push and run without modification.
**Requirements served**: FR-HND-01 to FR-HND-06

---

### US-HND-01: Assemble a standalone Playwright project

**Release**: R1 | **Personas**: P2 | **Priority**: Must
**Requirements**: FR-HND-01, FR-HND-02, FR-HND-03, FR-HND-04

**Story**: As a Test Automation Engineer, I want a complete project directory in the workspace, so
that I can push it to our Bitbucket repository and configure Jenkins myself.

**Acceptance criteria**

- **AC1 (happy)**: Given handover assembly runs, when it completes, then the directory contains
  `package.json`, `package-lock.json`, `playwright.config.ts`, `tsconfig.json`, tests, page objects,
  fixtures, API clients, test data, `.env.example`, `.gitignore` and `README.md`.
- **AC2 (happy)**: Given the project, when dependencies are inspected, then every version is exact
  and the lockfile is present.
- **AC3 (happy)**: Given the `README.md`, when I read it, then installation, environment
  configuration, tag-based suite selection and the reporter outputs are all documented.
- **AC4 (negative)**: Given handover completes, when I check what the system did, then it has not
  pushed to any repository, has not created a branch, and has not written Jenkins configuration.
- **AC5 (happy)**: Given `.gitignore`, when it is inspected, then the SQLite database and ingested
  corporate content are excluded, so the push cannot carry them.

---

### US-HND-02: Verify integrity before declaring handover ready

**Release**: R2 | **Personas**: P2 | **Priority**: Must
**Requirements**: FR-HND-05

**Story**: As a Test Automation Engineer, I want the assembled project checked before I am told it
is ready, so that I find problems here rather than in a failed Jenkins build.

**Acceptance criteria**

- **AC1 (happy)**: Given the assembled project, when verification runs, then every referenced page
  object, fixture and data file is confirmed to exist.
- **AC2 (happy)**: Given the project, when verification runs, then TypeScript compilation succeeds.
- **AC3 (happy)**: Given the project, when verification runs, then `playwright test --list`
  enumerates the tests without error.
- **AC4 (negative)**: Given a spec referencing a page object that was never generated, when
  verification runs, then handover is not declared ready and the specific broken reference is named.
- **AC5 (error)**: Given compilation fails, when verification runs, then the compiler output is
  surfaced rather than a generic failure.

---

### US-HND-03: Produce a handover manifest

**Release**: R2 | **Personas**: P2, P3 | **Priority**: Must
**Requirements**: FR-HND-06

**Story**: As a Test Lead, I want a manifest of everything in the handover, so that I know exactly
what was delivered and what it covers.

**Acceptance criteria**

- **AC1 (happy)**: Given handover completes, when the manifest is produced, then it lists every
  generated test with its case identifier, Jira key and tags.
- **AC2 (happy)**: Given the manifest, when I read it, then it states how many cases were
  automated, how many were manual-only, and the total in the corpus.
- **AC3 (negative)**: Given a test in the project that is absent from the manifest, or a manifest
  entry with no corresponding test, when the manifest is produced, then the mismatch is reported
  and handover is not declared ready.

---

# E8: Traceability

**Goal**: the rule that keeps the corpus honest, enforced rather than requested.
**Requirements served**: FR-TRC-01 to FR-TRC-06, FR-RPT-03

---

### US-TRC-01: Enforce the mandatory Jira key

**Release**: R1 | **Personas**: P3, P1 | **Priority**: Must
**Requirements**: FR-TRC-01

**Story**: As a Test Lead, I want the storage layer to refuse any case without a Jira key link, so
that the traceability rule cannot erode across thousands of cases.

**Acceptance criteria**

- **AC1 (happy)**: Given a case with at least one link resolving to a Jira key, when it is stored,
  then storage succeeds.
- **AC2 (negative)**: Given a case with no traceability links, when it is stored, then storage is
  refused and the reason is stated.
- **AC3 (negative)**: Given a case with links that resolve only to a Confluence page or a code
  symbol and to no Jira key, when it is stored, then storage is refused.
- **AC4 (negative)**: Given a case linked to a Jira key that does not exist in the ingested set,
  when it is stored, then storage is refused, so that an invented key cannot satisfy the rule.
- **AC5**: Given the corpus at any moment, when it is queried for cases without a Jira key, then the
  result is always empty.

---

### US-TRC-02: Derive Jira keys from commit history

**Release**: R2 | **Personas**: P1, P3 | **Priority**: Must
**Requirements**: FR-TRC-02, FR-TRC-03

**Story**: As a Test Analyst, I want behaviour found in code or designs traced to a Jira key through
the commits that touched it, so that undocumented functionality can still be tested without
weakening the traceability rule.

**Acceptance criteria**

- **AC1 (happy)**: Given a behaviour in a source file with no directly associated Jira story, when a
  key is derived, then commit history for that file is searched and the best-matching key attached.
- **AC2 (happy)**: Given a derived link, when it is stored, then its type is `derived-from-commit`
  and it is visually distinguishable from a `direct-story` link wherever it is shown.
- **AC3 (negative)**: Given a derived link, when coverage is reported, then derived links are
  counted separately from direct links, because provenance is weaker evidence than specification.
- **AC4 (negative)**: Given several candidate keys from different commits, when derivation runs,
  then the selection basis is recorded and the alternatives retained.
- **AC5 (error)**: Given commit history is unavailable for a file, when derivation is attempted,
  then the attempt is recorded as failed and the behaviour routes to the gap report.

---

### US-TRC-03: Route untraceable behaviour to the gap report

**Release**: R2 | **Personas**: P1, P3 | **Priority**: Must
**Requirements**: FR-TRC-04

**Story**: As a Test Lead, I want behaviour with no derivable Jira key recorded as a gap rather than
discarded, so that the boundary of our coverage is visible and someone can act on it.

**Acceptance criteria**

- **AC1 (happy)**: Given a behaviour with no key derivable by any route, when it is processed, then
  it appears in the gap report with its source location and what was attempted.
- **AC2 (negative)**: Given such a behaviour, when it is processed, then no test case is created for
  it — the rule is not relaxed to accommodate it.
- **AC3 (happy)**: Given the gap report, when I read it, then untraceable behaviours are grouped by
  source so that a repository with poor Jira key discipline is visible as a pattern.
- **AC4 (happy)**: Given a Jira story is later created covering a gapped behaviour, when the delta
  run executes, then the behaviour becomes eligible for case generation.

---

### US-TRC-04: Produce the bidirectional traceability matrix

**Release**: R2 | **Personas**: P3 | **Priority**: Must
**Requirements**: FR-TRC-05, FR-TRC-06, FR-RPT-03

**Story**: As a Test Lead, I want to trace forward from any requirement to its tests and back from
any test to its requirement, so that I can answer coverage questions from either direction.

**Acceptance criteria**

- **AC1 (happy)**: Given the matrix, when I select a requirement, then every case and every
  automated test derived from it is listed.
- **AC2 (happy)**: Given the matrix, when I select an automated test, then its case, its
  requirement, and its source artefact are reachable.
- **AC3 (happy)**: Given the matrix, when it is produced, then it is available in both Markdown and
  CSV.
- **AC4 (negative)**: Given a requirement with no cases, when the matrix is produced, then it
  appears with an empty test set rather than being omitted — an absent row hides exactly the thing
  the matrix exists to reveal.
- **AC5 (happy)**: Given ingested repositories, when the matrix is produced, then the Jira key
  coverage percentage reported by the Bitbucket MCP is included per repository.

---

# E9: Batch, State and Resumability

**Goal**: a run that spans days and sessions without losing or repeating work.
**Requirements served**: FR-BAT-01 to FR-BAT-07

---

### US-BAT-01: Name the batch scope

**Release**: R1 | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-BAT-01, FR-BAT-06

**Story**: As a Test Analyst, I want to name the feature and stage for each batch, so that the
system works on what I decided rather than on what it inferred.

**Acceptance criteria**

- **AC1 (happy)**: Given I name a feature and a stage, when the batch runs, then it operates on
  exactly that scope.
- **AC2 (negative)**: Given I have not named a scope, when I ask the system to continue, then it
  asks which feature and stage rather than selecting one.
- **AC3 (negative)**: Given a unit already completed for that stage, when I name it again, then the
  system reports it as complete and requires an explicit regeneration instruction before proceeding.
- **AC4 (negative)**: Given I name a feature that does not exist in the model, when the batch is
  requested, then the system says so and lists the closest matches rather than choosing one.
- **AC5**: Given a batch completes, when it finishes, then the system reports what it did and stops
  — it does not announce or begin the next unit.

---

### US-BAT-02: Track unit state durably and transactionally

**Release**: R1 | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-BAT-02, FR-BAT-03, FR-BAT-05

**Story**: As a Test Analyst, I want per-unit progress recorded transactionally and reportable on
demand, so that I can see where the run stands without reconstructing it from memory.

**Acceptance criteria**

- **AC1 (happy)**: Given any unit and stage, when I request status, then it reports not started, in
  progress, completed, failed or needs review.
- **AC2 (happy)**: Given I request overall status, when it is produced, then it shows what is
  complete and what remains, as reporting only — no next unit is proposed.
- **AC3 (happy)**: Given a unit completes, when its state is written, then the state change and its
  outputs commit in a single transaction.
- **AC4 (error)**: Given the process is killed mid-unit, when the database is inspected, then that
  unit shows its prior state and no partial output exists.
- **AC5 (happy)**: Given a unit fails, when its state is recorded, then the failure reason is stored
  and other units are unaffected.

---

### US-BAT-03: Resume after interruption

**Release**: R1 | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-BAT-04

**Story**: As a Test Analyst, I want to close the editor mid-run and pick up later with nothing
lost, so that a corpus of this size can be built across many sessions.

**Acceptance criteria**

- **AC1 (happy)**: Given a run interrupted after several completed units, when I return in a new
  session, then completed work is intact and status reports it accurately.
- **AC2 (happy)**: Given I resume, when I name the next unit, then previously completed units are
  not reprocessed.
- **AC3 (negative)**: Given a unit interrupted mid-processing, when I resume, then it is reported as
  in progress or failed and I decide whether to restart it — it does not silently resume from an
  unknown point.
- **AC4 (error)**: Given the database was left locked by a killed process, when I resume, then the
  lock is detected and reported with a recovery instruction rather than the run hanging.

---

### US-BAT-04: Stop at every stage gate

**Release**: R1 | **Personas**: P1, P3 | **Priority**: Must
**Requirements**: FR-BAT-07

**Story**: As a Test Analyst, I want every stage to stop for approval, so that the system never
advances work I have not seen.

**Acceptance criteria**

- **AC1 (happy)**: Given a unit completes a stage, when the stage ends, then the system presents the
  output and stops.
- **AC2 (negative)**: Given a unit whose stage has not been approved, when the next stage is
  requested, then it is refused and the outstanding approval is named.
- **AC3 (happy)**: Given I approve a stage for a unit, when the approval is recorded, then it
  captures who, when, and what was approved.
- **AC4 (negative)**: Given approved output is subsequently changed, when the next stage is
  requested, then the approval no longer applies.

---

# E10: Incremental Re-baselining

**Goal**: the baseline stays true as the application moves.
**Requirements served**: FR-DLT-01 to FR-DLT-07

---

### US-DLT-01: Detect changes since the last run

**Release**: R3 | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-DLT-01, FR-DLT-02

**Story**: As a Test Analyst, I want the system to find what changed in Bitbucket and Jira since the
last run, so that I re-analyse only what moved.

**Acceptance criteria**

- **AC1 (happy)**: Given a recorded head commit and a newer current head, when delta detection runs,
  then changed files, commits and their Jira keys are reported for the range.
- **AC2 (happy)**: Given a recorded last-run timestamp, when delta detection runs, then Jira issues
  updated since then are retrieved.
- **AC3 (happy)**: Given no changes since the last run, when detection runs, then it reports no
  changes rather than producing an empty work plan that looks like work.
- **AC4 (negative)**: Given the recorded head commit no longer exists — a force-push or a rebase —
  when detection runs, then this is reported and a full re-baseline is offered, rather than the
  comparison silently producing nonsense.
- **AC5 (error)**: Given a repository is unreachable, when detection runs, then that repository is
  reported as unchecked and other repositories are still compared.

---

### US-DLT-02: Map changes to affected artefacts and classify them

**Release**: R3 | **Personas**: P1, P3 | **Priority**: Must
**Requirements**: FR-DLT-03, FR-DLT-04, FR-DLT-06

**Story**: As a Test Analyst, I want each detected change traced to the cases and tests it affects
and classified, so that I know precisely what needs attention.

**Acceptance criteria**

- **AC1 (happy)**: Given a changed file, when impact is mapped, then the traceability graph yields
  the affected features, requirements, cases and automated tests.
- **AC2 (happy)**: Given each affected case, when it is classified, then it is marked unchanged,
  requires-update or obsolete with a stated reason.
- **AC3 (negative)**: Given a change to a file with no traceability links, when impact is mapped,
  then it is reported as unmapped rather than assumed to have no impact.
- **AC4 (happy)**: Given a delta run, when it reaches a stage boundary, then the same human gates
  apply as in the initial baseline.
- **AC5 (negative)**: Given a change affecting a very large share of the corpus, when impact is
  mapped, then the scale is reported before any regeneration begins.

---

### US-DLT-03: Retire obsolete cases without deleting them

**Release**: R3 | **Personas**: P3 | **Priority**: Must
**Requirements**: FR-DLT-05, FR-DLT-07

**Story**: As a Test Lead, I want obsolete cases marked and kept with their reason, so that coverage
history survives and nothing disappears without explanation.

**Acceptance criteria**

- **AC1 (happy)**: Given a case classified obsolete, when it is retired, then it is marked obsolete
  and retained with the reason and the change event that caused it.
- **AC2 (negative)**: Given any delta run, when it completes, then no case has been hard-deleted.
- **AC3 (happy)**: Given any case, when I inspect its history, then I can see the run that created
  it and every run that modified it.
- **AC4 (happy)**: Given obsolete cases exist, when the coverage report is produced, then they are
  excluded from active coverage and reported separately.

---

# E11: Reporting

**Goal**: coverage as computed fact, and the gaps stated plainly.
**Requirements served**: FR-RPT-01, FR-RPT-02, FR-RPT-04, FR-RPT-05, FR-COV-05

---

### US-RPT-01: Produce the coverage report

**Release**: R2 | **Personas**: P3 | **Priority**: Must
**Requirements**: FR-RPT-01, FR-RPT-05

**Story**: As a Test Lead, I want a coverage report generated from the database showing planned
against generated with its derivation, so that I can defend the coverage position.

**Acceptance criteria**

- **AC1 (happy)**: Given a generated corpus, when the report is produced, then it shows per feature
  and per test type the planned and generated counts.
- **AC2 (happy)**: Given any figure in the report, when I question it, then its derivation from the
  coverage model is shown.
- **AC3 (happy)**: Given the report, when it is produced, then every figure comes from a database
  query and none is assembled by hand.
- **AC4 (negative)**: Given generated counts fall short of planned counts, when the report is
  produced, then the shortfall is stated per feature with the reason rather than being averaged away
  into a headline percentage.

---

### US-RPT-02: Produce the gap report

**Release**: R2 | **Personas**: P3 | **Priority**: Must
**Requirements**: FR-RPT-02, FR-COV-05

**Story**: As a Test Lead, I want a report of what is *not* covered, because that is the half that
tells me where the risk is.

**Acceptance criteria**

- **AC1 (happy)**: Given the corpus, when the gap report is produced, then it lists requirements
  with no planned coverage, behaviours with no derivable Jira key, manual-only cases, features
  marked reduced-depth, and cases rejected as duplicates.
- **AC2 (happy)**: Given each gap, when it is listed, then its source and the reason it is a gap are
  stated.
- **AC3 (happy)**: Given no gaps exist in a category, when the report is produced, then the category
  is shown as empty rather than omitted, so a silent section is never mistaken for a missing check.
- **AC4 (happy)**: Given gaps grouped by source, when I read the report, then a repository or space
  with systematically poor traceability is visible as a pattern rather than as scattered entries.

---

### US-RPT-03: Produce the automation report

**Release**: R2 | **Personas**: P2, P3 | **Priority**: Must
**Requirements**: FR-RPT-04

**Story**: As a Test Automation Engineer, I want a report of what was automated and what was not
with reasons, so that the manual residue is a known quantity.

**Acceptance criteria**

- **AC1 (happy)**: Given automation generation has run, when the report is produced, then it states
  cases automated, cases deferred, and the reason for each deferral.
- **AC2 (happy)**: Given tests generated with fragile locators, when the report is produced, then
  they are listed as at risk.
- **AC3 (happy)**: Given tests annotated as contract-inferred or with unverified locators, when the
  report is produced, then they are listed so that their weaker basis is known before CI runs them.

---

# E12: Agent Layer

**Goal**: the Copilot configuration that makes the pipeline operable.
**Requirements served**: FR-AGT-01 to FR-AGT-06

---

### US-AGT-01: Establish repository instructions

**Release**: R1 | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-AGT-01, FR-AGT-06, NFR-USA-03

**Story**: As a Test Analyst, I want the agent to carry the project's standards without my restating
them, so that every session behaves consistently.

**Acceptance criteria**

- **AC1 (happy)**: Given `.github/copilot-instructions.md`, when a session starts, then the role,
  pipeline model, traceability rules and output conventions are in force without being restated.
- **AC2 (happy)**: Given the instructions, when they are read, then they require all durable state
  changes to go through `tto-testgen-mcp` rather than direct file writes.
- **AC3 (negative)**: Given the agent is asked to record a test case by writing a file directly,
  when it responds, then it uses the toolchain instead and says why.
- **AC4 (negative)**: Given the agent cannot ground an assertion in an ingested artefact, when it
  responds, then it says so rather than producing plausible content.

---

### US-AGT-02: Provide per-stage chat modes

**Release**: R1 | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-AGT-03, NFR-USA-01

**Story**: As a Test Analyst, I want one chat mode per pipeline stage with only that stage's tools
available, so that a session cannot stray outside the work I asked for.

**Acceptance criteria**

- **AC1 (happy)**: Given a chat mode per stage, when I select one, then the agent operates within
  that stage's purpose.
- **AC2 (happy)**: Given a stage's chat mode, when it is active, then only that stage's tools are
  available.
- **AC3 (negative)**: Given the ingestion mode is active, when automation generation is requested,
  then it is declined and the correct mode is named.
- **AC4 (happy)**: Given each mode, when it starts, then it states which stage it serves and what it
  needs from me.

---

### US-AGT-03: Register the MCP servers

**Release**: R1 | **Personas**: P1 | **Priority**: Must
**Requirements**: FR-AGT-05

**Story**: As a Test Analyst, I want all four MCP servers registered in the workspace, so that the
agent has its tools without per-machine setup beyond credentials.

**Acceptance criteria**

- **AC1 (happy)**: Given `.vscode/mcp.json`, when the workspace opens, then `tto-testgen-mcp`,
  TTO-Atlassian-MCP, TTO-Bitbucket-MCP and Playwright MCP are all registered.
- **AC2 (happy)**: Given the configuration, when it is inspected, then credentials come from
  environment variables or the OS credential store and no secret is present in the file.
- **AC3 (error)**: Given a server fails to start, when the agent attempts to use it, then the
  failure names the server and what is missing, and stages not depending on it still work.

---

### US-AGT-04: Provide path-scoped instructions and prompt files

**Release**: R2 | **Personas**: P1, P2 | **Priority**: Must
**Requirements**: FR-AGT-02, FR-AGT-04

**Story**: As a Test Automation Engineer, I want coding standards to apply automatically to the
files they govern, and recurring tasks available as prompts, so that guidance arrives without being
fetched.

**Acceptance criteria**

- **AC1 (happy)**: Given I edit a generated Playwright file, when the agent assists, then the
  automation coding standards apply through the `applyTo` glob without my invoking them.
- **AC2 (happy)**: Given I edit a test case view file, when the agent assists, then the test case
  standards apply instead.
- **AC3 (happy)**: Given the prompt files, when I invoke one, then the recurring task runs with its
  established structure.
- **AC4 (negative)**: Given a file matching no instruction glob, when the agent assists, then only
  the repository-wide instructions apply, and this is not treated as an error.

---

# E13: Technical Enablers

**Goal**: the machinery beneath the pipeline.

**These are enabler stories, not user value.** They are recorded separately and named honestly
because folding them into user-facing stories would disguise substantial effort inside deceptively
small work, and omitting them would lose it from the backlog altogether. Each states the user-facing
capability it exists to make possible.

**Requirements served**: the non-functional requirement set, plus the data requirements in §10 of
`requirements.md`

---

### US-ENB-01: Versioned SQLite schema and durability

**Release**: R1 (schema), R2 (durability) | **Enables**: E5, E8, E9, E10, E11
**Requirements**: requirements.md §10.2, §10.3, NFR-REL-01, NFR-REL-05, NFR-REL-06, NFR-REL-07

**Story**: As the toolchain, I need a versioned SQLite schema with transactional writes, backup and
portable export, so that the corpus is durable and the integrity rules are enforced by the storage
layer rather than by convention.

**Acceptance criteria**

- **AC1 (happy)**: Given the schema, when it is created, then all entities in §10.2 exist with their
  relationships, and the §10.3 integrity rules are enforced as constraints — not as application-level
  checks that can be bypassed.
- **AC2 (negative)**: Given an attempt to insert a test case with no steps or no Jira key link, when
  it reaches the database, then the constraint rejects it.
- **AC3 (happy)**: Given a schema change, when it is applied, then it runs as a versioned migration
  and can be reversed.
- **AC4 (happy)**: Given a destructive or schema-changing operation, when it runs, then a backup is
  taken first and retained locally.
- **AC5 (happy)**: Given the corpus, when export is requested, then it is written to a portable
  format sufficient to reconstruct it without the database file.
- **AC6 (error)**: Given a migration fails partway, when it is rolled back, then the database
  returns to its prior version intact.

---

### US-ENB-02: MCP server with typed, validated tools

**Release**: R1 | **Enables**: every epic
**Requirements**: C-10, NFR-SEC-02, NFR-SEC-03, NFR-SEC-04, NFR-POR-01, NFR-POR-02, NFR-SEC-09

**Story**: As the toolchain, I need to expose typed tools over stdio with validated inputs and
pinned dependencies, so that the agent has a safe, discoverable interface on any operator's machine.

**Acceptance criteria**

- **AC1 (happy)**: Given the server starts, when it is inspected, then it communicates over stdio
  and opens no network listener.
- **AC2 (happy)**: Given each tool, when it is registered, then it declares a typed schema the agent
  can discover.
- **AC3 (negative)**: Given a tool call with a wrong type, an oversized string or a malformed
  identifier, when it is received, then it is rejected by schema validation before any logic runs.
- **AC4 (negative)**: Given any database access, when the query is constructed, then parameters are
  bound and no string concatenation is used.
- **AC5 (happy)**: Given Python 3.11 or later on macOS, Windows or Linux, when the server is
  installed from its lockfile, then it starts successfully.
- **AC6 (happy)**: Given the project, when dependencies are inspected, then all are pinned, a
  vulnerability scanning step is documented and an SBOM is produced.

---

### US-ENB-03: Observability and failure isolation

**Release**: R1 | **Enables**: E9, E10, and diagnosis everywhere
**Requirements**: NFR-SEC-06, NFR-SEC-07, NFR-SEC-08, NFR-OBS-01, NFR-OBS-02, NFR-OBS-03,
NFR-REL-02, NFR-REL-03, NFR-REL-04

**Story**: As the toolchain, I need structured logging, health checks, per-unit metrics and bounded
retry with failure isolation, so that a long run can be diagnosed and one bad unit cannot take down
the run.

**Acceptance criteria**

- **AC1 (happy)**: Given any operation, when it logs, then the entry carries a timestamp,
  correlation identifier, level and message, and contains no credential or personal data.
- **AC2 (happy)**: Given the health check, when it runs, then it reports database accessibility,
  schema version and external MCP reachability.
- **AC3 (happy)**: Given a completed unit, when metrics are recorded, then duration, artefacts
  consumed, cases produced and failures are captured.
- **AC4 (happy)**: Given a transient external failure, when it occurs, then retry is bounded with
  backoff and each attempt is logged.
- **AC5 (negative)**: Given retries are exhausted, when the operation fails, then the unit fails and
  the run continues — the failure does not cascade.
- **AC6 (error)**: Given an unhandled exception anywhere, when it propagates, then the global
  handler logs it and returns a safe result that names no filesystem path outside the workspace and
  no internal stack detail.

---

### US-ENB-04: Secrets and confidentiality controls

**Release**: R1 | **Enables**: E7, and safe operation throughout
**Requirements**: NFR-SEC-01, NFR-SEC-05, NFR-SEC-10, NFR-SEC-11, NFR-SEC-12, NFR-SEC-13,
NFR-SEC-14, NFR-SEC-15, NFR-SEC-16

**Story**: As the toolchain, I need secrets kept out of every artefact and ingested corporate content
kept out of anything destined for another repository, so that using the system does not leak what it
reads.

**Acceptance criteria**

- **AC1 (negative)**: Given the repository and the database, when either is scanned, then no
  credential, token or API key is present.
- **AC2 (happy)**: Given `.gitignore`, when it is inspected, then the database and generated
  artefacts holding ingested content are excluded by default.
- **AC3 (negative)**: Given generation of a handover artefact, when it runs, then verbatim internal
  documentation is not carried into it — only the behaviour and expectations a test needs.
- **AC4 (negative)**: Given personal data appears in a source artefact, when cases are generated,
  then it does not propagate into any case or test.
- **AC5 (negative)**: Given YAML or JSON from a repository, when it is deserialised, then a safe
  loader is used that cannot instantiate arbitrary types.
- **AC6 (negative)**: Given any code path, when it is inspected, then no Atlassian or Bitbucket write
  tool is invoked anywhere.
- **AC7 (happy)**: Given a change to a test case or coverage decision, when it is recorded, then the
  actor, timestamp and change are captured.
- **AC8 (happy)**: Given external calls, when they are made, then TLS 1.2 or above is used and no
  unencrypted protocol appears.

---

### US-ENB-05: Scale and performance

**Release**: R2 | **Enables**: E5, E11 at full volume
**Requirements**: NFR-SCL-01, NFR-SCL-02, NFR-SCL-03, NFR-SCL-04, NFR-PRF-01, NFR-PRF-02,
NFR-PRF-03, NFR-PRF-04

**Story**: As the toolchain, I need to stay responsive at ten thousand test cases, so that the
system does not degrade as the corpus reaches the volume the project expects.

**Acceptance criteria**

- **AC1 (happy)**: Given a corpus of 10,000 cases, when a single-case operation runs, then it
  completes in under 200 milliseconds.
- **AC2 (happy)**: Given a corpus of 10,000 cases, when full report generation runs, then it
  completes in under 30 seconds.
- **AC3 (happy)**: Given duplicate detection at that volume, when it runs, then it uses indexed
  comparison and does not scan pairwise.
- **AC4 (happy)**: Given a previously ingested artefact whose content hash is unchanged, when
  ingestion runs, then the cached record is used and no external call is made.
- **AC5 (happy)**: Given any operation, when it executes, then it works at feature granularity and
  never requires the whole corpus in a model context window.

---

### US-ENB-06: Test suite including property-based tests

**Release**: R2 | **Enables**: confidence in every epic
**Requirements**: NFR-MNT-01, NFR-MNT-02, NFR-MNT-03, NFR-MNT-04, NFR-MNT-05, NFR-MNT-06,
NFR-MNT-07, NFR-MNT-08

**Story**: As the toolchain, I need example-based and property-based tests over my own logic, so
that the invariants the whole system depends on are verified rather than assumed.

**Acceptance criteria**

- **AC1 (happy)**: Given the modules, when the codebase is inspected, then ingestion, storage,
  coverage, generation, traceability, emission and reporting are separated.
- **AC2 (happy)**: Given documented behaviour, when tests run, then example-based tests cover it.
- **AC3 (happy)**: Given serialisation, when property tests run, then record-to-YAML-to-record and
  identifier encoding round-trips hold for all generated inputs.
- **AC4 (happy)**: Given the invariants, when property tests run, then identifier uniqueness and
  monotonic allocation, coverage totals equalling the sum of their parts, and de-duplication being
  reflexive and symmetric are all verified.
- **AC5 (happy)**: Given the generators, when they produce inputs, then they are domain-specific —
  realistic Jira keys, realistic step structures — not unconstrained primitives.
- **AC6 (happy)**: Given a property test failure, when it is reported, then the case is shrunk to a
  minimal counterexample and the seed is recorded for deterministic reproduction.

---

# Requirement Coverage

Every requirement in `requirements.md` v1.0 is served by at least one story. Verified
programmatically against the requirement identifiers in both documents.

| Requirement group | Count | Stories serving it |
|---|---|---|
| FR-AGT (Agent Layer) | 6 | US-AGT-01 to US-AGT-04 |
| FR-ING (Input Ingestion) | 10 | US-ING-01 to US-ING-04 |
| FR-ANA (Analyse and Understand) | 8 | US-ANA-01 to US-ANA-04 |
| FR-TRQ (Testable Requirements) | 5 | US-TRQ-01 to US-TRQ-03 |
| FR-COV (Coverage Baseline) | 7 | US-COV-01 to US-COV-05, US-RPT-02 |
| FR-TCG (Test Case Generation) | 10 | US-TCG-01 to US-TCG-06 |
| FR-AUT (Automation Generation) | 11 | US-AUT-01 to US-AUT-06 |
| FR-HND (Handover) | 6 | US-HND-01 to US-HND-03 |
| FR-TRC (Traceability) | 6 | US-TRC-01 to US-TRC-04 |
| FR-BAT (Batch and State) | 7 | US-BAT-01 to US-BAT-04 |
| FR-DLT (Re-baselining) | 7 | US-DLT-01 to US-DLT-03 |
| FR-RPT (Reporting) | 5 | US-RPT-01 to US-RPT-03, US-TRC-04 |
| **Functional total** | **88** | **all covered** |
| NFR-SCL (Scale) | 4 | US-ENB-05 |
| NFR-PRF (Performance) | 4 | US-ENB-05 |
| NFR-REL (Reliability) | 7 | US-ENB-01, US-ENB-03 |
| NFR-SEC (Security) | 16 | US-ENB-02, US-ENB-03, US-ENB-04 |
| NFR-OBS (Observability) | 3 | US-ENB-03 |
| NFR-MNT (Maintainability) | 8 | US-ENB-06 |
| NFR-USA (Usability) | 3 | US-AGT-01, US-AGT-02, US-TCG-06 |
| NFR-POR (Portability) | 2 | US-ENB-02 |
| **Non-functional total** | **47** | **all covered** |
| **Grand total** | **135** | **135 covered, 0 uncovered** |

## Requirements deliberately not given a dedicated story

None. Every requirement is served. Three are worth noting because they are served as acceptance
criteria within a broader story rather than as stories of their own:

- **FR-HND-04** (never push to a repository, never write Jenkins config) is a prohibition, not a
  capability. It appears as US-HND-01 AC4, where it is verifiable.
- **FR-AGT-06** (all durable state through the toolchain) is a standing rule expressed in
  US-AGT-01 AC2 and AC3.
- **FR-DLT-06** (delta runs respect the same gates) is US-DLT-02 AC4, since it is a property of
  delta running rather than separate work.

## Open decisions carried forward

OD-01 to OD-04 in `requirements.md` §11.9 remain open and are not story-bearing. They are
decisions for the NFR Requirements stage, and US-ENB-01 and US-ENB-04 will need revisiting once
OD-01 (backup interval) and OD-04 (file-level encryption) are settled.

---

# INVEST Verification

| Criterion | How it was verified | Result |
|---|---|---|
| **Independent** | Checked for stories that cannot be built without another being complete first. Genuine sequencing constraints are recorded below rather than hidden. | Pass, with 5 recorded constraints |
| **Negotiable** | Stories state the capability and its acceptance criteria, not the implementation. Technology choices live in `requirements.md` constraints, where they were decided. | Pass |
| **Valuable** | Each of the 49 non-enabler stories names a persona and the benefit. The 6 enabler stories are explicitly marked as enablers and name the epics they unblock, rather than claiming user value they do not have. | Pass |
| **Estimable** | Each story maps to 1-9 requirements with concrete acceptance criteria. None depends on an unresolved question. | Pass |
| **Small** | 55 stories over 135 requirements, averaging 2.5 requirements per story. The largest is US-ENB-04 at 9 security requirements, kept together because splitting confidentiality controls would let one half ship without the other. | Pass |
| **Testable** | 253 acceptance criteria in Given/When/Then form. Every story has at least one negative or boundary criterion and, where a failure mode exists, at least one error criterion. | Pass |

## Sequencing constraints

These are real dependencies, recorded rather than concealed. They constrain order, not
independence of definition.

| Story | Cannot start before | Reason |
|---|---|---|
| US-TRC-01 | US-ENB-01 | The Jira key rule is enforced as a database constraint, so the schema must exist first |
| US-AUT-01 | US-TCG-01 | Automation is generated from stored cases |
| US-HND-01 | US-AUT-01 | Assembly packages generated tests |
| US-DLT-01 | US-ING-03 | Delta detection compares against a recorded head commit |
| US-RPT-01 | US-COV-01, US-TCG-01 | Coverage reporting compares planned against generated |

Everything else can proceed in parallel once US-ENB-01 and US-ENB-02 are in place. That is the
main reason both sit in R1.

---

# Persona-to-Story Map

## P1 Test Analyst — 31 stories

US-ING-01, US-ING-02, US-ING-03, US-ING-04, US-ANA-01, US-ANA-02, US-ANA-03, US-ANA-04,
US-TRQ-01, US-TRQ-02, US-TRQ-03, US-COV-01, US-COV-03, US-TCG-01, US-TCG-02, US-TCG-03,
US-TCG-04, US-TCG-06, US-TRC-01, US-TRC-02, US-TRC-03, US-BAT-01, US-BAT-02, US-BAT-03,
US-BAT-04, US-DLT-01, US-DLT-02, US-AGT-01, US-AGT-02, US-AGT-03, US-AGT-04

## P2 Test Automation Engineer — 14 stories

US-ANA-03, US-ANA-04, US-TCG-04, US-AUT-01, US-AUT-02, US-AUT-03, US-AUT-04, US-AUT-05,
US-AUT-06, US-HND-01, US-HND-02, US-HND-03, US-RPT-03, US-AGT-04

## P3 Test Lead — 18 stories

US-TRQ-02, US-COV-01, US-COV-02, US-COV-03, US-COV-04, US-COV-05, US-TCG-03, US-TCG-05,
US-AUT-04, US-HND-03, US-TRC-01, US-TRC-02, US-TRC-03, US-TRC-04, US-BAT-04, US-DLT-02,
US-DLT-03, US-RPT-01, US-RPT-02, US-RPT-03

## Approval authority

| Approval | Held by | Story |
|---|---|---|
| Ingested inventory | P1 | US-ING-01 |
| Application model | P1 | US-ANA-01 |
| Testable requirement set | P1 | US-TRQ-01 |
| **Coverage baseline** | **P3 only** | US-COV-04 |
| Generated test cases | P1 | US-TCG-01 |
| Generated automation | P2 | US-AUT-01 |
| Handover project | P2 | US-HND-01 |
| Coverage reduction | P3 | US-COV-05 |

The coverage baseline approval is the only one restricted to a single role, and US-COV-04 AC4
enforces that restriction. It is also the approval with the largest downstream consequence, which
is why it is the one that is enforced rather than merely assigned.

---

# Summary

**55 stories** across **13 epics**, covering **all 135 requirements** with **253 acceptance
criteria**. Sequenced into three releases: R1 walking skeleton (29 stories), R2 production baseline
(25), R3 sustaining (4). Some stories span releases where one input source or capability lands
before another.

The count sits slightly above the 35-50 estimate in the story plan. The estimate assumed roughly
120 requirements; the verified base is 135, and holding stories to a size that stays Small under
INVEST produced 55 rather than 50.

Three structural choices are worth stating plainly.

**Enabler stories are named as enablers.** Six stories in E13 carry the SQLite schema, the MCP
server, observability, security controls, scale work, and the test suite. They are marked as
enablers rather than dressed as user value, and each names the epics it unblocks. This is
substantial work and hiding it inside user-facing stories would have made those stories dishonest
about their size.

**The traceability rule is a database constraint.** US-TRC-01 and US-ENB-01 place the Jira key
requirement and the mandatory-steps requirement in the schema, not in a guideline. Across
thousands of cases generated over many sessions, a rule the model is asked to follow degrades and
a rule the storage layer enforces does not.

**Negative paths are in the acceptance criteria, not implied.** Every story carries at least one
negative or boundary criterion. A system built to generate negative test coverage that lacked
negative acceptance criteria of its own would be difficult to take seriously.
