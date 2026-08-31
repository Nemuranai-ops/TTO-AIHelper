"""A1 SqliteSchemaManager and L2 MigrationRunner.

Every forward migration ships a tested reverse, so OD-02's rollback procedure -
`git checkout <tag>` then `uv sync` - stays true across a schema change rather than
stranding the database.

Requirements: NFR-REL-07, U1-NFR-DIST-04. Component: L2.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from tto_testgen.adapters.sqlite.migrations import ALL, LATEST_VERSION, Migration
from tto_testgen.platform.result import ErrorCode, Result, err, ok

VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


@dataclass(slots=True)
class MigrationReport:
    applied: list[int] = field(default_factory=list)
    reverted: list[int] = field(default_factory=list)
    from_version: int = 0
    to_version: int = 0



def split_statements(script: str) -> list[str]:
    """Split a DDL script into individual statements.

    `Connection.executescript` cannot be used here: it issues an implicit COMMIT
    before running, which would silently discard the explicit transaction a
    migration needs. Statements are therefore executed one at a time inside a
    BEGIN block.

    Trigger bodies contain semicolons inside `BEGIN ... END`, so a naive split on
    ";" would tear them apart. Depth is tracked so those semicolons are ignored.
    """
    statements: list[str] = []
    current: list[str] = []
    depth = 0

    for raw_line in script.splitlines():
        line = raw_line.split("--")[0] if raw_line.strip().startswith("--") else raw_line
        stripped = line.strip()
        if not stripped:
            continue

        current.append(line)
        upper = stripped.upper()

        # A trigger body opens with BEGIN and closes with END;
        if upper == "BEGIN" or upper.endswith(" BEGIN"):
            depth += 1
            continue
        if depth and upper.startswith("END"):
            depth -= 1
            if depth == 0 and stripped.endswith(";"):
                statements.append("\n".join(current).strip())
                current = []
            continue
        if depth:
            continue

        if stripped.endswith(";"):
            statements.append("\n".join(current).strip())
            current = []

    remainder = "\n".join(current).strip()
    if remainder:
        statements.append(remainder)
    return [s for s in statements if s and not s.startswith("--")]


def current_version(conn: sqlite3.Connection) -> int:
    conn.execute(VERSION_TABLE)
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def pending(conn: sqlite3.Connection) -> list[Migration]:
    at = current_version(conn)
    return [m for m in ALL if m.version > at]


def _known_versions() -> set[int]:
    return {m.version for m in ALL}


def migrate_up(conn: sqlite3.Connection, target: int | None = None) -> Result[MigrationReport]:
    """Apply pending migrations, each in its own transaction.

    A database at a version this build does not recognise is refused rather than
    guessed at: the shape of its data is unknown, and proceeding risks corrupting
    it in ways a backup cannot distinguish from intent.
    """
    at = current_version(conn)
    if at > LATEST_VERSION or (at > 0 and at not in _known_versions()):
        return err(
            ErrorCode.FAILED_MIGRATION,
            f"Database is at schema version {at}, which this build does not recognise "
            f"(latest known is {LATEST_VERSION})",
            remediation="Check out a build that knows this schema version, or restore a backup.",
        )

    ceiling = LATEST_VERSION if target is None else target
    report = MigrationReport(from_version=at, to_version=at)

    for migration in ALL:
        if migration.version <= at or migration.version > ceiling:
            continue
        try:
            conn.execute("BEGIN")
            for statement in split_statements(migration.up):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_version (version, name, applied_at) "
                "VALUES (?, ?, datetime('now'))",
                (migration.version, migration.name),
            )
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            conn.execute("ROLLBACK")
            return err(
                ErrorCode.FAILED_MIGRATION,
                f"Migration {migration.version} ({migration.name}) failed: {exc}",
            )
        report.applied.append(migration.version)
        report.to_version = migration.version

    return ok(report)


def migrate_down(conn: sqlite3.Connection, target: int) -> Result[MigrationReport]:
    """Revert migrations above `target`, newest first."""
    at = current_version(conn)
    report = MigrationReport(from_version=at, to_version=at)

    for migration in sorted(ALL, key=lambda m: m.version, reverse=True):
        if migration.version <= target or migration.version > at:
            continue
        try:
            conn.execute("BEGIN")
            for statement in split_statements(migration.down):
                conn.execute(statement)
            conn.execute("DELETE FROM schema_version WHERE version = ?", (migration.version,))
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            conn.execute("ROLLBACK")
            return err(
                ErrorCode.FAILED_MIGRATION,
                f"Reverse migration {migration.version} failed: {exc}",
            )
        report.reverted.append(migration.version)
        report.to_version = migration.version - 1

    return ok(report)


def ensure_schema(conn: sqlite3.Connection) -> Result[MigrationReport]:
    """Bring the database to the latest known version."""
    return migrate_up(conn)


def verify_reversibility(conn: sqlite3.Connection) -> Result[bool]:
    """Apply every migration and revert it, confirming the pair round-trips.

    Used in tests. A reverse migration nobody has run is a hypothesis, and
    U1-NFR-DIST-04 depends on it being a fact.
    """
    up = migrate_up(conn)
    if not up.ok:
        return up  # type: ignore[return-value]
    down = migrate_down(conn, 0)
    if not down.ok:
        return down  # type: ignore[return-value]
    if current_version(conn) != 0:
        return err(ErrorCode.FAILED_MIGRATION, "Reverse migrations did not return to version 0")
    return ok(True)
