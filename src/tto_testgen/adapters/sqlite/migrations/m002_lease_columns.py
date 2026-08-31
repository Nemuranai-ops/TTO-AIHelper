"""Migration 002 - lease heartbeat columns.

BR-U7-2 needs to tell a working session from an abandoned one. That requires state
migration 001 does not carry.

The reverse rebuilds the table rather than using DROP COLUMN. SQLite gained DROP
COLUMN in 3.35, and the reverse must work on whatever version the operator's machine
has - a rollback that fails on an older SQLite is not a rollback.
"""

UP = """
ALTER TABLE unit_state ADD COLUMN leased_at TEXT;
ALTER TABLE unit_state ADD COLUMN last_heartbeat TEXT;
ALTER TABLE unit_state ADD COLUMN lease_holder TEXT;
"""

DOWN = """
CREATE TABLE unit_state_rebuild (
    id                    INTEGER PRIMARY KEY,
    unit_ref              TEXT    NOT NULL,
    stage                 TEXT    NOT NULL,
    state                 TEXT    NOT NULL DEFAULT 'not-started'
                          CHECK (state IN ('not-started','in-progress','completed',
                                           'failed','needs-review')),
    lease_id              TEXT,
    approved_by           TEXT,
    approved_at           TEXT,
    approved_content_hash TEXT,
    failure_reason        TEXT,
    metrics               TEXT    NOT NULL DEFAULT '{}',
    UNIQUE (unit_ref, stage),
    CHECK (state <> 'in-progress' OR lease_id IS NOT NULL),
    CHECK (state <> 'failed' OR failure_reason IS NOT NULL)
);
INSERT INTO unit_state_rebuild
    (id, unit_ref, stage, state, lease_id, approved_by, approved_at,
     approved_content_hash, failure_reason, metrics)
SELECT id, unit_ref, stage, state, lease_id, approved_by, approved_at,
       approved_content_hash, failure_reason, metrics
FROM unit_state;
DROP INDEX IF EXISTS idx_unit_state;
DROP TABLE unit_state;
ALTER TABLE unit_state_rebuild RENAME TO unit_state;
CREATE INDEX idx_unit_state ON unit_state (unit_ref, stage);
"""
