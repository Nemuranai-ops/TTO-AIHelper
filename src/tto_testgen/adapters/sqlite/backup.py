"""L3 BackupManager - backup before risk, export after progress.

Two mechanisms because they protect against different failures. A SQLite file copy
restores byte-identically but is only readable by a compatible schema version; the
export is portable and survives a database the current code can no longer open.

The online backup API is used rather than a filesystem copy: copying the file while
a write is in flight produces a corrupt copy, and WAL makes that more likely rather
than less.

Requirements: U1-NFR-REC-01 to -04, NFR-REL-05, NFR-REL-06, RESILIENCY-12.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from tto_testgen.platform.result import ErrorCode, Result, err, ok


@dataclass(frozen=True, slots=True)
class BackupRef:
    path: Path
    taken_at: str
    operation: str
    bytes_written: int


@dataclass(slots=True)
class ExportManifest:
    destination: Path
    tables: dict[str, int] = field(default_factory=dict)
    exported_at: str = ""

    @property
    def total_rows(self) -> int:
        return sum(self.tables.values())


#: Tables carrying corpus content. Ordered so a rebuild can honour foreign keys.
EXPORT_TABLES: tuple[str, ...] = (
    "resource", "artefact", "feature", "journey", "business_rule",
    "api_endpoint", "screen", "ui_element", "testable_requirement",
    "coverage_item", "test_case", "test_step", "test_data", "trace_link",
    "automated_test", "run", "unit_state", "change_event",
)


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup_before(
    conn: sqlite3.Connection, operation: str, backup_dir: Path
) -> Result[BackupRef]:
    """Take a consistent backup before a destructive or schema-changing operation."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    taken_at = _stamp()
    safe_operation = "".join(c if c.isalnum() or c in "-_" else "-" for c in operation)[:40]
    destination = backup_dir / f"taas-{taken_at}-{safe_operation}.db"

    try:
        target = sqlite3.connect(str(destination))
        with target:
            # The online backup API takes a consistent snapshot of a live database.
            # A filesystem copy during an in-flight write would not.
            conn.backup(target)
        target.close()
    except sqlite3.Error as exc:
        return err(ErrorCode.FAILED_DB_UNAVAILABLE, f"Backup failed: {exc}")

    return ok(
        BackupRef(
            path=destination,
            taken_at=taken_at,
            operation=operation,
            bytes_written=destination.stat().st_size,
        )
    )


def list_backups(backup_dir: Path) -> list[BackupRef]:
    if not backup_dir.exists():
        return []
    refs = []
    for path in sorted(backup_dir.glob("taas-*.db")):
        parts = path.stem.split("-", 2)
        refs.append(
            BackupRef(
                path=path,
                taken_at=parts[1] if len(parts) > 1 else "",
                operation=parts[2] if len(parts) > 2 else "",
                bytes_written=path.stat().st_size,
            )
        )
    return refs


def prune(backup_dir: Path, keep: int = 10) -> Result[int]:
    """Retain the newest `keep` backups. U1-NFR-REC-04."""
    if keep < 1:
        return err(ErrorCode.FAILED_INTERNAL, "keep must be at least 1")
    backups = list_backups(backup_dir)
    removed = 0
    for ref in backups[: max(0, len(backups) - keep)]:
        ref.path.unlink(missing_ok=True)
        removed += 1
    return ok(removed)


def export_corpus(conn: sqlite3.Connection, destination: Path) -> Result[ExportManifest]:
    """Write the corpus in a portable form.

    JSON Lines per table: rebuildable into a fresh schema without the database
    file, which is the failure a byte-identical backup cannot cover.
    """
    destination.mkdir(parents=True, exist_ok=True)
    manifest = ExportManifest(destination=destination, exported_at=_stamp())

    try:
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table in EXPORT_TABLES:
            if table not in existing:
                continue
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            out = destination / f"{table}.jsonl"
            with out.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(dict(row), default=str, sort_keys=True) + "\n")
            manifest.tables[table] = len(rows)
    except sqlite3.Error as exc:
        return err(ErrorCode.FAILED_DB_UNAVAILABLE, f"Export failed: {exc}")

    (destination / "manifest.json").write_text(
        json.dumps(
            {"exported_at": manifest.exported_at, "tables": manifest.tables},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return ok(manifest)


def restore(backup: BackupRef, db_path: Path) -> Result[None]:
    """Restore a backup over the working database."""
    if not backup.path.exists():
        return err(ErrorCode.FAILED_INTERNAL, f"Backup not found: {backup.path.name}")
    try:
        source = sqlite3.connect(str(backup.path))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(str(db_path))
        with target:
            source.backup(target)
        source.close()
        target.close()
    except sqlite3.Error as exc:
        return err(ErrorCode.FAILED_DB_UNAVAILABLE, f"Restore failed: {exc}")
    return ok(None)
