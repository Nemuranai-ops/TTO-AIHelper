"""Migration 007 - the delta baseline, recorded on the run that established it.

The baseline is what the system saw when a run completed, so it is a property of
that run. `run` already carries `ended_at`, which makes "the last completed run" one
query with no separate record to fall out of step with it.

A dedicated `delta_baseline` table was the alternative and would introduce a second
answer to "when did we last look at this" - the two disagreeing after a run that
failed partway, where one record was updated and the other was not.

`head_commits` is a JSON object keyed by repository slug: a delta run compares many
repositories, and one column per repository would need a migration per repository.
"""

UP = """
ALTER TABLE run ADD COLUMN head_commits TEXT NOT NULL DEFAULT '{}';
ALTER TABLE run ADD COLUMN jira_watermark TEXT;
CREATE INDEX idx_run_completed ON run (ended_at);
"""

DOWN = """
DROP INDEX IF EXISTS idx_run_completed;

-- SQLite before 3.35 cannot DROP COLUMN, so the reverse rebuilds. Written
-- explicitly rather than relying on the operator's SQLite version: a rollback that
-- fails on an older build is not a rollback.
CREATE TABLE run_rebuild (
    id             INTEGER PRIMARY KEY,
    correlation_id TEXT    NOT NULL,
    kind           TEXT    NOT NULL DEFAULT 'baseline' CHECK (kind IN ('baseline','delta')),
    operator       TEXT    NOT NULL DEFAULT '',
    started_at     TEXT    NOT NULL,
    ended_at       TEXT,
    business_rules TEXT    NOT NULL DEFAULT '{}'
);
INSERT INTO run_rebuild
    (id, correlation_id, kind, operator, started_at, ended_at, business_rules)
SELECT id, correlation_id, kind, operator, started_at, ended_at, business_rules
FROM run;
DROP TABLE run;
ALTER TABLE run_rebuild RENAME TO run;
"""
