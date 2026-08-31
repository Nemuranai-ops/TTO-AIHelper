"""The composition root. Requirements: NFR-MNT-01, NFR-SEC-01, U1-NFR-ENC-01."""

import pytest

from tto_testgen.composition import build


def env(tmp_path) -> dict:
    """Two dummy scripts, so config.load()'s existence check passes.

    Neither script is ever actually run by these tests - McpClientSession is only
    opened during an ingestion run, which none of these exercise. The paths just
    need to exist for load() to succeed.
    """
    atlassian = tmp_path / "atlassian_mcp_server.py"
    bitbucket = tmp_path / "bitbucket_mcp_server.py"
    atlassian.write_text("")
    bitbucket.write_text("")
    return {
        "TAAS_ATLASSIAN_MCP_SCRIPT": str(atlassian),
        "TAAS_BITBUCKET_MCP_SCRIPT": str(bitbucket),
        "TAAS_LOG_LEVEL": "CRITICAL",
    }


class TestBuild:
    def test_fails_fast_on_missing_configuration(self, tmp_path):
        # A workspace with no vendored MCP scripts must surface before a database
        # file is created - here tmp_path is a bare fake workspace, not the real
        # repo root, so the default script paths resolve to nothing.
        result = build(tmp_path, {})
        assert not result.ok
        assert "TAAS_ATLASSIAN_MCP_SCRIPT" in result.message
        assert not (tmp_path / ".taas").exists()

    def test_builds_a_working_application(self, tmp_path):
        result = build(tmp_path, env(tmp_path))
        assert result.ok
        app = result.value
        try:
            assert len(app.server.registry.by_tier("read")) == 17
            assert app.run_state is not None
            assert app.coverage is not None
            assert app.requirements is not None
            assert app.generation is not None
            assert app.automation is not None
            assert app.handover is not None
            assert app.reporting is not None
            assert app.delta is not None
            # U7 registers 5, U3 registers 4, U4 registers 3, U5 registers 2,
            # U6 registers 2, U8 registers 2 write + 1 read, U2 registers 4 -
            # ingest_resources, analysis_upsert, api_model_derive, ui_model_upsert,
            # each opening its own MCP session per call rather than holding one open.
            assert len(app.server.registry.by_tier("write")) == 22
        finally:
            app.close()

    def test_all_state_stays_inside_the_workspace(self, tmp_path):
        # U1-NFR-ENC-01: nothing is written outside the workspace.
        app = build(tmp_path, env(tmp_path)).value
        try:
            root = tmp_path.resolve()
            assert app.config.db_path.is_relative_to(root)
            assert app.config.backup_dir.is_relative_to(root)
            assert app.config.export_dir.is_relative_to(root)
        finally:
            app.close()

    def test_schema_is_migrated_on_startup(self, tmp_path):
        from tto_testgen.adapters.sqlite.migrations import LATEST_VERSION
        from tto_testgen.adapters.sqlite.schema import current_version

        app = build(tmp_path, env(tmp_path)).value
        try:
            assert current_version(app.connection) == LATEST_VERSION
        finally:
            app.close()

    def test_second_startup_is_idempotent(self, tmp_path):
        first = build(tmp_path, env(tmp_path)).value
        first.close()
        second = build(tmp_path, env(tmp_path))
        assert second.ok
        second.value.close()

    def test_no_atlassian_or_bitbucket_credential_is_held_by_config(self, tmp_path):
        """The invariant that replaced the old credential-wrapping test.

        Neither tt-atlassian-mcp nor tt-bitbucket-mcp takes a secret from TAAS any
        more, so there is nothing left for Config to wrap - the absence of the
        field is the guarantee, the same way a missing method is the guarantee for
        the read-only source protocols.
        """
        app = build(tmp_path, env(tmp_path)).value
        try:
            for forbidden in ("atlassian_token", "bitbucket_token", "atlassian_base_url"):
                assert not hasattr(app.config, forbidden)
        finally:
            app.close()

    def test_health_check_reports_ok_after_build(self, tmp_path):
        app = build(tmp_path, env(tmp_path)).value
        try:
            assert app.server.call("health_check", {})["value"]["overall"] == "ok"
        finally:
            app.close()
