"""Parameterised SQL, held apart from the repository logic.

Every statement binds its parameters. No f-string, no concatenation, no format()
anywhere in a query path (NFR-SEC-04). Keeping the SQL in one place makes that
reviewable at a glance rather than scattered through method bodies.

There is no DELETE against a business entity anywhere in this package. Deletion is
soft: obsolete rows are retained with their reason and the change that caused them.
"""

from __future__ import annotations

# --- artefacts ---------------------------------------------------------------
ARTEFACT_UPSERT = """
INSERT INTO artefact (resource_id, kind, source_identifier, content, content_hash,
                      metadata, detail_level, ingested_at, run_id)
VALUES (:resource_id, :kind, :source_identifier, :content, :content_hash,
        :metadata, :detail_level, :ingested_at, :run_id)
ON CONFLICT (resource_id, source_identifier, content_hash) DO NOTHING
"""
ARTEFACT_BY_HASH = "SELECT * FROM artefact WHERE content_hash = :content_hash LIMIT 1"
ARTEFACT_PAGE = """
SELECT * FROM artefact
WHERE (:kind IS NULL OR kind = :kind) AND id > :after
ORDER BY id LIMIT :limit
"""
KNOWN_JIRA_KEYS = """
SELECT DISTINCT source_identifier FROM artefact WHERE kind = 'jira-issue'
"""

# --- resources ---------------------------------------------------------------
RESOURCE_UPSERT = """
INSERT INTO resource (raw_ref, type, inferred_from, status, failure_reason, first_seen_at)
VALUES (:raw_ref, :type, :inferred_from, :status, :failure_reason, :first_seen_at)
ON CONFLICT (raw_ref) DO UPDATE SET
    type = excluded.type,
    inferred_from = excluded.inferred_from,
    status = excluded.status,
    failure_reason = excluded.failure_reason,
    last_ingested_at = excluded.first_seen_at
"""
RESOURCE_ALL = "SELECT * FROM resource ORDER BY id"
RESOURCE_UNCLASSIFIED = "SELECT * FROM resource WHERE type = 'unclassified' ORDER BY id"
RESOURCE_ID_FOR_REF = "SELECT id FROM resource WHERE raw_ref = :raw_ref"

# --- features ----------------------------------------------------------------
FEATURE_UPSERT = """
INSERT INTO feature (slug, name, parent_id, description, risk_band)
VALUES (:slug, :name, :parent_id, :description, :risk_band)
ON CONFLICT (slug) DO UPDATE SET
    name = excluded.name,
    parent_id = excluded.parent_id,
    description = excluded.description,
    risk_band = excluded.risk_band
"""
FEATURE_BY_SLUG = "SELECT * FROM feature WHERE slug = :slug"
FEATURE_ALL = "SELECT * FROM feature ORDER BY id"

# --- application model owned by S2 -------------------------------------------
# U1 created these tables; U2 is the first unit that writes them.
JOURNEY_INSERT = """
INSERT INTO journey (name, steps) VALUES (:name, :steps)
"""
JOURNEY_ALL = "SELECT * FROM journey ORDER BY id"

RULE_INSERT = """
INSERT INTO business_rule (feature_id, rule_kind, condition, effect, is_documented,
                           contradicts_id)
VALUES (:feature_id, :rule_kind, :condition, :effect, :is_documented, :contradicts_id)
"""
RULE_FOR_FEATURE = "SELECT * FROM business_rule WHERE feature_id = :feature_id ORDER BY id"
RULE_ALL = "SELECT * FROM business_rule ORDER BY id"

ENDPOINT_UPSERT = """
INSERT INTO api_endpoint (feature_id, method, route, file_path, line, symbol,
                          request_shape, response_shapes, status_codes,
                          auth_requirement, shape_source)
VALUES (:feature_id, :method, :route, :file_path, :line, :symbol, :request_shape,
        :response_shapes, :status_codes, :auth_requirement, :shape_source)
"""
ENDPOINT_ALL = "SELECT * FROM api_endpoint ORDER BY id"

SCREEN_INSERT = """
INSERT INTO screen (feature_id, name, state, route, source, discrepancy_id)
VALUES (:feature_id, :name, :state, :route, :source, :discrepancy_id)
"""
SCREEN_ALL = "SELECT * FROM screen ORDER BY id"

ELEMENT_INSERT = """
INSERT INTO ui_element (screen_id, role, accessible_name, test_id, locator_chain,
                        is_fragile, is_verified)
VALUES (:screen_id, :role, :accessible_name, :test_id, :locator_chain, :is_fragile,
        :is_verified)
"""
ELEMENT_FOR_SCREEN = "SELECT * FROM ui_element WHERE screen_id = :screen_id ORDER BY id"

DISCREPANCY_INSERT = """
INSERT INTO discrepancy (kind, subject, source_a, claim_a, source_b, claim_b,
                         detected_at, run_id)
VALUES (:kind, :subject, :source_a, :claim_a, :source_b, :claim_b, :detected_at, :run_id)
"""
DISCREPANCY_ALL = "SELECT * FROM discrepancy ORDER BY id"
DISCREPANCY_BY_KIND = "SELECT * FROM discrepancy WHERE kind = :kind ORDER BY id"

# --- requirements ------------------------------------------------------------
REQUIREMENT_UPSERT = """
INSERT INTO testable_requirement
    (id, feature_id, statement, classification, category, risk_score, risk_band,
     risk_factors, risk_is_partial, source_artefact_ids)
VALUES (:id, :feature_id, :statement, :classification, :category, :risk_score,
        :risk_band, :risk_factors, :risk_is_partial, :source_artefact_ids)
ON CONFLICT (id) DO UPDATE SET
    statement = excluded.statement,
    category = excluded.category,
    risk_score = excluded.risk_score,
    risk_band = excluded.risk_band,
    risk_factors = excluded.risk_factors,
    risk_is_partial = excluded.risk_is_partial
"""
REQUIREMENT_GET = "SELECT * FROM testable_requirement WHERE id = :id"
REQUIREMENT_PAGE = """
SELECT * FROM testable_requirement
WHERE (:feature_id IS NULL OR feature_id = :feature_id) AND id > :after
ORDER BY id LIMIT :limit
"""

# --- coverage ----------------------------------------------------------------
COVERAGE_UPSERT = """
INSERT INTO coverage_item
    (id, requirement_id, test_type, technique, planned_count, rationale,
     is_required, reduction_applied, model_version)
VALUES (:id, :requirement_id, :test_type, :technique, :planned_count, :rationale,
        :is_required, :reduction_applied, :model_version)
ON CONFLICT (id) DO UPDATE SET
    planned_count = excluded.planned_count,
    rationale = excluded.rationale,
    is_required = excluded.is_required,
    reduction_applied = excluded.reduction_applied,
    model_version = excluded.model_version
"""
COVERAGE_FOR_REQUIREMENT = "SELECT * FROM coverage_item WHERE requirement_id = :requirement_id ORDER BY id"
COVERAGE_MODEL_VERSION = """
SELECT ci.model_version FROM coverage_item ci
JOIN testable_requirement tr ON tr.id = ci.requirement_id
WHERE tr.feature_id = :feature_id
ORDER BY ci.model_version DESC LIMIT 1
"""
COVERAGE_CONTENT_FOR_FEATURE = """
SELECT ci.id, ci.test_type, ci.planned_count, ci.is_required
FROM coverage_item ci
JOIN testable_requirement tr ON tr.id = ci.requirement_id
WHERE tr.feature_id = :feature_id
ORDER BY ci.id
"""

# --- test cases --------------------------------------------------------------
CASE_INSERT = """
INSERT INTO test_case
    (id, feature_id, coverage_item_id, title, test_type, priority, preconditions,
     expected_result, automatability, automatability_reason,
     automatability_overridden_by, tags, normalised_hash, bucket_key,
     created_run_id, last_modified_run_id, created_at, last_modified_at, last_modified_by)
VALUES (:id, :feature_id, :coverage_item_id, :title, :test_type, :priority,
        :preconditions, :expected_result, :automatability, :automatability_reason,
        :automatability_overridden_by, :tags, :normalised_hash, :bucket_key,
        :run_id, :run_id, :now, :now, :actor)
ON CONFLICT (id) DO UPDATE SET
    title = excluded.title,
    expected_result = excluded.expected_result,
    automatability = excluded.automatability,
    automatability_reason = excluded.automatability_reason,
    tags = excluded.tags,
    normalised_hash = excluded.normalised_hash,
    bucket_key = excluded.bucket_key,
    last_modified_run_id = excluded.last_modified_run_id,
    last_modified_at = excluded.last_modified_at,
    last_modified_by = excluded.last_modified_by
"""
CASE_GET = "SELECT * FROM test_case WHERE id = :id"
CASE_PAGE = """
SELECT * FROM test_case
WHERE (:feature_id IS NULL OR feature_id = :feature_id)
  AND (:include_obsolete = 1 OR is_obsolete = 0)
  AND (:tag IS NULL OR tags LIKE :tag_pattern)
  AND id > :after
ORDER BY id LIMIT :limit
"""
CASE_BUCKET_CANDIDATES = """
SELECT id, normalised_hash FROM test_case
WHERE bucket_key = :bucket_key AND is_obsolete = 0
"""
CASE_IDENTIFIERS = "SELECT id FROM test_case"
CASE_MARK_OBSOLETE = """
UPDATE test_case
SET is_obsolete = 1,
    obsolete_reason = :reason,
    obsoleted_by_change_id = :change_event_id,
    last_modified_at = :now,
    last_modified_by = :actor
WHERE id = :id
"""
CASE_COUNT_ACTIVE = "SELECT COUNT(*) AS n FROM test_case WHERE is_obsolete = 0"
CASE_CLASSES = """
SELECT case_id, equivalence_class FROM test_data WHERE case_id IN (SELECT id FROM test_case WHERE bucket_key = :bucket_key AND is_obsolete = 0)
"""

STEP_INSERT = """
INSERT INTO test_step (case_id, ordinal, action, expected)
VALUES (:case_id, :ordinal, :action, :expected)
ON CONFLICT (case_id, ordinal) DO UPDATE SET
    action = excluded.action, expected = excluded.expected
"""
STEPS_FOR_CASE = "SELECT * FROM test_step WHERE case_id = :case_id ORDER BY ordinal"

DATA_INSERT = """
INSERT INTO test_data (case_id, step_ordinal, field_name, value, equivalence_class,
                       boundary_relation)
VALUES (:case_id, :step_ordinal, :field_name, :value, :equivalence_class,
        :boundary_relation)
"""
DATA_FOR_CASE = "SELECT * FROM test_data WHERE case_id = :case_id ORDER BY id"

INTEGRITY_CHECK = "INSERT INTO case_integrity_check (case_id) VALUES (:case_id)"
INTEGRITY_CLEAR = "DELETE FROM case_integrity_check WHERE case_id = :case_id"

# --- traceability ------------------------------------------------------------
TRACE_INSERT = """
INSERT INTO trace_link (source_kind, source_id, target_ref, link_type, evidence,
                        selection_basis, alternatives, resolved_jira_key)
VALUES (:source_kind, :source_id, :target_ref, :link_type, :evidence,
        :selection_basis, :alternatives, :resolved_jira_key)
"""
TRACE_FOR_SOURCE = "SELECT * FROM trace_link WHERE source_id = :source_id ORDER BY id"
TRACE_ALL = "SELECT * FROM trace_link ORDER BY id"

# --- automation --------------------------------------------------------------
AUTOMATION_UPSERT = """
INSERT INTO automated_test (id, case_id, spec_path, test_name, page_object_refs,
                            input_hash, output_hash, is_at_risk, at_risk_reason)
VALUES (:id, :case_id, :spec_path, :test_name, :page_object_refs, :input_hash,
        :output_hash, :is_at_risk, :at_risk_reason)
ON CONFLICT (id) DO UPDATE SET
    spec_path = excluded.spec_path,
    output_hash = excluded.output_hash,
    is_at_risk = excluded.is_at_risk,
    at_risk_reason = excluded.at_risk_reason
"""
AUTOMATION_FOR_CASE = "SELECT * FROM automated_test WHERE case_id = :case_id"
AUTOMATION_AT_RISK = "SELECT * FROM automated_test WHERE is_at_risk = 1 ORDER BY id"

# --- run state ---------------------------------------------------------------
RUN_INSERT = """
INSERT INTO run (correlation_id, kind, operator, started_at, business_rules)
VALUES (:correlation_id, :kind, :operator, :started_at, :business_rules)
"""
STATE_GET = "SELECT * FROM unit_state WHERE unit_ref = :unit_ref AND stage = :stage"
STATE_UPSERT = """
INSERT INTO unit_state (unit_ref, stage, state, lease_id, approved_by, approved_at,
                        approved_content_hash, failure_reason, metrics)
VALUES (:unit_ref, :stage, :state, :lease_id, :approved_by, :approved_at,
        :approved_content_hash, :failure_reason, :metrics)
ON CONFLICT (unit_ref, stage) DO UPDATE SET
    state = excluded.state,
    lease_id = excluded.lease_id,
    approved_by = excluded.approved_by,
    approved_at = excluded.approved_at,
    approved_content_hash = excluded.approved_content_hash,
    failure_reason = excluded.failure_reason,
    metrics = excluded.metrics
"""
STATE_ALL = """
SELECT * FROM unit_state
WHERE (:unit_ref IS NULL OR unit_ref = :unit_ref)
ORDER BY unit_ref, stage
"""

# --- change events -----------------------------------------------------------
CHANGE_INSERT = """
INSERT INTO change_event (run_id, source, ref_from, ref_to, changed_refs, jira_keys,
                          is_unmapped, impact_scale)
VALUES (:run_id, :source, :ref_from, :ref_to, :changed_refs, :jira_keys,
        :is_unmapped, :impact_scale)
"""
CHANGE_LATEST = """
SELECT * FROM change_event WHERE source = :source ORDER BY id DESC LIMIT 1
"""


# --- gaps and coverage reductions (U3) ---------------------------------------
GAP_INSERT = """
INSERT INTO gap (category, subject, source_ref, attempted, feature_slug, detail,
                 detected_at, run_id)
VALUES (:category, :subject, :source_ref, :attempted, :feature_slug, :detail,
        :detected_at, :run_id)
"""
GAP_OPEN = """
SELECT * FROM gap
WHERE closed_at IS NULL
  AND (:category IS NULL OR category = :category)
  AND (:feature_slug IS NULL OR feature_slug = :feature_slug)
ORDER BY id
"""
GAP_BY_CATEGORY = "SELECT category, COUNT(*) AS n FROM gap WHERE closed_at IS NULL GROUP BY category"
GAP_CLOSE = """
UPDATE gap SET closed_at = :closed_at, closed_by = :closed_by
WHERE id = :id AND closed_at IS NULL
"""
GAP_FIND = """
SELECT * FROM gap
WHERE category = :category AND subject = :subject AND closed_at IS NULL
LIMIT 1
"""

REDUCTION_INSERT = """
INSERT INTO coverage_reduction (feature_id, model_version, technique, reason,
                                full_yield, reduced_yield, decided_by, decided_at,
                                risk_band, was_override)
VALUES (:feature_id, :model_version, :technique, :reason, :full_yield,
        :reduced_yield, :decided_by, :decided_at, :risk_band, :was_override)
"""
REDUCTION_FOR_FEATURE = """
SELECT * FROM coverage_reduction WHERE feature_id = :feature_id
ORDER BY model_version DESC, id DESC
"""
REDUCTION_ALL = "SELECT * FROM coverage_reduction ORDER BY id"

COVERAGE_LATEST_VERSION = """
SELECT ci.model_version_int AS version, ci.content_hash AS content_hash
FROM coverage_item ci
JOIN testable_requirement tr ON tr.id = ci.requirement_id
WHERE tr.feature_id = :feature_id
ORDER BY ci.model_version_int DESC
LIMIT 1
"""
COVERAGE_FOR_FEATURE = """
SELECT ci.* FROM coverage_item ci
JOIN testable_requirement tr ON tr.id = ci.requirement_id
WHERE tr.feature_id = :feature_id
ORDER BY ci.id
"""
COVERAGE_SET_VERSION = """
UPDATE coverage_item SET model_version_int = :version, content_hash = :content_hash
WHERE id = :id
"""

# --- U4: emitted views --------------------------------------------------------
VIEW_UPSERT = """
INSERT INTO emitted_view (path, feature_slug, content_hash, emitted_at, case_count, kind)
VALUES (:path, :feature_slug, :content_hash, :emitted_at, :case_count, :kind)
ON CONFLICT (path) DO UPDATE SET
    content_hash = excluded.content_hash,
    emitted_at   = excluded.emitted_at,
    case_count   = excluded.case_count,
    kind         = excluded.kind
"""
VIEW_GET = "SELECT * FROM emitted_view WHERE path = :path"
VIEW_FOR_FEATURE = """
SELECT * FROM emitted_view WHERE feature_slug = :feature_slug ORDER BY path
"""

# --- U4: volume reporting -----------------------------------------------------
# Planned and generated in one pass. A LEFT JOIN rather than an inner one, because
# a coverage item that produced no case is exactly the row the report exists to
# show - BR-U4-7.3 forbids closing a shortfall by padding, which is only checkable
# if the shortfall appears.
VOLUME_BY_COVERAGE_ITEM = """
SELECT ci.id                AS coverage_item_id,
       ci.requirement_id    AS requirement_id,
       ci.test_type         AS test_type,
       ci.technique         AS technique,
       ci.planned_count     AS planned,
       ci.is_required       AS is_required,
       COUNT(tc.id)         AS generated
FROM coverage_item ci
JOIN testable_requirement tr ON tr.id = ci.requirement_id
LEFT JOIN test_case tc ON tc.coverage_item_id = ci.id AND tc.is_obsolete = 0
WHERE tr.feature_id = :feature_id
GROUP BY ci.id
ORDER BY ci.id
"""
VOLUME_BY_FEATURE = """
SELECT f.slug                AS feature_slug,
       COUNT(DISTINCT tc.id) AS cases,
       SUM(CASE WHEN tc.automatability = 'automatable' THEN 1 ELSE 0 END) AS automatable,
       SUM(CASE WHEN tc.automatability = 'manual-only' THEN 1 ELSE 0 END) AS manual_only,
       SUM(CASE WHEN tc.automatability = 'needs-review' THEN 1 ELSE 0 END) AS needs_review
FROM feature f
LEFT JOIN test_case tc ON tc.feature_id = f.id AND tc.is_obsolete = 0
GROUP BY f.id
ORDER BY f.slug
"""

# --- U4: streamed matrix ------------------------------------------------------
# Ordered by id so the stream is deterministic across runs; the matrix is written
# to a file and a file that reorders itself between identical runs reads as churn.
TRACE_STREAM = """
SELECT source_kind, source_id, target_ref, link_type, resolved_jira_key
FROM trace_link ORDER BY id
"""
REQUIREMENT_IDS_STREAM = "SELECT id FROM testable_requirement ORDER BY id"
CASES_FOR_FEATURE_SLUG = """
SELECT tc.* FROM test_case tc
JOIN feature f ON f.id = tc.feature_id
WHERE f.slug = :feature_slug AND tc.is_obsolete = 0
ORDER BY tc.id
"""

# --- U5: automation -----------------------------------------------------------
ELEMENTS_FOR_FEATURE = """
SELECT ue.*, s.name AS screen_name, s.state AS screen_state, s.route AS screen_route
FROM ui_element ue
JOIN screen s ON s.id = ue.screen_id
WHERE s.feature_id = :feature_id
ORDER BY s.name, ue.id
"""
AUTOMATION_FOR_FEATURE = """
SELECT at.* FROM automated_test at
JOIN test_case tc ON tc.id = at.case_id
JOIN feature f ON f.id = tc.feature_id
WHERE f.slug = :feature_slug
ORDER BY at.id
"""
AUTOMATION_COUNTS = """
SELECT COUNT(*) AS total,
       SUM(CASE WHEN is_at_risk = 1 THEN 1 ELSE 0 END) AS at_risk
FROM automated_test
"""
AUTOMATION_DELETE_FOR_FEATURE = """
DELETE FROM automated_test WHERE case_id IN (
    SELECT tc.id FROM test_case tc
    JOIN feature f ON f.id = tc.feature_id
    WHERE f.slug = :feature_slug
)
"""

AUTOMATION_ALL = "SELECT * FROM automated_test ORDER BY id"

# --- U8: reporting ------------------------------------------------------------
# Aggregated in SQL, never by counting in Python: the Python form reads the whole
# corpus to produce 150 rows (U8-NFR-SCL-03). The LEFT JOIN is load-bearing - a
# coverage item that produced nothing is the row the report exists to show - and
# `is_obsolete = 0` is where retirement takes effect with no separate step.
REPORT_COVERAGE_BY_FEATURE = """
SELECT f.slug                 AS feature,
       ci.test_type           AS test_type,
       COUNT(DISTINCT tr.id)  AS requirements,
       COUNT(DISTINCT ci.id)  AS coverage_items,
       SUM(ci.planned_count)  AS planned,
       COUNT(DISTINCT tc.id)  AS generated
FROM feature f
JOIN testable_requirement tr ON tr.feature_id = f.id
JOIN coverage_item ci        ON ci.requirement_id = tr.id
LEFT JOIN test_case tc       ON tc.coverage_item_id = ci.id AND tc.is_obsolete = 0
GROUP BY f.id, ci.test_type
ORDER BY f.slug, ci.test_type
"""
REPORT_COVERAGE_BY_TEST_TYPE = """
SELECT ci.test_type          AS test_type,
       SUM(ci.planned_count) AS planned,
       COUNT(DISTINCT tc.id) AS generated
FROM coverage_item ci
LEFT JOIN test_case tc ON tc.coverage_item_id = ci.id AND tc.is_obsolete = 0
GROUP BY ci.test_type
ORDER BY ci.test_type
"""
REPORT_GAPS = """
SELECT category, subject, source_ref, feature_slug, detail, detected_at
FROM gap WHERE closed_at IS NULL
ORDER BY category, subject
"""
REPORT_AUTOMATION = """
SELECT at.id            AS test_id,
       at.case_id       AS case_id,
       at.test_name     AS test_name,
       at.is_at_risk    AS is_at_risk,
       at.at_risk_reason AS at_risk_reason,
       tc.title         AS case_title,
       tc.automatability AS automatability
FROM automated_test at
JOIN test_case tc ON tc.id = at.case_id
ORDER BY at.id
"""
REPORT_DEFERRED = """
SELECT tc.id                    AS case_id,
       tc.title                 AS title,
       tc.automatability        AS classification,
       tc.automatability_reason AS reason
FROM test_case tc
LEFT JOIN automated_test at ON at.case_id = tc.id
WHERE at.id IS NULL AND tc.is_obsolete = 0
ORDER BY tc.id
"""
REPORT_RETIRED = """
SELECT id, title, obsolete_reason, obsoleted_by_change_id, last_modified_run_id
FROM test_case WHERE is_obsolete = 1 ORDER BY id
"""

# --- U8: the delta baseline ----------------------------------------------------
RUN_LAST_COMPLETED = """
SELECT * FROM run WHERE ended_at IS NOT NULL ORDER BY ended_at DESC, id DESC LIMIT 1
"""
RUN_RECORD_BASELINE = """
UPDATE run SET head_commits = :head_commits, jira_watermark = :jira_watermark
WHERE id = :id
"""
RUN_COMPLETE = "UPDATE run SET ended_at = :ended_at WHERE id = :id"
TRACE_FOR_TARGET = "SELECT * FROM trace_link WHERE target_ref = :target_ref ORDER BY id"
