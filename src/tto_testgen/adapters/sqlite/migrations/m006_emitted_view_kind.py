"""Migration 006 - emitted_view records generated TypeScript as well as views.

U4 built `emitted_view` for Markdown and YAML. U5 writes TypeScript and needs the
same protection: a file was written, a person may have edited it, and the hash at
last emission is the only thing that distinguishes their edit from a corpus change.

A second table was the alternative and was declined. The problem is identical, and
two tables would mean two implementations of one rule - the second drifting until
someone discovers that hand-edits are protected in the views but not in the specs,
which is the worst possible way to find out.

`kind` defaults to 'view' so every row U4 already wrote is correctly labelled
without a backfill.
"""

UP = """
ALTER TABLE emitted_view ADD COLUMN kind TEXT NOT NULL DEFAULT 'view';
CREATE INDEX idx_emitted_view_kind ON emitted_view (kind);
"""

DOWN = """
DROP INDEX IF EXISTS idx_emitted_view_kind;

-- SQLite before 3.35 cannot DROP COLUMN, so the reverse rebuilds. Written
-- explicitly rather than relying on the operator's SQLite version: a rollback that
-- fails on an older build is not a rollback.
CREATE TABLE emitted_view_rebuild (
    id           INTEGER PRIMARY KEY,
    path         TEXT    NOT NULL UNIQUE,
    feature_slug TEXT    NOT NULL CHECK (length(trim(feature_slug)) > 0),
    content_hash TEXT    NOT NULL CHECK (length(content_hash) = 64),
    emitted_at   TEXT    NOT NULL,
    case_count   INTEGER NOT NULL DEFAULT 0 CHECK (case_count >= 0)
);
INSERT INTO emitted_view_rebuild
    (id, path, feature_slug, content_hash, emitted_at, case_count)
SELECT id, path, feature_slug, content_hash, emitted_at, case_count
FROM emitted_view
WHERE kind = 'view';
DROP TABLE emitted_view;
ALTER TABLE emitted_view_rebuild RENAME TO emitted_view;
CREATE INDEX idx_emitted_view_feature ON emitted_view (feature_slug);
"""
