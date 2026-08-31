"""Migration 001 - the initial schema.

The requirements.md 10.3 integrity rules live here as constraints and triggers, not
only in D7. The domain validator produces an error the agent can act on; the
constraint makes the rule unbreakable even if a future code path bypasses the
validator. Neither alone is sufficient: a constraint gives an unhelpful error, and
a validator can be forgotten.
"""

UP = """
-- ---------------------------------------------------------------------------
-- Ingestion
-- ---------------------------------------------------------------------------
CREATE TABLE resource (
    id                INTEGER PRIMARY KEY,
    raw_ref           TEXT    NOT NULL,
    type              TEXT    NOT NULL,
    inferred_from     TEXT    NOT NULL DEFAULT '',
    status            TEXT    NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','ingested','failed','unclassified')),
    failure_reason    TEXT,
    first_seen_at     TEXT    NOT NULL,
    last_ingested_at  TEXT,
    UNIQUE (raw_ref)
);

CREATE TABLE artefact (
    id                INTEGER PRIMARY KEY,
    resource_id       INTEGER NOT NULL REFERENCES resource(id),
    kind              TEXT    NOT NULL,
    source_identifier TEXT    NOT NULL,
    content           TEXT    NOT NULL,
    content_hash      TEXT    NOT NULL CHECK (length(content_hash) = 64),
    metadata          TEXT    NOT NULL DEFAULT '{}',
    detail_level      TEXT    NOT NULL DEFAULT 'full'
                      CHECK (detail_level IN ('full','low')),
    ingested_at       TEXT    NOT NULL,
    run_id            INTEGER,
    -- FR-ING-10: re-ingesting unchanged content creates no duplicate.
    UNIQUE (resource_id, source_identifier, content_hash)
);

-- ---------------------------------------------------------------------------
-- Application model
-- ---------------------------------------------------------------------------
CREATE TABLE feature (
    id          INTEGER PRIMARY KEY,
    slug        TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL CHECK (length(trim(name)) > 0),
    parent_id   INTEGER REFERENCES feature(id),
    description TEXT    NOT NULL DEFAULT '',
    risk_band   TEXT    CHECK (risk_band IN ('low','medium','high','critical'))
);

CREATE TABLE journey (
    id    INTEGER PRIMARY KEY,
    name  TEXT    NOT NULL,
    steps TEXT    NOT NULL DEFAULT '[]'
);

CREATE TABLE business_rule (
    id             INTEGER PRIMARY KEY,
    feature_id     INTEGER NOT NULL REFERENCES feature(id),
    rule_kind      TEXT    NOT NULL
                   CHECK (rule_kind IN ('validation','state-transition','calculation','permission')),
    condition      TEXT    NOT NULL,
    effect         TEXT    NOT NULL,
    is_documented  INTEGER NOT NULL DEFAULT 1,
    -- FR-ANA-08: when Jira and code disagree, both rules persist and point at
    -- each other. The system records the conflict; it does not resolve it.
    contradicts_id INTEGER REFERENCES business_rule(id)
);

CREATE TABLE api_endpoint (
    id               INTEGER PRIMARY KEY,
    feature_id       INTEGER REFERENCES feature(id),
    method           TEXT    NOT NULL,
    route            TEXT    NOT NULL,
    file_path        TEXT    NOT NULL,
    line             INTEGER NOT NULL,
    symbol           TEXT    NOT NULL DEFAULT '',
    request_shape    TEXT,
    response_shapes  TEXT,
    status_codes     TEXT    NOT NULL DEFAULT '[]',
    -- 'unknown' is a distinct state from 'none': defaulting an undetermined auth
    -- requirement to public would hide a security-relevant gap.
    auth_requirement TEXT    NOT NULL DEFAULT 'unknown'
                     CHECK (auth_requirement IN ('none','required','unknown')),
    shape_source     TEXT    NOT NULL DEFAULT 'inferred'
                     CHECK (shape_source IN ('specified','inferred'))
);

CREATE TABLE screen (
    id             INTEGER PRIMARY KEY,
    feature_id     INTEGER REFERENCES feature(id),
    name           TEXT    NOT NULL,
    state          TEXT    NOT NULL DEFAULT 'default',
    route          TEXT,
    source         TEXT    NOT NULL DEFAULT 'figma',
    discrepancy_id INTEGER
);

CREATE TABLE ui_element (
    id              INTEGER PRIMARY KEY,
    screen_id       INTEGER NOT NULL REFERENCES screen(id),
    role            TEXT,
    accessible_name TEXT,
    test_id         TEXT,
    locator_chain   TEXT    NOT NULL DEFAULT '[]',
    is_fragile      INTEGER NOT NULL DEFAULT 0,
    -- is_verified separates a locator that works from one that ought to.
    is_verified     INTEGER NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- Requirements and coverage
-- ---------------------------------------------------------------------------
CREATE TABLE testable_requirement (
    id                  TEXT    PRIMARY KEY CHECK (id GLOB 'TR-*'),
    feature_id          INTEGER NOT NULL REFERENCES feature(id),
    statement           TEXT    NOT NULL CHECK (length(trim(statement)) > 0),
    classification      TEXT    NOT NULL DEFAULT 'functional',
    category            TEXT    NOT NULL DEFAULT 'business-rule',
    risk_score          INTEGER CHECK (risk_score IS NULL OR (risk_score BETWEEN 0 AND 100)),
    risk_band           TEXT    CHECK (risk_band IN ('low','medium','high','critical')),
    risk_factors        TEXT    NOT NULL DEFAULT '{}',
    risk_is_partial     INTEGER NOT NULL DEFAULT 0,
    source_artefact_ids TEXT    NOT NULL DEFAULT '[]'
);

CREATE TABLE coverage_item (
    id                TEXT    PRIMARY KEY CHECK (id GLOB 'CI-*'),
    requirement_id    TEXT    NOT NULL REFERENCES testable_requirement(id),
    test_type         TEXT    NOT NULL,
    technique         TEXT    NOT NULL DEFAULT 'direct',
    planned_count     INTEGER NOT NULL DEFAULT 1 CHECK (planned_count >= 0),
    rationale         TEXT    NOT NULL DEFAULT '',
    -- BR-2.6: a not-required row is kept, with zero planned cases. An absent row
    -- and a deliberate exclusion look identical unless the exclusion is recorded.
    is_required       INTEGER NOT NULL DEFAULT 1,
    reduction_applied TEXT,
    model_version     TEXT    NOT NULL DEFAULT '1',
    CHECK (is_required = 1 OR planned_count = 0)
);

-- ---------------------------------------------------------------------------
-- Test corpus
-- ---------------------------------------------------------------------------
CREATE TABLE test_case (
    id                         TEXT    PRIMARY KEY CHECK (id GLOB 'TC-*'),
    feature_id                 INTEGER NOT NULL REFERENCES feature(id),
    coverage_item_id           TEXT    NOT NULL REFERENCES coverage_item(id),
    title                      TEXT    NOT NULL CHECK (length(trim(title)) > 0),
    test_type                  TEXT    NOT NULL,
    priority                   TEXT    NOT NULL DEFAULT 'medium',
    preconditions              TEXT    NOT NULL DEFAULT '',
    expected_result            TEXT    NOT NULL CHECK (length(trim(expected_result)) > 0),
    automatability             TEXT    NOT NULL DEFAULT 'needs-review'
                               CHECK (automatability IN ('automatable','manual-only','needs-review')),
    automatability_reason      TEXT    NOT NULL DEFAULT '',
    automatability_overridden_by TEXT,
    tags                       TEXT    NOT NULL DEFAULT '[]',
    normalised_hash            TEXT,
    bucket_key                 TEXT,
    -- Deletion is soft. No query module contains a DELETE against a business entity.
    is_obsolete                INTEGER NOT NULL DEFAULT 0,
    obsolete_reason            TEXT,
    obsoleted_by_change_id     INTEGER,
    created_run_id             INTEGER,
    last_modified_run_id       INTEGER,
    created_at                 TEXT    NOT NULL,
    last_modified_at           TEXT    NOT NULL,
    last_modified_by           TEXT    NOT NULL DEFAULT 'toolchain',
    CHECK (is_obsolete = 0 OR (obsolete_reason IS NOT NULL AND length(trim(obsolete_reason)) > 0))
);

CREATE TABLE test_step (
    id       INTEGER PRIMARY KEY,
    case_id  TEXT    NOT NULL REFERENCES test_case(id) ON DELETE CASCADE,
    ordinal  INTEGER NOT NULL CHECK (ordinal >= 1),
    action   TEXT    NOT NULL CHECK (length(trim(action)) > 0),
    -- A step without an expected result is not a step.
    expected TEXT    NOT NULL CHECK (length(trim(expected)) > 0),
    UNIQUE (case_id, ordinal)
);

CREATE TABLE test_data (
    id                 INTEGER PRIMARY KEY,
    case_id            TEXT    NOT NULL REFERENCES test_case(id) ON DELETE CASCADE,
    step_ordinal       INTEGER,
    field_name         TEXT    NOT NULL,
    value              TEXT    NOT NULL,
    -- Mandatory: it is what makes two superficially similar cases materially
    -- different in de-duplication, and what lets a reviewer see why a value was chosen.
    equivalence_class  TEXT    NOT NULL CHECK (length(trim(equivalence_class)) > 0),
    boundary_relation  TEXT    CHECK (boundary_relation IS NULL
                                 OR boundary_relation IN ('at','just-inside','just-outside'))
);

CREATE TABLE trace_link (
    id                INTEGER PRIMARY KEY,
    source_kind       TEXT    NOT NULL,
    source_id         TEXT    NOT NULL,
    target_ref        TEXT    NOT NULL CHECK (length(trim(target_ref)) > 0),
    link_type         TEXT    NOT NULL
                      CHECK (link_type IN ('direct-story','derived-from-commit',
                                           'confluence','code-symbol','screenshot')),
    evidence          TEXT    NOT NULL DEFAULT '',
    selection_basis   TEXT,
    alternatives      TEXT    NOT NULL DEFAULT '[]',
    resolved_jira_key TEXT,
    -- A link type that claims to resolve a Jira key must carry one, and a
    -- derived link must record why that key was chosen over the alternatives.
    CHECK (link_type NOT IN ('direct-story','derived-from-commit')
           OR resolved_jira_key IS NOT NULL),
    CHECK (link_type <> 'derived-from-commit'
           OR (selection_basis IS NOT NULL AND length(trim(selection_basis)) > 0))
);

CREATE TABLE automated_test (
    id               TEXT    PRIMARY KEY CHECK (id GLOB 'AT-*'),
    case_id          TEXT    NOT NULL UNIQUE REFERENCES test_case(id),
    spec_path        TEXT    NOT NULL,
    test_name        TEXT    NOT NULL,
    page_object_refs TEXT    NOT NULL DEFAULT '[]',
    input_hash       TEXT,
    output_hash      TEXT,
    is_at_risk       INTEGER NOT NULL DEFAULT 0,
    at_risk_reason   TEXT,
    CHECK (is_at_risk = 0 OR at_risk_reason IS NOT NULL)
);

-- ---------------------------------------------------------------------------
-- Run state
-- ---------------------------------------------------------------------------
CREATE TABLE run (
    id             INTEGER PRIMARY KEY,
    correlation_id TEXT    NOT NULL,
    kind           TEXT    NOT NULL DEFAULT 'baseline' CHECK (kind IN ('baseline','delta')),
    operator       TEXT    NOT NULL DEFAULT '',
    started_at     TEXT    NOT NULL,
    ended_at       TEXT,
    -- The tunables that change the corpus, recorded alongside the results they produced.
    business_rules TEXT    NOT NULL DEFAULT '{}'
);

CREATE TABLE unit_state (
    id                    INTEGER PRIMARY KEY,
    unit_ref              TEXT    NOT NULL,
    stage                 TEXT    NOT NULL,
    state                 TEXT    NOT NULL DEFAULT 'not-started'
                          CHECK (state IN ('not-started','in-progress','completed',
                                           'failed','needs-review')),
    lease_id              TEXT,
    approved_by           TEXT,
    approved_at           TEXT,
    -- Approval binds to content: modify what was approved and the hash no longer
    -- matches, so the approval no longer applies.
    approved_content_hash TEXT,
    failure_reason        TEXT,
    metrics               TEXT    NOT NULL DEFAULT '{}',
    UNIQUE (unit_ref, stage),
    CHECK (state <> 'in-progress' OR lease_id IS NOT NULL),
    CHECK (state <> 'failed' OR failure_reason IS NOT NULL)
);

CREATE TABLE change_event (
    id           INTEGER PRIMARY KEY,
    run_id       INTEGER NOT NULL REFERENCES run(id),
    source       TEXT    NOT NULL CHECK (source IN ('bitbucket','jira')),
    ref_from     TEXT    NOT NULL,
    ref_to       TEXT    NOT NULL,
    changed_refs TEXT    NOT NULL DEFAULT '[]',
    jira_keys    TEXT    NOT NULL DEFAULT '[]',
    is_unmapped  INTEGER NOT NULL DEFAULT 0,
    impact_scale REAL    NOT NULL DEFAULT 0.0
                 CHECK (impact_scale BETWEEN 0.0 AND 1.0)
);

-- ---------------------------------------------------------------------------
-- Triggers: the two rules that matter most, enforced at the storage layer.
--
-- A CHECK constraint cannot span tables, so "a case must have at least one step"
-- and "a case must carry a Jira key" are enforced by deferred triggers on a
-- sentinel column update, invoked by the repository at the end of each batch.
-- ---------------------------------------------------------------------------
CREATE TABLE case_integrity_check (
    case_id TEXT PRIMARY KEY REFERENCES test_case(id) ON DELETE CASCADE
);

CREATE TRIGGER trg_case_requires_steps
BEFORE INSERT ON case_integrity_check
FOR EACH ROW
WHEN (SELECT COUNT(*) FROM test_step WHERE case_id = NEW.case_id) = 0
BEGIN
    SELECT RAISE(ABORT, 'REJECTED_NO_STEPS: test case has no steps');
END;

CREATE TRIGGER trg_case_requires_jira_key
BEFORE INSERT ON case_integrity_check
FOR EACH ROW
WHEN (SELECT COUNT(*) FROM trace_link
      WHERE source_kind = 'test_case'
        AND source_id = NEW.case_id
        AND resolved_jira_key IS NOT NULL) = 0
BEGIN
    SELECT RAISE(ABORT, 'REJECTED_NO_JIRA_KEY: test case carries no Jira key link');
END;

-- Identifiers are allocated by the toolchain and are immutable.
CREATE TRIGGER trg_case_id_is_immutable
BEFORE UPDATE OF id ON test_case
FOR EACH ROW
WHEN OLD.id <> NEW.id
BEGIN
    SELECT RAISE(ABORT, 'test case identifiers are immutable');
END;

-- ---------------------------------------------------------------------------
-- Indexes (nfr-design-patterns.md P-PRF-01)
-- ---------------------------------------------------------------------------
-- The single most important index in the schema. Without bucketed candidate
-- selection, de-duplication degrades to a full scan and the 200 ms budget in
-- NFR-PRF-01 becomes unreachable at volume.
--
-- Composite on (bucket_key, is_obsolete), in that order, because the candidate
-- query filters on both. A bare index on bucket_key alone loses: the planner
-- prefers idx_case_obsolete, which is almost entirely unselective - nearly every
-- row has is_obsolete = 0 - and the lookup degrades to scanning the active corpus.
-- Leading with bucket_key makes the selective column the one the planner uses,
-- and the index still serves bucket-only lookups.
CREATE INDEX idx_case_bucket        ON test_case (bucket_key, is_obsolete);
CREATE INDEX idx_case_feature_type  ON test_case (feature_id, test_type);
CREATE INDEX idx_case_obsolete      ON test_case (is_obsolete);
CREATE INDEX idx_trace_source       ON trace_link (source_kind, source_id);
CREATE INDEX idx_trace_target       ON trace_link (target_ref);
CREATE INDEX idx_trace_jira         ON trace_link (resolved_jira_key);
CREATE INDEX idx_artefact_hash      ON artefact (content_hash);
CREATE INDEX idx_unit_state         ON unit_state (unit_ref, stage);
CREATE INDEX idx_step_case_ord      ON test_step (case_id, ordinal);
"""

DOWN = """
DROP INDEX IF EXISTS idx_step_case_ord;
DROP INDEX IF EXISTS idx_unit_state;
DROP INDEX IF EXISTS idx_artefact_hash;
DROP INDEX IF EXISTS idx_trace_jira;
DROP INDEX IF EXISTS idx_trace_target;
DROP INDEX IF EXISTS idx_trace_source;
DROP INDEX IF EXISTS idx_case_obsolete;
DROP INDEX IF EXISTS idx_case_feature_type;
DROP INDEX IF EXISTS idx_case_bucket;
DROP TRIGGER IF EXISTS trg_case_id_is_immutable;
DROP TRIGGER IF EXISTS trg_case_requires_jira_key;
DROP TRIGGER IF EXISTS trg_case_requires_steps;
DROP TABLE IF EXISTS case_integrity_check;
DROP TABLE IF EXISTS change_event;
DROP TABLE IF EXISTS unit_state;
DROP TABLE IF EXISTS run;
DROP TABLE IF EXISTS automated_test;
DROP TABLE IF EXISTS trace_link;
DROP TABLE IF EXISTS test_data;
DROP TABLE IF EXISTS test_step;
DROP TABLE IF EXISTS test_case;
DROP TABLE IF EXISTS coverage_item;
DROP TABLE IF EXISTS testable_requirement;
DROP TABLE IF EXISTS ui_element;
DROP TABLE IF EXISTS screen;
DROP TABLE IF EXISTS api_endpoint;
DROP TABLE IF EXISTS business_rule;
DROP TABLE IF EXISTS journey;
DROP TABLE IF EXISTS feature;
DROP TABLE IF EXISTS artefact;
DROP TABLE IF EXISTS resource;
"""
