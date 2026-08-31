# Logical Components — U1 Core Platform

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U1 | **Stage**: NFR Design
**Version**: 1.0 | **Date**: 2026-08-29

Four supporting components beyond the 20 defined in Application Design. Each exists because a
specific NFR would otherwise have no owner.

---

## Why Four, and Why These

| Component | The requirement that would otherwise be unowned |
|---|---|
| L1 ConnectionFactory | `foreign_keys = ON` asserted, not merely set — SQLite defaults it off and fails silently |
| L2 MigrationRunner | U1-NFR-DIST-04 — rollback across a schema migration must not strand the database |
| L3 BackupManager | OD-01's recovery point of one unit of work |
| L4 BenchmarkHarness | The Q12 decision that performance budgets are proven rather than asserted |

**No rate limiter** (Question 8 option C declined): the external MCP servers enforce their own
limits and P-RES-02 handles 429 correctly. A client-side limiter would need tuning against limits
we do not control.

---

## L1: ConnectionFactory

**Ring**: Adapter (alongside A1, A2)
**Delivers**: U1-NFR-PRF-01, U1-NFR-REL-01, referential integrity generally

### Responsibility

Produce configured SQLite connections and prove the configuration took effect.

| Setting | Value | Why |
|---|---|---|
| `journal_mode` | WAL | Readers do not block the writer; a report can run while a batch commits |
| `foreign_keys` | ON | Referential rules in `domain-entities.md` depend on it |
| `busy_timeout` | 5000 ms | A brief lock waits rather than failing |
| `synchronous` | NORMAL | Safe under WAL, and materially faster than FULL |

### Interface

```
get_connection() -> Connection          # configured and asserted
assert_configuration(conn) -> Result    # raises at startup on mismatch
close(conn) -> None
```

### The assertion

After applying each PRAGMA, the factory reads it back and compares. A mismatch fails at startup.

**This exists because the failure is otherwise invisible.** `PRAGMA foreign_keys = ON` is silently
ignored inside a transaction, and a schema whose foreign keys are not enforced behaves normally
until inconsistent data surfaces months later. Reading the value back converts a silent
misconfiguration into an immediate, obvious failure.

### Lifecycle

One connection per unit of work, created on entry and closed on exit. **No pool** — one operator,
one process, and a pool would introduce exhaustion failure modes to solve a contention problem that
does not exist.

---

## L2: MigrationRunner

**Ring**: Adapter (within A1)
**Delivers**: U1-NFR-REL-07, U1-NFR-DIST-04, NFR-REL-07

### Responsibility

Apply versioned forward migrations, apply reverse migrations on rollback, and refuse to run against
a database whose version it does not recognise.

### Interface

```
current_version(conn) -> int
pending(conn) -> list[Migration]
migrate_up(conn, target=None) -> Result[MigrationReport]
migrate_down(conn, target) -> Result[MigrationReport]
verify_reversibility(migration) -> Result      # used in tests
```

### Rules

| Rule | Reason |
|---|---|
| Every forward migration ships a reverse | U1-NFR-DIST-04 — rollback across a migration must not strand the database |
| The reverse is tested with the forward | A reverse migration nobody has run is a hypothesis |
| Backup is taken before any migration | OD-01, via L3 |
| A migration runs in one transaction | Partial schema change is unrecoverable without a restore |
| A database at an unknown version is refused | Better to stop than to guess at the shape of the data |
| Version recorded in a `schema_version` table | Single source of truth for L1 and the health check |

### Why reversibility is enforced rather than encouraged

OD-02's rollback story is `git checkout <tag>` then `uv sync`. That works cleanly for code. The
moment a migration has run, rolling the code back leaves it facing a schema it does not understand.
Requiring and testing the reverse is what makes the stated rollback procedure true rather than
aspirational.

---

## L3: BackupManager

**Ring**: Adapter (within A1)
**Delivers**: U1-NFR-REC-01 to -04, NFR-REL-05, NFR-REL-06, RESILIENCY-12

### Responsibility

Take backups before risk, export after progress, and keep the set bounded.

### Interface

```
backup_before(operation: str) -> Result[BackupRef]
export_corpus(destination: Path) -> Result[ExportManifest]
list_backups() -> list[BackupRef]
restore(ref: BackupRef) -> Result[None]
prune(keep: int = 10) -> Result[int]
```

### Triggers

| Trigger | Action |
|---|---|
| Before any migration | Backup |
| Before any destructive operation | Backup |
| After every `unit_complete` | Export |
| Backups exceed 10 | Prune oldest |

### Backup versus export

Two different mechanisms for two different failure modes, which is why both exist.

| | Backup | Export |
|---|---|---|
| Form | SQLite file copy via the online backup API | YAML and CSV |
| Protects against | A failed migration or destructive operation | Loss or corruption of the database file, and version drift |
| Restores | Byte-identical database | Corpus content, rebuildable into a fresh schema |
| Requirement | NFR-REL-05 | NFR-REL-06 |

**A file copy alone is insufficient** because it is only readable by a compatible schema version.
The export is portable: it survives a database the current code can no longer open.

**The online backup API rather than a filesystem copy** — copying a SQLite file while a write is in
flight produces a corrupt copy, and WAL mode makes that more likely, not less.

---

## L4: BenchmarkHarness

**Ring**: Test support (not shipped in the runtime package)
**Delivers**: U1-NFR-PRF-01, U1-NFR-PRF-02, the Q12 verification decision

### Responsibility

Generate a synthetic corpus at target scale and assert the performance budgets.

### Interface

```
seed_corpus(cases: int = 10_000, seed: int = 42) -> CorpusStats
bench_single_case_op() -> Duration        # asserts < 200 ms
bench_full_report() -> Duration           # asserts < 30 s
bench_dedup_candidates() -> QueryPlan     # asserts idx_case_bucket is used
report() -> BenchmarkReport
```

### Design

| Property | Value |
|---|---|
| Corpus generation | From the D1 domain model, using the Hypothesis strategies already written for the property suite |
| Determinism | Fixed seed, so runs are comparable |
| Realism | Feature distribution and step counts drawn from the coverage model, not uniform |
| Index verification | `EXPLAIN QUERY PLAN` asserted, not inferred from timing |
| Execution | On demand and before any release; not on every commit |

### Why the index is asserted separately from the timing

A timing test can pass on a small corpus while the planner is doing a full scan, and then fail
mysteriously at volume. Asserting that `idx_case_bucket` appears in the query plan catches the
regression at its cause rather than at its symptom.

**Reusing the property-test strategies** means the synthetic corpus is realistic by construction and
there is no second generator to keep in step with the domain model.

---

## Placement in the Hexagon

```
        +-------------------------------------------+
        |             MCP SURFACE  M1, M2           |
        +-------------------------------------------+
                            |
        +-------------------------------------------+
        |        APPLICATION SERVICES  S1-S10       |
        +-------------------------------------------+
              |                          |
   +---------------------+    +---------------------+
   |   DOMAIN  D1-D8     |<---|    PORTS  P1-P3     |
   |   pure, no I/O      |    |                     |
   +---------------------+    +---------------------+
                                         ^
        +-------------------------------------------+
        |                 ADAPTERS                  |
        |   A1  A2   +  L1 ConnectionFactory        |
        |            +  L2 MigrationRunner          |
        |            +  L3 BackupManager            |
        +-------------------------------------------+

        +-------------------------------------------+
        |   TEST SUPPORT  (not in runtime package)  |
        |            L4 BenchmarkHarness            |
        +-------------------------------------------+
```

**Text alternative**: L1, L2 and L3 sit in the adapter ring beside A1 and A2, so they may depend on
ports and domain types but not on services. L4 is test support and is excluded from the runtime
package entirely. None of the four is reachable from the domain, so the dependency rule and the
import contracts hold unchanged.

---

## Configuration Surface

All settings resolve through X3 ConfigAndSecrets at startup into the frozen config object.

| Setting | Default | Component | Requirement |
|---|---|---|---|
| `TAAS_DB_PATH` | `.taas/taas.db` | L1 | U1-NFR-ENC-01 |
| `TAAS_BUSY_TIMEOUT_MS` | 5000 | L1 | |
| `TAAS_BACKUP_DIR` | `.taas/backups` | L3 | U1-NFR-REC-01 |
| `TAAS_BACKUP_KEEP` | 10 | L3 | U1-NFR-REC-04 |
| `TAAS_EXPORT_DIR` | `generated/exports` | L3 | U1-NFR-REC-02 |
| `TAAS_RETRY_ATTEMPTS` | 3 | X4 | U1-NFR-REL-02 |
| `TAAS_RETRY_BASE_MS` | 1000 | X4 | U1-NFR-REL-02 |
| `TAAS_PAGE_SIZE` | 200 | P-SCL-01 | U1-NFR-SCL-03 |
| `TAAS_SIMILARITY_THRESHOLD` | 0.90 | D4 | BR-1.3 |
| `TAAS_COMMIT_LOOKBACK_DAYS` | 180 | D3 | BR-3.1 |
| `TAAS_LOG_LEVEL` | INFO | X2 | U1-NFR-SEC-06 |

**Two of these are business rules rather than infrastructure settings**:
`TAAS_SIMILARITY_THRESHOLD` and `TAAS_COMMIT_LOOKBACK_DAYS`. They are configurable because tuning
them is legitimate, and their defaults are the values decided in `business-rules.md`. Changing
either changes the corpus, so a change is recorded in the run metadata alongside the results it
produced.

---

## Dependency Rule Verification

| Component | Imports | Violates the rule? |
|---|---|---|
| L1 ConnectionFactory | stdlib `sqlite3`, X1, X2 | No |
| L2 MigrationRunner | L1, X1, X2 | No |
| L3 BackupManager | L1, stdlib, X1, X2 | No |
| L4 BenchmarkHarness | domain, adapters, Hypothesis strategies (test scope only) | No — test support is outside the runtime import graph |

No new component imports a service. No new component is imported by the domain. The import-linter
contracts (P-MNT-02) hold unchanged, and are extended to cover the new adapter modules.

---

## Requirement Coverage

All 45 U1 NFR requirements have a delivering pattern (in
[nfr-design-patterns.md](nfr-design-patterns.md) §8) or one of these four components. No requirement
is unowned.
