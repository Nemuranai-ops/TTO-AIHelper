"""Migration 005 - the record of what was emitted.

Hand-edit detection needs a third point of comparison. Rendering the view and
diffing it against the file on disk tells you the two differ; it cannot tell you
whether the operator edited the file or the corpus moved underneath it. The hash
recorded at the last emission is what separates those two, and BR-U4-5.2 turns on
the distinction: a corpus change is written, an operator's edit is preserved.

`path` is UNIQUE because a view has one location, and a second row for the same path
would mean two hashes claiming to describe one file - with no rule for which wins.
"""

UP = """
CREATE TABLE emitted_view (
    id           INTEGER PRIMARY KEY,
    path         TEXT    NOT NULL UNIQUE,
    feature_slug TEXT    NOT NULL CHECK (length(trim(feature_slug)) > 0),
    content_hash TEXT    NOT NULL CHECK (length(content_hash) = 64),
    emitted_at   TEXT    NOT NULL,
    case_count   INTEGER NOT NULL DEFAULT 0 CHECK (case_count >= 0)
);
CREATE INDEX idx_emitted_view_feature ON emitted_view (feature_slug);
"""

DOWN = """
DROP INDEX IF EXISTS idx_emitted_view_feature;
DROP TABLE IF EXISTS emitted_view;
"""
