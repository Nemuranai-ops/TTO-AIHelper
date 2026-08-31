# Restore Procedure and Rehearsal Scenario

**Satisfies**: OD-03, U1-NFR-REH-01 to U1-NFR-REH-04, RESILIENCY-13, RESILIENCY-14

A backup nobody has restored is a hypothesis. This document is the procedure, and
the rehearsal is what turns it into a fact.

---

## What is at risk

The SQLite database at `.taas/taas.db` is the system of record for the test corpus.
Losing it loses every test case, coverage decision and traceability link generated
so far — potentially weeks of work.

**Recovery point**: one unit of work. A backup is taken before every destructive or
schema-changing operation, and a portable export is written after every completed
unit. At most one feature's generation is ever at risk.

---

## The two mechanisms

|  | Backup | Export |
|---|---|---|
| Location | `.taas/backups/` | `generated/exports/` |
| Form | SQLite file, via the online backup API | JSON Lines per table |
| Restores | Byte-identical database | Corpus content, into a fresh schema |
| Covers | A failed migration or destructive operation | Loss or corruption of the file, and schema version drift |
| Retention | Newest 10 | Per unit of work |

Both exist because neither covers the other's failure. A file copy is only readable
by a compatible schema version; an export survives a database the current code can
no longer open.

The online backup API is used rather than a filesystem copy: copying a SQLite file
while a write is in flight produces a corrupt copy, and WAL journalling makes that
more likely rather than less.

---

## Procedure 1 — Restore from backup

Use when the database is lost or corrupt and the code version is unchanged.

```bash
ls -lt .taas/backups/          # newest first; names carry the triggering operation
mv .taas/taas.db .taas/taas.db.broken   # keep the broken file for diagnosis
uv run python -c "
from pathlib import Path
from tto_testgen.adapters.sqlite.backup import BackupRef, restore
ref = BackupRef(path=Path('.taas/backups/<chosen>.db'), taken_at='', operation='', bytes_written=0)
print(restore(ref, Path('.taas/taas.db')))
"
uv run python -c "
from tto_testgen.composition import build
app = build().value
print(app.server.call('health_check', {}))
print(app.server.call('run_status', {}))
"
```

Confirm the case count matches what `run_status` reported before the loss. **Do not
delete `taas.db.broken` until you have.**

---

## Procedure 2 — Rebuild from export

Use when no usable backup exists, or when the backup predates a schema migration the
current code requires.

```bash
mv .taas/taas.db .taas/taas.db.broken 2>/dev/null || true
uv run tto-testgen-mcp   # creates and migrates a fresh schema, then Ctrl-C
```

Then load `generated/exports/<latest>/` table by table, honouring the order in
`EXPORT_TABLES` (it respects foreign keys). `manifest.json` in that directory records
the row count per table — reconcile against it.

**Expect a gap.** The export is written per completed unit, so anything generated
after the last completed unit is not in it. Re-run those units; the traceability
links make it clear which.

---

## Rehearsal scenario

Execute this **before the corpus first exceeds 1,000 cases**, and **after every
schema migration**. Both are points where the value at risk rises sharply.

### Setup
1. Note the current active case count from `run_status`.
2. Confirm at least one backup exists in `.taas/backups/`.
3. Confirm an export exists in `generated/exports/`.

### Scenario A — database loss
1. `mv .taas/taas.db /tmp/rehearsal-hidden.db`
2. Follow **Procedure 1**.
3. **Pass**: the case count matches, and `health_check` reports `ok`.

### Scenario B — corruption
1. `printf 'corrupt' > .taas/taas.db`
2. Attempt startup. **Pass**: it fails with `FAILED_DB_UNAVAILABLE` and a clear
   message, rather than proceeding against a damaged file.
3. Follow **Procedure 1**. **Pass**: as above.

### Scenario C — rollback across a migration
1. Note the schema version.
2. Apply a migration, then `git checkout` the previous tag and `uv sync`.
3. **Pass**: the older code refuses to run against the newer schema, naming the
   version, rather than corrupting data.
4. Run the reverse migration. **Pass**: the older code starts cleanly.

### Record the result

| Field | Value |
|---|---|
| Date | |
| Trigger | corpus milestone / migration `<version>` |
| Scenarios executed | A / B / C |
| Outcome | pass / fail |
| Time to recover | |
| Issues found | |

Append each rehearsal to this file. An untested backup is a hypothesis; the record
is what makes it evidence.
