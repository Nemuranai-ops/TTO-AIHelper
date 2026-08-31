"""End to end: resources.md names a design folder, real screenshots get ingested.

This is the path that had no wiring at all until now - register_u2_tools was never
called from composition.py, so ingest_resources did not exist as a callable tool.
This test proves the actual production code an operator's `ingest_resources` call
runs, not a simplified stand-in for it: the real ResourceManifestAdapter parses a
real resources.md, the real classifier recognises the folder, the real
DesignFolderFetcher reads real files from disk, and the real IngestionService
writes real artefact rows through a real SQLite connection.
"""

from __future__ import annotations

from pathlib import Path

from tto_testgen.adapters.sources.dispatch import build_source_for
from tto_testgen.adapters.sources.manifest import ResourceManifestAdapter
from tto_testgen.adapters.sqlite.repositories import unit_of_work
from tto_testgen.platform.logging import configure
from tto_testgen.services.ingestion import IngestionService


def run(conn, workspace_root: Path):
    manifest = ResourceManifestAdapter(workspace_root / "resources.md", workspace_root)
    source_for = build_source_for(
        atlassian=None, bitbucket=None, workspace_root=workspace_root
    )
    service = IngestionService(
        lambda: unit_of_work(conn), manifest, source_for, configure("CRITICAL"),
    )
    return service.ingest_resources()


def test_screenshots_in_the_declared_folder_are_ingested_as_artefacts(conn, tmp_path):
    designs = tmp_path / "designs" / "checkout"
    designs.mkdir(parents=True)
    (designs / "checkout__basket.png").write_bytes(b"fake-png-one")
    (designs / "checkout__basket__empty.png").write_bytes(b"fake-png-two")
    (tmp_path / "resources.md").write_text("./designs/checkout\n", encoding="utf-8")

    result = run(conn, tmp_path)

    assert result.ok, getattr(result, "message", "")
    report = result.value
    assert report.failed == []
    assert report.unclassified == []
    assert len(report.succeeded) == 1
    assert report.succeeded[0]["type"] == "design-folder"
    assert report.succeeded[0]["artefacts"] == 2

    rows = conn.execute("SELECT * FROM artefact WHERE kind = 'screenshot'").fetchall()
    assert len(rows) == 2
    names = {r["source_identifier"] for r in rows}
    assert names == {"checkout__basket.png", "checkout__basket__empty.png"}


def test_the_resource_is_recorded_with_its_inferred_type(conn, tmp_path):
    designs = tmp_path / "designs"
    designs.mkdir()
    (designs / "checkout__basket.png").write_bytes(b"x")
    (tmp_path / "resources.md").write_text("designs\n", encoding="utf-8")

    run(conn, tmp_path)

    row = conn.execute("SELECT * FROM resource WHERE raw_ref = 'designs'").fetchone()
    assert row is not None
    assert row["type"] == "design-folder"
    assert row["status"] == "ingested"


def test_an_unassociated_screenshot_is_reported_without_failing_the_run(conn, tmp_path):
    designs = tmp_path / "designs"
    designs.mkdir()
    (designs / "checkout__basket.png").write_bytes(b"x")
    (designs / "random-screenshot.png").write_bytes(b"y")
    (tmp_path / "resources.md").write_text("designs\n", encoding="utf-8")

    report = run(conn, tmp_path).value

    assert report.failed == []
    assert report.succeeded[0]["artefacts"] == 1
    assert report.ceiling_notices
    assert "random-screenshot.png" in report.ceiling_notices[0]["guidance"]


def test_re_ingesting_unchanged_screenshots_skips_them(conn, tmp_path):
    """FR-ING-10 / NFR-PRF-04: no store, no re-fetch, on an unchanged run."""
    designs = tmp_path / "designs"
    designs.mkdir()
    (designs / "checkout__basket.png").write_bytes(b"x")
    (tmp_path / "resources.md").write_text("designs\n", encoding="utf-8")

    first = run(conn, tmp_path).value
    assert first.succeeded[0]["artefacts"] == 1

    second = run(conn, tmp_path).value
    assert second.skipped_unchanged
    assert second.skipped_unchanged[0]["artefacts"] == 1

    total = conn.execute("SELECT COUNT(*) FROM artefact").fetchone()[0]
    assert total == 1, "an unchanged re-ingestion must not duplicate the artefact"


def test_a_nonexistent_path_is_unclassified_not_a_failure(conn, tmp_path):
    """Rule 8 requires the path to already be a real directory (classify.py), so a
    typo'd folder never reaches DESIGN_FOLDER at all - it is reported as
    unclassified, the same as any other reference no rule recognised (BR-U2-1.3).
    The fetcher's own "folder not found" path (proven directly in
    test_source_dispatch.py) only matters for a folder deleted between
    classification and fetch - a narrower race, not a typo."""
    (tmp_path / "resources.md").write_text("nonexistent-folder\n", encoding="utf-8")
    report = run(conn, tmp_path).value
    assert report.succeeded == []
    assert report.failed == []
    assert report.unclassified == ["nonexistent-folder"]


def test_a_jira_link_alongside_a_design_folder_is_reported_but_not_fetched(conn, tmp_path):
    """No Atlassian session is supplied in this test (atlassian=None), matching a
    workspace with no MCP session available - the missing adapter must surface as
    a per-resource failure, not crash the whole run or silently skip the folder."""
    designs = tmp_path / "designs"
    designs.mkdir()
    (designs / "checkout__basket.png").write_bytes(b"x")
    (tmp_path / "resources.md").write_text(
        "designs\nhttps://example.atlassian.net/browse/PAY-12\n", encoding="utf-8"
    )

    report = run(conn, tmp_path).value

    assert report.succeeded[0]["type"] == "design-folder"
    assert any(f["type"] == "jira-issue" for f in report.failed)
