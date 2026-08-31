"""Migration 004 - gaps, coverage reductions, and coverage versioning columns.

Three things U3 needs that no earlier unit created:

  - `gap`: FR-TRC-04, FR-COV-05 and FR-TRQ-05 all produce gaps, and until now they
    had nowhere to go. Six categories are declared, not the four U3 uses: U4 writes
    `rejected-duplicate` and `manual-only`, and the CHECK would otherwise reject them.
  - `coverage_reduction`: both yields stored, so the gap report can say how much
    coverage was given up rather than merely that some was.
  - Two columns on `coverage_item`, added rather than altering U1's `model_version`,
    which is TEXT and written by code that is complete and approved.
"""

UP = """
CREATE TABLE gap (
    id           INTEGER PRIMARY KEY,
    category     TEXT    NOT NULL
                 CHECK (category IN ('untraceable-behaviour','uncovered-requirement',
                                     'boundaries-undetermined','reduced-depth',
                                     'rejected-duplicate','manual-only')),
    subject      TEXT    NOT NULL CHECK (length(trim(subject)) > 0),
    source_ref   TEXT    NOT NULL DEFAULT '',
    attempted    TEXT    NOT NULL DEFAULT '[]',
    feature_slug TEXT,
    detail       TEXT    NOT NULL DEFAULT '',
    detected_at  TEXT    NOT NULL,
    run_id       INTEGER,
    closed_at    TEXT,
    closed_by    TEXT,
    -- A gap that stops appearing might have been resolved or might have stopped
    -- being detected. Recording who closed it separates the two, which the delta
    -- pipeline needs.
    CHECK (closed_at IS NULL OR closed_by IS NOT NULL)
);
CREATE INDEX idx_gap_category ON gap (category);
CREATE INDEX idx_gap_open ON gap (closed_at);
CREATE INDEX idx_gap_feature ON gap (feature_slug);

CREATE TABLE coverage_reduction (
    id            INTEGER PRIMARY KEY,
    feature_id    INTEGER NOT NULL REFERENCES feature(id),
    model_version INTEGER NOT NULL,
    technique     TEXT    NOT NULL,
    reason        TEXT    NOT NULL CHECK (length(trim(reason)) > 0),
    full_yield    INTEGER NOT NULL,
    reduced_yield INTEGER NOT NULL,
    decided_by    TEXT    NOT NULL,
    decided_at    TEXT    NOT NULL,
    risk_band     TEXT,
    was_override  INTEGER NOT NULL DEFAULT 0,
    -- Reduction never increases coverage. A record claiming otherwise is a bug in
    -- D2, caught at the storage layer rather than discovered in a report.
    CHECK (reduced_yield <= full_yield),
    -- A high-risk reduction is permitted, but it must be deliberate.
    CHECK (risk_band IS NULL OR risk_band NOT IN ('high','critical') OR was_override = 1)
);
CREATE INDEX idx_reduction_feature ON coverage_reduction (feature_id);

ALTER TABLE coverage_item ADD COLUMN model_version_int INTEGER NOT NULL DEFAULT 1;
ALTER TABLE coverage_item ADD COLUMN content_hash TEXT;
CREATE INDEX idx_coverage_requirement ON coverage_item (requirement_id);
CREATE INDEX idx_coverage_required ON coverage_item (is_required);
"""

DOWN = """
DROP INDEX IF EXISTS idx_coverage_required;
DROP INDEX IF EXISTS idx_coverage_requirement;
DROP INDEX IF EXISTS idx_reduction_feature;
DROP TABLE IF EXISTS coverage_reduction;
DROP INDEX IF EXISTS idx_gap_feature;
DROP INDEX IF EXISTS idx_gap_open;
DROP INDEX IF EXISTS idx_gap_category;
DROP TABLE IF EXISTS gap;

-- SQLite before 3.35 cannot DROP COLUMN, so the reverse rebuilds the table. Written
-- explicitly rather than relying on the operator's SQLite version: a rollback that
-- fails on an older build is not a rollback.
CREATE TABLE coverage_item_rebuild (
    id                TEXT    PRIMARY KEY CHECK (id GLOB 'CI-*'),
    requirement_id    TEXT    NOT NULL REFERENCES testable_requirement(id),
    test_type         TEXT    NOT NULL,
    technique         TEXT    NOT NULL DEFAULT 'direct',
    planned_count     INTEGER NOT NULL DEFAULT 1 CHECK (planned_count >= 0),
    rationale         TEXT    NOT NULL DEFAULT '',
    is_required       INTEGER NOT NULL DEFAULT 1,
    reduction_applied TEXT,
    model_version     TEXT    NOT NULL DEFAULT '1',
    CHECK (is_required = 1 OR planned_count = 0)
);
INSERT INTO coverage_item_rebuild
    (id, requirement_id, test_type, technique, planned_count, rationale,
     is_required, reduction_applied, model_version)
SELECT id, requirement_id, test_type, technique, planned_count, rationale,
       is_required, reduction_applied, model_version
FROM coverage_item;
DROP TABLE coverage_item;
ALTER TABLE coverage_item_rebuild RENAME TO coverage_item;
"""
