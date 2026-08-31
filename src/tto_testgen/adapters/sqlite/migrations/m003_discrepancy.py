"""Migration 003 - the discrepancy table.

U1's schema already references this table from `screen.discrepancy_id` and
`business_rule.contradicts_id`. Those were forward references to something that did
not exist yet; FR-ANA-08 is what needs it.

Both claims are stored with both sources and neither is marked correct. A record
holding one claim plus a note about "the other source" is readable in one direction,
and the reader frequently arrives from the side that was not chosen as primary.
"""

UP = """
CREATE TABLE discrepancy (
    id          INTEGER PRIMARY KEY,
    kind        TEXT    NOT NULL,
    subject     TEXT    NOT NULL,
    source_a    TEXT    NOT NULL,
    claim_a     TEXT    NOT NULL,
    source_b    TEXT    NOT NULL,
    claim_b     TEXT    NOT NULL,
    detected_at TEXT    NOT NULL,
    run_id      INTEGER,
    resolved_by TEXT,
    resolution  TEXT,
    -- A resolution is a human act. Recording who made it is what separates a
    -- decision from a value that simply appeared.
    CHECK (resolved_by IS NULL OR resolution IS NOT NULL)
);
CREATE INDEX idx_discrepancy_kind ON discrepancy (kind);
CREATE INDEX idx_discrepancy_subject ON discrepancy (subject);
"""

DOWN = """
DROP INDEX IF EXISTS idx_discrepancy_subject;
DROP INDEX IF EXISTS idx_discrepancy_kind;
DROP TABLE IF EXISTS discrepancy;
"""
