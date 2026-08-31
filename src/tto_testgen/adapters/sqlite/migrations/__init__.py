"""Versioned, reversible schema migrations.

Every forward migration ships its reverse, and the pair is tested together
(U1-NFR-DIST-04). OD-02's rollback story is `git checkout <tag>` then `uv sync`,
which works cleanly for code - but the moment a migration has run, rolling the code
back leaves it facing a schema it does not understand. Requiring and testing the
reverse is what makes the stated rollback procedure true rather than aspirational.
"""

from __future__ import annotations

from dataclasses import dataclass

from tto_testgen.adapters.sqlite.migrations import (
    m001_initial,
    m002_lease_columns,
    m003_discrepancy,
    m004_gaps_and_reductions,
    m005_emitted_view,
    m006_emitted_view_kind,
    m007_run_baseline,
)


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    up: str
    down: str


ALL: tuple[Migration, ...] = (
    Migration(1, "initial schema", m001_initial.UP, m001_initial.DOWN),
    Migration(2, "lease heartbeat columns", m002_lease_columns.UP, m002_lease_columns.DOWN),
    Migration(3, "discrepancy table", m003_discrepancy.UP, m003_discrepancy.DOWN),
    Migration(
        4, "gaps and coverage reductions",
        m004_gaps_and_reductions.UP, m004_gaps_and_reductions.DOWN,
    ),
    Migration(5, "emitted view record", m005_emitted_view.UP, m005_emitted_view.DOWN),
    Migration(
        6, "emitted view kind",
        m006_emitted_view_kind.UP, m006_emitted_view_kind.DOWN,
    ),
    Migration(7, "run baseline columns", m007_run_baseline.UP, m007_run_baseline.DOWN),
)

LATEST_VERSION = max(m.version for m in ALL)
