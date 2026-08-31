# Business Rules — U2 Ingestion and Analysis

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U2 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-29

U2 reads from outside the workspace and turns what it finds into the application
model. Everything here is either a deterministic rule the toolchain applies, or a
contract the agent's payload must satisfy.

---

# BR-U2-1: Resource Type Inference

**Decision**: ordered pattern rules, first match wins, each recording which rule fired.

## BR-U2-1.1 The rules

Evaluated in order. The first match decides.

| # | Pattern | Type |
|---|---|---|
| 1 | `/browse/<KEY>-<n>` or `/rest/api/*/issue/<KEY>-<n>` | `jira-issue` |
| 2 | A bare `<KEY>-<n>` token | `jira-issue` |
| 3 | `jql=` in the query string, or a bare JQL-shaped string | `jira-query` |
| 4 | `/wiki/spaces/<SPACE>/pages/<id>` or `pageId=<id>` | `confluence-page` |
| 5 | `/wiki/spaces/<SPACE>` with no page segment | `confluence-space` |
| 6 | `/projects/<PROJ>/repos/<slug>` or `bitbucket.*/<owner>/<repo>` | `bitbucket-repo` |
| 7 | A path ending `openapi.{yaml,yml,json}` or `swagger.{yaml,yml,json}` | `openapi-spec` |
| 8 | A local path that is an existing directory | `design-folder` |
| 9 | Anything else | `unclassified` |

## BR-U2-1.2 Recording the match

Each resource stores `inferred_from` — the rule number and the pattern that fired.

**A wrong inference is otherwise mysterious.** When a Confluence URL is read as a
Bitbucket repository, "rule 6 matched `/projects/.../repos/`" turns a puzzling
failure into a one-line fix. Storing only the verdict would leave the operator
guessing which of nine rules to suspect.

## BR-U2-1.3 Unclassified entries

Reported, never guessed at and never dropped (FR-ING-02). The ingestion report lists
them with the raw reference so the operator can correct `resources.md`.

## BR-U2-1.4 Duplicates

Recognised by exact raw reference after trimming. A repeated link is stored once
(US-ING-01 AC3).

---

# BR-U2-2: Jira and Confluence Normalisation

## BR-U2-2.1 Jira issue fields

Stored: key, issue type, summary, description, acceptance criteria, status, labels,
parent or epic key, and comments. All flattened from ADF to text by the MCP server.

## BR-U2-2.2 Detail level

**Decision**: `low` when the description is under **200 characters** **and** there are
no acceptance criteria. Both conditions, so a story is flagged only when it is thin on
both counts.

A short story with clear acceptance criteria is perfectly usable, and a long
description without formal criteria usually carries enough narrative to work from.
Flagging either alone would fire on much of the backlog, and a flag that common stops
being read.

*An earlier draft of this rationale argued the opposite — that a long description
without criteria is still thin — which is the case for option B rather than the option
chosen. Corrected to match the decision.*

`low` is a flag, not a rejection. The story is stored and usable; the flag makes the
thinness visible at ingestion rather than surfacing later as unexplainable thin
coverage (US-ING-02 AC4).

## BR-U2-2.3 Confluence tables

Preserved as structured rows, not flattened into prose (FR-ING-04). A table of
validation rules is the most directly useful thing a Confluence page can contain, and
flattening destroys exactly that.

## BR-U2-2.4 Not-found versus not-authorised

Distinguished in the report (US-ING-02 AC6). They call for different actions: fix the
reference, or fix the permissions.

---

# BR-U2-3: Content Hashing

**Decision**: content only. Metadata is excluded.

## BR-U2-3.1 What is hashed

| Source | Hashed |
|---|---|
| Jira issue | summary + description + acceptance criteria + comment bodies |
| Confluence page | body text and structured tables |
| Source file | file contents at the ref |
| Endpoint | method + route + file + line + symbol |
| Screenshot | file bytes |
| OpenAPI spec | spec document |

Excluded: labels, status, assignee, timestamps, version numbers, page ordering.

## BR-U2-3.2 Why metadata is excluded

A Jira issue whose label changed but whose text did not is unchanged for our purposes.
Including metadata would re-ingest and re-analyse everything downstream on a harmless
field update — and worse, the delta pipeline would report churn that changed nothing
testable, training the operator to ignore it.

**Status is the interesting exclusion.** A story moving to Done does not change what
must be tested. If the story text changes, the hash catches it.

## BR-U2-3.3 Skip-if-unchanged

A matching hash means no re-fetch and no re-store (FR-ING-10, NFR-PRF-04). The
existing artefact's `last_ingested_at` is updated so the operator can see it was
checked.

---

# BR-U2-4: Design Asset Parsing

**Decision**: split on double underscore; the manifest overrides field by field.

## BR-U2-4.1 Filename convention

| Segments | Interpretation |
|---|---|
| 2 | `<feature>__<screen>`, state defaults to `default` |
| 3 | `<feature>__<screen>__<state>` |
| 1, or 4+ | Unassociated; reported |

Segments are slugified. The extension is stripped before splitting.

## BR-U2-4.2 Manifest precedence

`screens.manifest.yaml`, keyed by filename, overrides **field by field**. A manifest
entry supplying only `feature` leaves the parsed screen and state intact.

Wholesale replacement would force an operator correcting one attribute to restate the
others, and a restatement is a chance to introduce an error.

The manifest may also supply `route` and a `jira_key` that the filename cannot carry.

## BR-U2-4.3 Unassociated files

Listed with their filenames, never dropped and never guessed at (US-ING-04 AC3).

## BR-U2-4.4 Safe loading

The manifest is parsed with a safe YAML loader that cannot instantiate arbitrary types
(NFR-SEC-05). It is a file from a shared folder, and a shared folder is an untrusted
input.

---

# BR-U2-5: API Model Derivation

**Decision**: merge, preferring the spec for shapes and the code for existence.

## BR-U2-5.1 The merge

| Situation | Result |
|---|---|
| In code and in spec | Endpoint exists. Shapes from the spec, `shape_source=specified` |
| In code, not in spec | Endpoint exists. Shapes inferred from the handler, `shape_source=inferred` |
| **In spec, not in code** | **Not an endpoint.** Recorded as a discrepancy |
| Shapes disagree | Spec wins for shapes; the disagreement is recorded |

## BR-U2-5.2 Why code decides existence

**Code is what runs.** A spec entry with no implementation would produce tests for an
endpoint that returns 404 — tests that fail for a reason unrelated to any defect, and
that erode trust in the whole suite.

The reverse is safe: an endpoint in code but not the spec genuinely exists, and its
shape being inferred is recorded so a later failure can be judged against the weaker
source.

## BR-U2-5.3 Authentication requirement

`none`, `required`, or `unknown`. **`unknown` is never defaulted to `none`.**
Defaulting an undetermined authentication requirement to public would hide a
security-relevant gap (US-ANA-03 AC3).

## BR-U2-5.4 Status codes

Every code found in the handler is recorded, including ones absent from the spec.
Those are exactly the error paths negative test cases are derived from
(US-ANA-03 AC4).

---

# BR-U2-6: Discrepancy Detection

**Decision**: record incompatible claims about the same testable thing.

## BR-U2-6.1 The test

**Would a tester write a different test depending on which source they believed?**

If yes, it is a discrepancy. If no, it is a difference and is not recorded.

## BR-U2-6.2 Recorded

| Discrepancy | Sources |
|---|---|
| Endpoint in the spec, absent from the code | OpenAPI vs code |
| Request or response shape disagrees | OpenAPI vs handler |
| Status code documented but not returned | OpenAPI vs handler |
| Screen in Figma, absent from the live application | Design vs live |
| Screen materially different from its screenshot | Design vs live |
| Rule stated in Jira contradicting the implementation | Jira vs code |
| Auth requirement differs between spec and code | OpenAPI vs code |

## BR-U2-6.3 Not recorded

Wording, formatting, field ordering, comment differences, whitespace, or a Confluence
page phrasing a rule differently from Jira while meaning the same thing.

**Recording everything buries the signal.** A discrepancy report nobody reads because
it is mostly noise is worse than none, because it looks like diligence.

## BR-U2-6.4 Never resolved

A discrepancy is recorded against both sources with both claims. The system does not
decide which is correct — that requires knowing intent, which is a human judgement
(FR-ANA-08).

The one exception is BR-U2-5.2, where code decides *existence*. That is a rule about
what is real, not about which source is right.

---

# BR-U2-7: Agent Payload Contracts

The agent supplies what needs judgement. These are the shapes S2 accepts.

## BR-U2-7.1 Feature model

Each feature: `slug`, `name`, optional `parent_slug`, `description`, and
`source_artefact_ids` — at least one. A feature grounded in no artefact is rejected:
it is an invention, and inventions are what the traceability rule exists to stop.

Cycles in `parent_slug` are rejected.

## BR-U2-7.2 Business rules

Each: `feature_slug`, `rule_kind`, `condition`, `effect`, `is_documented`,
`source_artefact_ids`. Where the agent detects a contradiction, both rules are
supplied with `contradicts` naming the other.

## BR-U2-7.3 UI model

Each screen: `name`, `state`, optional `feature_slug` and `route`, and a `source` of
`figma`, `live`, `code` or `figma+live`. Each element: `role`, `accessible_name`,
`test_id`, an ordered `locator_chain`, `is_fragile`, `is_verified`.

**`is_verified` is true only for locators confirmed against the running application.**
The agent derives them by exploring the live AUT with Playwright MCP (FR-ANA-06) —
that stays with the agent rather than the toolchain, because deciding what matters on
a screen is a judgement. When the environment is unreachable, every derived locator is
stored unverified rather than presented as confirmed (US-ANA-04 AC5).

A locator that works and one that ought to are different facts, and the flag is what
keeps them distinguishable downstream: U4's automatability classifier reads it, and
U5 annotates a generated test built on an unverified locator.

## BR-U2-7.4 Unassigned artefacts

An artefact mapping to no feature is listed, not forced into the nearest one
(US-ANA-01 AC3). Forcing it would create a false link that later reads as evidence.

---

# BR-U2-8: Partial Ingestion

**Decision**: report everything and let the operator decide.

## BR-U2-8.1 The report

Per resource: succeeded, skipped-unchanged, failed with reason, or unclassified. Plus
totals and a list of not-found versus not-authorised failures.

## BR-U2-8.2 A partial run does not block the stage

The unit completes. The ingest gate is the operator's to approve, and a partial
ingestion is a fact for them to weigh.

**The system cannot know whether the missing repository mattered.** Refusing to
complete would substitute its ignorance for their judgement; completing silently would
deny them the fact. Reporting and stopping is the only honest option.

## BR-U2-8.3 Isolation

Per resource, under U1's `isolate` (NFR-REL-04). One unreachable source does not
discard an hour of successful retrieval.

## BR-U2-8.4 Retry

U1's bounded retry applies to transient failures — connection, timeout, 429, 5xx.
Never to 4xx authentication or validation failures.

---

# Rule-to-Requirement Traceability

| Rule | Requirements | Stories |
|---|---|---|
| BR-U2-1 Type inference | FR-ING-01, FR-ING-02 | US-ING-01 |
| BR-U2-2 Normalisation | FR-ING-03, FR-ING-04 | US-ING-02 |
| BR-U2-3 Content hashing | FR-ING-08, FR-ING-10, NFR-PRF-04 | US-ING-01, US-ING-04 |
| BR-U2-4 Design assets | FR-ING-07 | US-ING-04 |
| BR-U2-5 API derivation | FR-ING-06, FR-ANA-04 | US-ING-03, US-ANA-03 |
| BR-U2-6 Discrepancies | FR-ANA-08 | US-ANA-02, US-ANA-04 |
| BR-U2-7 Payload contracts | FR-ANA-01, FR-ANA-02, FR-ANA-03, FR-ANA-05, FR-ANA-06, FR-ANA-07 | US-ANA-01, US-ANA-02, US-ANA-04 |
| BR-U2-8 Partial ingestion | FR-ING-05, FR-ING-09, NFR-REL-04 | US-ING-02, US-ING-03 |
