# Component Methods

**Project**: TTO Test Analyst Agent System (TAAS)
**Stage**: INCEPTION - Application Design
**Version**: 1.0
**Date**: 2026-08-28

---

## Scope of this document

Method signatures, purpose, and input/output types. **Detailed business rules are deferred to
Functional Design** (per-unit, CONSTRUCTION phase) — this document establishes the shape of the
interfaces, not the logic inside them.

Types are given in Python annotation form. `Result[T]` is the structured result type from X1: every
method that can fail returns it, and exceptions never cross a component boundary outward.

---

## Shared Types

```
Result[T]          = Ok(value: T) | Err(code: ErrorCode, message: str, remediation: str)
ErrorCode          = REJECTED_* | FAILED_* | NOT_FOUND | UNAUTHORISED | CONFLICT
TestCaseId         = branded str, format "TC-<feature-slug>-<seq:05d>"
JiraKey            = branded str, format "<PROJECT>-<number>"
LinkType           = direct-story | derived-from-commit | confluence | code-symbol | screenshot
TestType           = functional-positive | functional-negative | boundary | validation
                   | ui-behaviour | api-contract | integration | permissions | error-handling
UnitState          = not-started | in-progress | completed | failed | needs-review
StageName          = ingest | analyse | requirements | coverage | cases | automation | handover
```

**`ErrorCode` separates two families deliberately.** `REJECTED_*` means the agent supplied
something invalid and must fix it. `FAILED_*` means the system had a problem and the agent should
not retry blindly. Conflating them would make the agent respond to a missing Jira key the same way
it responds to an unreachable database.

---

# Domain Core

## D1: DomainModel

| Method | Signature | Purpose |
|---|---|---|
| `TestCase.__init__` | `(title, feature_id, test_type, priority, preconditions, steps: list[TestStep], expected_result, test_data, tags) -> TestCase` | Construct a case; raises at construction if `steps` is empty |
| `TestStep.__init__` | `(ordinal: int, action: str, expected: str, data: Optional[TestData]) -> TestStep` | Construct a step; `expected` may not be blank |
| `TraceLink.__init__` | `(source_id, target_ref, link_type: LinkType, evidence: str) -> TraceLink` | Construct a typed link |
| `to_dict` | `(entity) -> dict` | Serialise any entity to a plain dictionary |
| `from_dict` | `(kind: str, d: dict) -> Result[Entity]` | Deserialise; validates shape |

## D2: CoverageModeller

| Method | Signature | Purpose |
|---|---|---|
| `derive_coverage` | `(requirements: list[TestableRequirement], rules: list[BusinessRule], depth_policy: DepthPolicy) -> CoverageModel` | Produce required test types per requirement with rationale |
| `derive_depth` | `(requirement, technique_inputs) -> list[CoverageItem]` | Apply equivalence partitioning, boundary analysis, decision tables, state transitions |
| `apply_reduction` | `(items: list[CoverageItem], technique: ReductionTechnique) -> tuple[list[CoverageItem], ReductionRecord]` | Reduce combinatorial expansion, recording the technique |
| `compute_yield` | `(model: CoverageModel) -> YieldForecast` | Expected cases per feature, per test type, and total with derivation |
| `find_uncovered` | `(model, requirements) -> list[Gap]` | Requirements with no planned coverage |
| `apply_risk_reduction` | `(model, feature_id, decision: ReductionDecision) -> Result[CoverageModel]` | Mark a feature reduced-depth; refuses silently on high risk without override |

## D3: TraceabilityResolver

| Method | Signature | Purpose |
|---|---|---|
| `require_jira_key` | `(links: list[TraceLink], known_keys: set[JiraKey]) -> Result[JiraKey]` | Enforce FR-TRC-01; fails if no link resolves to a known key |
| `derive_key_from_commits` | `(file_path: str, commits: list[CommitRecord]) -> Result[DerivedLink]` | Resolve a key from commit history; records selection basis and retains alternatives |
| `classify_link` | `(link: TraceLink) -> LinkType` | Determine link type |
| `build_matrix` | `(links: list[TraceLink]) -> TraceMatrix` | Bidirectional requirement-case-test matrix |
| `to_gap` | `(behaviour: DiscoveredBehaviour, attempts: list[str]) -> Gap` | Route untraceable behaviour to the gap set with what was tried |

## D4: SimilarityAnalyzer

| Method | Signature | Purpose |
|---|---|---|
| `normalise` | `(case: TestCase) -> NormalisedCase` | Lowercase, collapse whitespace, order steps and expectations, exclude test data |
| `similarity` | `(a: NormalisedCase, b: NormalisedCase) -> float` | Score in `[0, 1]`; reflexive and symmetric |
| `classify` | `(a, b, threshold: float) -> DuplicateVerdict` | identical, near-duplicate, or distinct |
| `is_material_difference` | `(a: TestCase, b: TestCase) -> bool` | Differing equivalence class counts as material even at high similarity |

## D5: IdentifierAllocator

| Method | Signature | Purpose |
|---|---|---|
| `allocate` | `(kind: EntityKind, state: SequenceState) -> tuple[Id, SequenceState]` | Monotonic allocation scoped to entity kind |
| `encode` | `(id: Id) -> str` | Canonical string form |
| `decode` | `(s: str) -> Result[Id]` | Parse string form |
| `is_stable_for` | `(existing: Entity, incoming: Entity) -> bool` | Whether a regenerated entity retains its identifier |

## D6: Classifier

| Method | Signature | Purpose |
|---|---|---|
| `rate_risk` | `(requirement, signals: RiskSignals) -> RiskRating` | Rate from criticality, complexity, integration surface, change frequency; each factor recorded, missing factors marked unavailable |
| `classify_automatability` | `(case, ui_model, api_model) -> AutomatabilityVerdict` | automatable, manual-only, or needs-review with basis |
| `apply_override` | `(verdict, override: HumanOverride) -> AutomatabilityVerdict` | Record a human decision with actor and reason |

## D7: IntegrityValidator

| Method | Signature | Purpose |
|---|---|---|
| `validate_case` | `(case, links, known_keys) -> Result[ValidatedCase]` | Steps present, expectations present, Jira key resolvable, identifier not self-supplied |
| `validate_coverage` | `(model) -> Result[CoverageModel]` | Internal consistency of the coverage model |
| `validate_batch` | `(cases, links, known_keys) -> BatchValidation` | Validate a whole batch, reporting every failure rather than the first |

## D8: ImpactAnalyzer

| Method | Signature | Purpose |
|---|---|---|
| `map_impact` | `(changes: ChangeSet, graph: TraceGraph) -> ImpactSet` | Changed files and issues to affected features, requirements, cases, tests |
| `classify` | `(impact: ImpactSet) -> list[ClassifiedImpact]` | unchanged, requires-update, or obsolete with reason |
| `find_unmapped` | `(changes, graph) -> list[UnmappedChange]` | Changes touching nothing traceable |
| `assess_scale` | `(impact: ImpactSet, corpus_size: int) -> ImpactScale` | Proportion of the corpus affected, reported before regeneration |

---

# Application Services

Every service method opens exactly one transaction and commits or rolls back as a whole.

## S1: IngestionService

| Method | Signature | Purpose |
|---|---|---|
| `ingest_resources` | `(manifest_path: Path, correlation_id: str) -> Result[IngestionReport]` | Full ingestion across all declared resources; per-resource failures isolated |
| `ingest_single` | `(resource_ref: str) -> Result[ArtefactSet]` | Ingest one resource |
| `list_unclassified` | `() -> list[UnclassifiedEntry]` | Manifest entries whose type could not be inferred |

## S2: AnalysisService

| Method | Signature | Purpose |
|---|---|---|
| `upsert_feature_model` | `(payload: FeatureModelPayload) -> Result[FeatureModel]` | Store the agent-reasoned feature hierarchy and journeys |
| `derive_api_model` | `(repo_ids: list[str]) -> Result[ApiModel]` | Toolchain-derived from endpoints and OpenAPI; no agent involvement |
| `upsert_ui_model` | `(payload: UiModelPayload) -> Result[UiModel]` | Store screens, components, states and locator chains from agent Playwright exploration |
| `upsert_business_rules` | `(payload: BusinessRulePayload) -> Result[list[BusinessRule]]` | Store extracted rules |
| `record_discrepancy` | `(a: SourceRef, b: SourceRef, description: str) -> Result[Discrepancy]` | Record conflicting sources without resolving them |
| `list_unassigned_artefacts` | `() -> list[Artefact]` | Artefacts mapping to no feature |

## S3: TestableRequirementService

| Method | Signature | Purpose |
|---|---|---|
| `upsert_requirements` | `(feature_id, payload: RequirementPayload) -> Result[list[TestableRequirement]]` | Validate atomicity, rate risk, enforce Jira key, store |
| `identify_edge_cases` | `(requirement_id, payload: EdgeCasePayload) -> Result[list[EdgeCase]]` | Store boundaries and failure scenarios |
| `query_requirements` | `(filter: RequirementFilter) -> list[TestableRequirement]` | Read |

## S4: CoverageService

| Method | Signature | Purpose |
|---|---|---|
| `build_model` | `(feature_id: Optional[str]) -> Result[CoverageModel]` | Derive coverage for one feature or all |
| `forecast_yield` | `(model_version: str) -> Result[YieldForecast]` | Expected counts with derivation |
| `approve_baseline` | `(approver: str, role: Role, model_version: str) -> Result[Approval]` | Test Lead only; records who, when, what |
| `is_approved` | `(model_version: str) -> bool` | Gate check used by S5 |
| `apply_reduction` | `(feature_id, decision: ReductionDecision) -> Result[CoverageModel]` | Risk-based reduction with recorded rationale |

## S5: TestCaseService

| Method | Signature | Purpose |
|---|---|---|
| `upsert_cases` | `(feature_id, payload: CaseBatchPayload, correlation_id) -> Result[CaseBatchReport]` | Validate, de-duplicate, allocate identifiers, classify, enforce traceability, commit atomically, emit views |
| `check_duplicates` | `(candidate: TestCase) -> DuplicateVerdict` | Read-only pre-check the agent may call before submitting |
| `query_cases` | `(filter: CaseFilter) -> list[TestCase]` | Read |
| `get_case` | `(id: TestCaseId) -> Result[TestCase]` | Read one with steps and links |
| `emit_views` | `(feature_id: Optional[str]) -> Result[ViewManifest]` | Regenerate sharded Markdown and YAML |

## S6: AutomationService

| Method | Signature | Purpose |
|---|---|---|
| `emit_automation` | `(feature_id, correlation_id) -> Result[EmissionReport]` | Render automatable cases to TypeScript deterministically |
| `detect_hand_edits` | `(feature_id) -> list[HandEditedFile]` | Compare emitted files against last-emitted hashes |
| `list_deferred` | `(feature_id) -> list[DeferredCase]` | Manual-only and needs-review cases with reasons |

## S7: HandoverService

| Method | Signature | Purpose |
|---|---|---|
| `assemble` | `(output_dir: Path) -> Result[HandoverPackage]` | Assemble the complete Playwright project |
| `verify` | `(package_dir: Path) -> Result[VerificationReport]` | Reference integrity, TypeScript compilation, test enumeration |
| `produce_manifest` | `(package_dir: Path) -> Result[HandoverManifest]` | Every test with case id, Jira key, tags; reconciled against the filesystem |

## S8: ReportingService

| Method | Signature | Purpose |
|---|---|---|
| `coverage_report` | `(format: OutputFormat) -> Result[Report]` | Planned versus generated with derivation |
| `gap_report` | `(format) -> Result[Report]` | All five gap categories, empty categories shown |
| `automation_report` | `(format) -> Result[Report]` | Automated, deferred, at-risk |
| `traceability_matrix` | `(format) -> Result[Report]` | Bidirectional matrix, Markdown and CSV |

## S9: DeltaService

| Method | Signature | Purpose |
|---|---|---|
| `detect_changes` | `(since: Optional[datetime]) -> Result[ChangeSet]` | Bitbucket ref range and Jira updated-since |
| `classify_impact` | `(changes: ChangeSet) -> Result[list[ClassifiedImpact]]` | Map and classify affected artefacts |
| `retire_obsolete` | `(impacts, change_event_id) -> Result[RetirementReport]` | Soft-delete with reason and originating change |
| `run_history` | `(entity_id: str) -> list[RunRecord]` | Every run that created or modified an entity |

## S10: RunStateService

| Method | Signature | Purpose |
|---|---|---|
| `begin_unit` | `(unit_id, stage: StageName, correlation_id) -> Result[UnitLease]` | Mark in-progress; refuses if already completed without explicit regeneration flag |
| `complete_unit` | `(lease: UnitLease, outputs: OutputRefs) -> Result[None]` | Transactional state and output commit |
| `fail_unit` | `(lease: UnitLease, reason: str) -> Result[None]` | Record failure without affecting other units |
| `get_status` | `(scope: Optional[str]) -> StatusReport` | Reporting only — returns what is done and what remains, and never a recommendation |
| `approve_stage` | `(unit_id, stage, approver, role) -> Result[Approval]` | Record a gate approval |
| `is_gate_open` | `(unit_id, stage) -> bool` | Whether the prior stage is approved and unmodified |
| `detect_stale_lock` | `() -> Optional[StaleLock]` | Identify a lock left by a killed process, with recovery guidance |

**There is deliberately no `next_unit()` method.** Constraint C-12 reserves scope selection to the
operator, and the absence of the method is how that constraint is enforced structurally rather than
by instruction.

---

# MCP Tool Surface

Two tiers, per the Q2 decision.

## Write Tier — coarse, transactional

Each call performs one complete unit of work, owns its transaction, and applies fully or not at all.

| Tool | Input | Output | Service |
|---|---|---|---|
| `ingest_resources` | `{manifest_path?, resource_refs?}` | `IngestionReport` | S1 |
| `analysis_upsert` | `{feature_model, journeys, business_rules}` | `AnalysisReport` | S2 |
| `api_model_derive` | `{repo_ids}` | `ApiModel` | S2 |
| `ui_model_upsert` | `{screens, components, locator_chains}` | `UiModelReport` | S2 |
| `requirements_upsert` | `{feature_id, requirements, edge_cases}` | `RequirementReport` | S3 |
| `coverage_build` | `{feature_id?}` | `CoverageModel` | S4 |
| `coverage_approve` | `{approver, role, model_version}` | `Approval` | S4 |
| `coverage_reduce` | `{feature_id, reason, override?}` | `CoverageModel` | S4 |
| `testcases_upsert` | `{feature_id, cases[]}` | `CaseBatchReport` | S5 |
| `automation_emit` | `{feature_id}` | `EmissionReport` | S6 |
| `handover_assemble` | `{output_dir}` | `HandoverPackage` | S7 |
| `handover_verify` | `{package_dir}` | `VerificationReport` | S7 |
| `delta_detect` | `{since?}` | `ChangeSet` | S9 |
| `delta_classify` | `{change_set_id}` | `ClassifiedImpacts` | S9 |
| `delta_retire` | `{impact_ids, change_event_id}` | `RetirementReport` | S9 |
| `unit_begin` | `{unit_id, stage, regenerate?}` | `UnitLease` | S10 |
| `unit_complete` | `{lease_id, outputs}` | `Ok` | S10 |
| `stage_approve` | `{unit_id, stage, approver, role}` | `Approval` | S10 |
| `reports_generate` | `{kind, format}` | `Report` | S8 |
| `views_emit` | `{feature_id?}` | `ViewManifest` | S5 |

## Read Tier — fine-grained, cheap

| Tool | Input | Output |
|---|---|---|
| `resources_list` | `{}` | declared resources with status |
| `artefacts_query` | `{type?, feature_id?, since?}` | matching artefacts |
| `features_list` | `{}` | feature hierarchy |
| `feature_get` | `{feature_id}` | one feature with its links |
| `requirements_query` | `{feature_id?, category?, risk?}` | matching requirements |
| `coverage_get` | `{feature_id?}` | coverage items |
| `coverage_forecast` | `{model_version?}` | yield forecast with derivation |
| `testcases_query` | `{feature_id?, type?, tag?, automatable?}` | matching cases |
| `testcase_get` | `{case_id}` | one case with steps, data, links |
| `duplicates_check` | `{candidate_case}` | duplicate verdict, no write |
| `trace_query` | `{from_id?, to_id?, link_type?}` | matching links |
| `trace_matrix` | `{format}` | bidirectional matrix |
| `gap_query` | `{category?}` | gaps by category |
| `run_status` | `{scope?}` | unit and stage status |
| `unit_state_get` | `{unit_id}` | one unit's per-stage state |
| `health_check` | `{}` | database, schema version, MCP reachability |

**Note on `duplicates_check`.** It sits in the read tier so the agent can test a candidate before
committing to a batch, at no transactional cost. `testcases_upsert` re-checks regardless — the read
tool is a convenience, never the enforcement point.

---

# Platform

## X1: ResultAndErrors

| Method | Signature | Purpose |
|---|---|---|
| `ok` | `(value: T) -> Result[T]` | Success |
| `err` | `(code: ErrorCode, message: str, remediation: str) -> Result[T]` | Failure with guidance |
| `sanitise` | `(message: str, workspace_root: Path) -> str` | Strip paths outside the workspace and internal stack detail |
| `is_rejection` | `(result) -> bool` | Whether the agent should fix its input rather than retry |

## X2: StructuredLogger

| Method | Signature | Purpose |
|---|---|---|
| `bind` | `(correlation_id: str, unit_id?: str) -> Logger` | Context-bound logger |
| `log` | `(level, message, **fields) -> None` | Structured entry with redaction applied |
| `record_metrics` | `(unit_id, stage, metrics: UnitMetrics) -> None` | Duration, artefacts consumed, cases produced, failures |

## X3: ConfigAndSecrets

| Method | Signature | Purpose |
|---|---|---|
| `load` | `() -> Result[Config]` | Read from environment and credential store; fails naming any missing variable |
| `get_secret` | `(name: str) -> Result[SecretStr]` | Retrieve a credential; the value never enters a log or an artefact |

## X4: ResilienceGateway

| Method | Signature | Purpose |
|---|---|---|
| `with_retry` | `(op: Callable[[], Result[T]], policy: RetryPolicy) -> Result[T]` | Bounded retry with backoff, every attempt logged |
| `isolate` | `(items, op) -> IsolatedResults` | Per-item failure isolation so one failure does not stop the batch |

## X5: HealthCheck

| Method | Signature | Purpose |
|---|---|---|
| `check` | `() -> HealthReport` | Database accessibility, schema version, per-server MCP reachability reported independently |
