# Domain Entities — U1 Core Platform

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U1 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-29

Technology-agnostic. Storage mapping appears only where an integrity rule is enforced by a
constraint, because that enforcement point is a business decision rather than an implementation one.

---

## Entity Count

`requirements.md` §10.2 lists **16 rows**, two of which name a pair — `screen`/`ui_element` and
`run`/`unit_state`. Expanded, that is **18 entities**.

---

## Value Objects

Constructed, validated, immutable. A value object that cannot be constructed validly does not exist,
which removes a whole class of downstream checking.

| Value object | Form | Construction rule |
|---|---|---|
| `TestCaseId` | `TC-<FEATURE_SLUG>-<00001>` | Slug is lowercase alphanumeric with hyphens; sequence is 5 digits, zero-padded |
| `RequirementId` | `TR-<FEATURE_SLUG>-<00001>` | As above |
| `CoverageItemId` | `CI-<FEATURE_SLUG>-<00001>` | As above |
| `AutomatedTestId` | `AT-<FEATURE_SLUG>-<00001>` | As above |
| `JiraKey` | `<PROJECT>-<n>` | Project is 2-10 uppercase letters; n is a positive integer |
| `ContentHash` | 64 hex characters | SHA-256 of normalised content |
| `FeatureSlug` | lowercase, hyphenated, 1-60 chars | Derived from the feature name, uniqueness enforced |
| `Ordinal` | integer >= 1 | Step ordering; gaps are not permitted within a case |
| `SimilarityScore` | float in [0.0, 1.0] | Rejected outside range |
| `RiskScore` | integer in [0, 100] | With its band |
| `Correlationid` | UUIDv4 string | One per unit of work |

### Enumerations

| Enum | Values |
|---|---|
| `LinkType` | `direct-story`, `derived-from-commit`, `confluence`, `code-symbol`, `screenshot` |
| `TestType` | `functional-positive`, `functional-negative`, `boundary`, `validation`, `ui-behaviour`, `api-contract`, `integration`, `permissions`, `error-handling` |
| `AutomatabilityClass` | `automatable`, `manual-only`, `needs-review` |
| `RiskBand` | `low`, `medium`, `high`, `critical` |
| `UnitState` | `not-started`, `in-progress`, `completed`, `failed`, `needs-review` |
| `StageName` | `ingest`, `analyse`, `requirements`, `coverage`, `cases`, `automation`, `handover` |
| `ChangeClassification` | `unchanged`, `requires-update`, `obsolete` |
| `ResourceType` | `jira-issue`, `jira-query`, `confluence-page`, `confluence-space`, `bitbucket-repo`, `openapi-spec`, `design-folder`, `unclassified` |
| `CoverageTechnique` | `equivalence-partitioning`, `boundary-value-analysis`, `decision-table`, `state-transition`, `direct` |
| `ErrorCode` | see [business-logic-model.md](business-logic-model.md) §4 |

---

## Entities

### 1. `resource`

A declared input from `resources.md` or the design-asset folder.

| Attribute | Type | Notes |
|---|---|---|
| `id` | int | Surrogate |
| `raw_ref` | str | The link or path exactly as written |
| `type` | `ResourceType` | Inferred; `unclassified` when inference fails |
| `inferred_from` | str | The pattern that produced the type — evidence, not just a verdict |
| `status` | str | `pending`, `ingested`, `failed`, `unclassified` |
| `failure_reason` | str? | Present only when `status = failed` |
| `first_seen_at`, `last_ingested_at` | timestamp | |

**Cardinality**: one `resource` to many `artefact`.

### 2. `artefact`

An ingested item with provenance.

| Attribute | Type | Notes |
|---|---|---|
| `id` | int | |
| `resource_id` | int | FK |
| `kind` | str | `jira-issue`, `confluence-page`, `source-file`, `endpoint`, `screenshot`, `openapi-spec` |
| `source_identifier` | str | Jira key, page id, file path at a ref, screenshot filename |
| `content` | text | Normalised |
| `content_hash` | `ContentHash` | Drives skip-if-unchanged |
| `metadata` | json | Kind-specific: labels, status, parent, line ranges |
| `detail_level` | str | `full`, `low` — a Jira issue with no description or acceptance criteria is `low` |
| `ingested_at` | timestamp | |
| `run_id` | int | FK, the run that ingested it |

**Unique**: (`resource_id`, `source_identifier`, `content_hash`) — re-ingesting unchanged content
creates no duplicate (FR-ING-10).

**`detail_level` is not decoration.** A thin story is visible at ingestion rather than surfacing
later as thin coverage nobody can explain.

### 3. `feature`

A node in the feature hierarchy.

| Attribute | Type | Notes |
|---|---|---|
| `id` | int | |
| `slug` | `FeatureSlug` | Unique; the identifier namespace for everything beneath it |
| `name` | str | |
| `parent_id` | int? | Self-referencing; null at root |
| `description` | text | |
| `risk_band` | `RiskBand`? | Aggregated from its requirements |

**Cardinality**: self-referencing hierarchy; one feature to many requirements, screens, endpoints.

### 4. `journey`

A multi-step user flow crossing features.

| Attribute | Type | Notes |
|---|---|---|
| `id` | int | |
| `name` | str | |
| `steps` | json | Ordered list of `{feature_id, screen_id?, endpoint_id?, description}` |

### 5. `business_rule`

A discrete extracted rule.

| Attribute | Type | Notes |
|---|---|---|
| `id` | int | |
| `feature_id` | int | FK |
| `rule_kind` | str | `validation`, `state-transition`, `calculation`, `permission` |
| `condition` | text | |
| `effect` | text | |
| `is_documented` | bool | False when found only as a code branch |
| `contradicts_id` | int? | Set when this rule conflicts with another; both are retained |

**`contradicts_id` implements FR-ANA-08 and US-ANA-02 AC4.** When Jira and code disagree, both rules
persist and point at each other. The system records the conflict; it does not resolve it.

### 6. `api_endpoint`

| Attribute | Type | Notes |
|---|---|---|
| `id` | int | |
| `feature_id` | int? | FK; null when unassigned |
| `method`, `route` | str | |
| `file_path`, `line`, `symbol` | str, int, str | From `bitbucket_endpoints` |
| `request_shape`, `response_shapes` | json? | |
| `status_codes` | json | Including codes found only in source |
| `auth_requirement` | str | `none`, `required`, `unknown` — never defaulted |
| `shape_source` | str | `specified` or `inferred` |

**`auth_requirement = unknown` is a distinct state from `none`.** Defaulting an undetermined
authentication requirement to public would hide a security-relevant gap (US-ANA-03 AC3).

### 7. `screen`

| Attribute | Type | Notes |
|---|---|---|
| `id` | int | |
| `feature_id` | int? | |
| `name`, `state` | str | From the `<feature>__<screen>__<state>` convention or the manifest |
| `route` | str? | |
| `source` | str | `figma`, `live`, `code`, `figma+live` |
| `discrepancy_id` | int? | Set when design and live differ |

### 8. `ui_element`

| Attribute | Type | Notes |
|---|---|---|
| `id` | int | |
| `screen_id` | int | FK |
| `role`, `accessible_name`, `test_id` | str? | |
| `locator_chain` | json | Ordered preference list, strongest first |
| `is_fragile` | bool | True when no semantic locator exists |
| `is_verified` | bool | True only when confirmed against the live application |

**`is_verified` separates a locator that works from one that ought to.** When the environment is
unreachable, every derived locator is stored unverified rather than presented as confirmed
(US-ANA-04 AC5).

### 9. `testable_requirement`

| Attribute | Type | Notes |
|---|---|---|
| `id` | `RequirementId` | Allocated |
| `feature_id` | int | FK |
| `statement` | text | One verifiable behaviour |
| `classification` | str | `functional`, `non-functional` |
| `category` | str | ui-behaviour, api-contract, business-rule, validation, integration, security, performance, accessibility |
| `risk_score`, `risk_band` | `RiskScore`, `RiskBand` | |
| `risk_factors` | json | Every contributing factor with its value or `unavailable` |
| `risk_is_partial` | bool | True when a factor was unavailable |
| `source_artefact_ids` | json | |

### 10. `coverage_item`

A required (requirement, test type) pairing with depth and rationale.

| Attribute | Type | Notes |
|---|---|---|
| `id` | `CoverageItemId` | |
| `requirement_id` | `RequirementId` | FK |
| `test_type` | `TestType` | |
| `technique` | `CoverageTechnique` | |
| `planned_count` | int | Expected cases from this item |
| `rationale` | text | Why this type is required — or why it is not |
| `is_required` | bool | False records an explicit not-required decision |
| `reduction_applied` | str? | The reduction technique, when one was used |
| `model_version` | str | Which coverage model version this belongs to |

**`is_required = false` rows are kept, not omitted.** An absent row and a deliberate exclusion look
identical unless the exclusion is recorded (US-COV-01 AC3).

### 11. `test_case`

| Attribute | Type | Notes |
|---|---|---|
| `id` | `TestCaseId` | Toolchain-allocated, never supplied |
| `feature_id` | int | FK |
| `coverage_item_id` | `CoverageItemId` | FK |
| `title` | str | |
| `test_type` | `TestType` | |
| `priority` | str | |
| `preconditions` | text | |
| `expected_result` | text | Overall |
| `automatability` | `AutomatabilityClass` | |
| `automatability_reason` | text | |
| `automatability_overridden_by` | str? | Actor, when a human overrode the verdict |
| `tags` | json | suite, type, feature, priority |
| `normalised_hash` | `ContentHash` | For duplicate detection |
| `bucket_key` | str | Indexed candidate selection for de-duplication |
| `is_obsolete` | bool | Soft delete |
| `obsolete_reason`, `obsoleted_by_change_id` | text?, int? | |
| `created_run_id`, `last_modified_run_id` | int | |

**Constraint** `chk_case_has_steps`: a case must have at least one `test_step`.
**Constraint** `chk_case_has_jira_link`: a case must have at least one `trace_link` resolving to a
Jira key.

### 12. `test_step`

| Attribute | Type | Notes |
|---|---|---|
| `id` | int | |
| `case_id` | `TestCaseId` | FK, cascade |
| `ordinal` | `Ordinal` | Unique within case, no gaps |
| `action` | text | Non-empty |
| `expected` | text | Non-empty |

**Constraint** `chk_step_expected_not_blank`. A step without an expected result is not a step.

### 13. `test_data`

| Attribute | Type | Notes |
|---|---|---|
| `id` | int | |
| `case_id` | `TestCaseId` | FK |
| `step_ordinal` | int? | Null when case-level |
| `field`, `value` | str | Synthetic always |
| `equivalence_class` | str | The class or boundary this value represents |
| `boundary_relation` | str? | `at`, `just-inside`, `just-outside` |

**`equivalence_class` is mandatory.** It is what makes two superficially similar cases materially
different in de-duplication, and what lets a reviewer see why a value was chosen.

### 14. `trace_link`

| Attribute | Type | Notes |
|---|---|---|
| `id` | int | |
| `source_kind`, `source_id` | str, str | The linked entity |
| `target_ref` | str | Jira key, page id, file:symbol, screenshot |
| `link_type` | `LinkType` | |
| `evidence` | text | Commit sha, page title, line number |
| `selection_basis` | text? | For `derived-from-commit`: why this key over the alternatives |
| `alternatives` | json? | Candidate keys not chosen — retained, not discarded |
| `resolved_jira_key` | `JiraKey`? | Non-null for `direct-story` and `derived-from-commit` |

### 15. `automated_test`

| Attribute | Type | Notes |
|---|---|---|
| `id` | `AutomatedTestId` | |
| `case_id` | `TestCaseId` | FK |
| `spec_path`, `test_name` | str | |
| `page_object_refs` | json | |
| `input_hash` | `ContentHash` | Inputs that produced this output; drives deterministic regeneration |
| `output_hash` | `ContentHash` | Detects hand-edits |
| `is_at_risk` | bool | Fragile locator or inferred contract |
| `at_risk_reason` | text? | |

### 16. `run`

| Attribute | Type | Notes |
|---|---|---|
| `id` | int | |
| `correlation_id` | `CorrelationId` | |
| `started_at`, `ended_at` | timestamp | |
| `kind` | str | `baseline` or `delta` |
| `operator` | str | |

### 17. `unit_state`

| Attribute | Type | Notes |
|---|---|---|
| `id` | int | |
| `unit_ref` | str | Feature slug or unit name |
| `stage` | `StageName` | |
| `state` | `UnitState` | |
| `lease_id` | str? | Non-null while `in-progress` |
| `approved_by`, `approved_at` | str?, timestamp? | |
| `approved_content_hash` | `ContentHash`? | Approval binds to content |
| `failure_reason` | text? | |
| `metrics` | json | Duration, artefacts consumed, cases produced, failures |

**Unique**: (`unit_ref`, `stage`).

**`approved_content_hash` is what makes a gate real.** Approval binds to what was approved. Modify
the content and the hash no longer matches, so the approval no longer applies (US-COV-04 AC3,
US-BAT-04 AC4).

### 18. `change_event`

| Attribute | Type | Notes |
|---|---|---|
| `id` | int | |
| `run_id` | int | FK |
| `source` | str | `bitbucket` or `jira` |
| `ref_from`, `ref_to` | str | Commit shas, or timestamps for Jira |
| `changed_refs` | json | Files or issue keys |
| `jira_keys` | json | |
| `is_unmapped` | bool | True when it traces to nothing |
| `impact_scale` | float | Proportion of the corpus affected |

---

## Relationships

```
resource 1--* artefact
feature  1--* feature (self, hierarchy)
feature  1--* testable_requirement
feature  1--* business_rule
feature  1--* screen
feature  1--* api_endpoint
screen   1--* ui_element
testable_requirement 1--* coverage_item
coverage_item        1--* test_case
test_case 1--* test_step        (cascade delete, but cases are soft-deleted)
test_case 1--* test_data
test_case 1--* trace_link       (at least one resolving to a Jira key)
test_case 1--1 automated_test   (only when automatable)
run       1--* unit_state
run       1--* change_event
change_event 1--* test_case     (via obsoleted_by_change_id)
```

**Text alternative**: a resource yields many artefacts. Features nest and own requirements, business
rules, screens and endpoints. A screen owns UI elements. A requirement yields coverage items, each
yielding test cases. A case owns its steps, data and trace links, and may have one automated test. A
run owns unit states and change events, and a change event may obsolete many cases.

---

## Integrity Rules and Their Enforcement

Each `requirements.md` §10.3 rule, and where it is enforced.

| Rule | Enforcement | Mechanism |
|---|---|---|
| A case with zero steps is invalid | **Database + domain** | `chk_case_has_steps` trigger, and D7 validation |
| A case with no Jira-resolving link is invalid | **Database + domain** | `chk_case_has_jira_link` trigger, and D3 plus D7 |
| Case identifiers are toolchain-allocated and immutable | **Database + domain** | No `UPDATE` permitted on `test_case.id`; D7 rejects a self-supplied identifier |
| Deletion is soft; obsolete records keep their reason | **Database** | `is_obsolete` with `NOT NULL` reason when true; no `DELETE` in any query module |
| A step must have a non-empty expected result | **Database** | `chk_step_expected_not_blank` |
| Step ordinals are unique and gapless within a case | **Domain** | D7 — cheaper to check in code than to express as a constraint |
| Equivalence class is mandatory on test data | **Database** | `NOT NULL` |
| Approval binds to content | **Domain** | D7 compares `approved_content_hash` |

**Two enforcement points for the two most important rules is deliberate.** The domain validator
produces a good error message the agent can act on; the database constraint makes the rule
unbreakable even if the validator is bypassed by a future code path. Neither alone is sufficient:
a constraint gives an unhelpful error, and a validator can be forgotten.

---

## Soft Delete and Audit Semantics

**Nothing is hard-deleted.** No query module contains a `DELETE` statement against a business
entity.

| Concern | Rule |
|---|---|
| Obsolete cases | `is_obsolete = true` with a mandatory reason and the originating change event |
| Active corpus | Every query filters `is_obsolete = false` unless explicitly asked otherwise |
| Coverage reporting | Obsolete cases excluded from active coverage, reported separately (US-DLT-03 AC4) |
| Audit trail | Every mutation to a case or coverage decision records actor, timestamp and change |
| Run history | `created_run_id` and `last_modified_run_id` on every case; full history via `change_event` |
| Cascade | `test_step` and `test_data` cascade on the physical row, but since cases are never physically deleted, the cascade only fires during a migration rollback |

---

## Indexes

Supporting the NFR-PRF budget at 10,000 cases.

| Index | Table | Purpose |
|---|---|---|
| `idx_case_bucket` | `test_case(bucket_key)` | De-duplication candidate selection — the index that makes NFR-PRF-03 achievable |
| `idx_case_feature_type` | `test_case(feature_id, test_type)` | Coverage report aggregation |
| `idx_case_obsolete` | `test_case(is_obsolete)` | Active-corpus filtering on every query |
| `idx_trace_source` | `trace_link(source_kind, source_id)` | Forward matrix traversal |
| `idx_trace_target` | `trace_link(target_ref)` | Reverse matrix traversal |
| `idx_trace_jira` | `trace_link(resolved_jira_key)` | Jira key coverage checks |
| `idx_artefact_hash` | `artefact(content_hash)` | Skip-if-unchanged on ingestion |
| `idx_unit_state` | `unit_state(unit_ref, stage)` | Gate checks, called on every write operation |
| `idx_step_case_ord` | `test_step(case_id, ordinal)` | Ordered step retrieval |

**`idx_case_bucket` is the single most important index in the schema.** Without it, de-duplication
degrades to a full scan and the 200 ms budget in NFR-PRF-01 becomes unreachable at volume.
