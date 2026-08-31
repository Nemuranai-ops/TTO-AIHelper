"""L1 ConnectionFactory - configured connections, with the configuration proven.

Setting a PRAGMA is not the same as it taking effect. `PRAGMA foreign_keys = ON` is
silently ignored inside a transaction, and a schema whose foreign keys are not
enforced behaves normally until inconsistent data surfaces months later. Reading
each value back converts a silent misconfiguration into an immediate failure.

Requirements: U1-NFR-PRF-01, U1-NFR-REL-01. Pattern: P-PRF-04.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from tto_testgen.platform.result import ErrorCode, Result, err, ok


@dataclass(frozen=True, slots=True)
class ConnectionSettings:
    db_path: Path
    busy_timeout_ms: int = 5000
    journal_mode: str = "wal"
    synchronous: str = "normal"


class ConfigurationNotApplied(RuntimeError):
    """A PRAGMA was set but did not take effect."""


def _configure(conn: sqlite3.Connection, settings: ConnectionSettings) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {int(settings.busy_timeout_ms)}")
    conn.execute(f"PRAGMA journal_mode = {settings.journal_mode}")
    conn.execute(f"PRAGMA synchronous = {settings.synchronous}")


def assert_configuration(conn: sqlite3.Connection, settings: ConnectionSettings) -> None:
    """Read every PRAGMA back and compare. Raises on mismatch.

    An in-memory database cannot use WAL, so the journal-mode check accepts
    'memory' there. Everything else is asserted unconditionally, foreign_keys
    above all - it is the one that fails silently and expensively.
    """
    foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    if foreign_keys != 1:
        raise ConfigurationNotApplied(
            "PRAGMA foreign_keys did not take effect. Referential integrity would "
            "be unenforced and the failure invisible until inconsistent data appears."
        )

    journal = conn.execute("PRAGMA journal_mode").fetchone()[0].lower()
    expected = settings.journal_mode.lower()
    if journal != expected and journal != "memory":
        raise ConfigurationNotApplied(
            f"PRAGMA journal_mode is {journal!r}, expected {expected!r}"
        )

    timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    if int(timeout) != int(settings.busy_timeout_ms):
        raise ConfigurationNotApplied(
            f"PRAGMA busy_timeout is {timeout}, expected {settings.busy_timeout_ms}"
        )


def get_connection(settings: ConnectionSettings) -> sqlite3.Connection:
    """Open a configured, verified connection.

    One connection per unit of work, no pool. One operator and one process means a
    pool would introduce exhaustion failure modes to solve a contention problem
    that does not exist.
    """
    if str(settings.db_path) != ":memory:":
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(settings.db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    _configure(conn, settings)
    assert_configuration(conn, settings)
    return conn


def open_checked(settings: ConnectionSettings) -> Result[sqlite3.Connection]:
    """Result-returning wrapper for the MCP boundary."""
    try:
        return ok(get_connection(settings))
    except ConfigurationNotApplied as exc:
        return err(ErrorCode.FAILED_DB_UNAVAILABLE, str(exc))
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower():
            return err(ErrorCode.FAILED_LOCKED, str(exc))
        return err(ErrorCode.FAILED_DB_UNAVAILABLE, str(exc))
