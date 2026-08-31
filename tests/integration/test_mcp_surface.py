"""M1, M2. Requirements: US-ENB-02, US-ENB-04, NFR-SEC-02, NFR-SEC-03, NFR-SEC-07/08."""

import inspect

import pytest
from pydantic import BaseModel

from tto_testgen.adapters.sqlite.repositories import MAX_PAGE_SIZE
from tto_testgen.mcp import server as server_module
from tto_testgen.domain.model import StageName
from tto_testgen.mcp.server import McpServer, ToolRegistry, ToolSpec
from tto_testgen.mcp.tools_read import register_read_tools
from tto_testgen.mcp.tools_write import register_write_tools
from tto_testgen.platform.logging import configure
from tto_testgen.platform.result import ErrorCode, err, ok


@pytest.fixture
def registry(conn):
    from tto_testgen.adapters.sqlite.repositories import unit_of_work
    from tto_testgen.services.runstate import RunStateService

    reg = ToolRegistry()
    register_read_tools(reg, lambda: conn)
    register_write_tools(reg, RunStateService(lambda: unit_of_work(conn)))
    return reg


@pytest.fixture
def srv(registry, tmp_path):
    return McpServer(registry, configure("CRITICAL"), workspace_root=tmp_path)


class TestToolRegistry:
    def test_read_and_write_tiers_are_registered(self, registry):
        assert len(registry.by_tier("read")) == 16
        assert len(registry.by_tier("write")) == 5

    def test_duplicate_registration_is_refused(self, registry):
        class Args(BaseModel):
            pass

        with pytest.raises(ValueError, match="already registered"):
            registry.register(ToolSpec("health_check", "dup", Args, lambda a, l: ok(1), "read"))

    def test_unknown_tier_is_refused(self, registry):
        class Args(BaseModel):
            pass

        with pytest.raises(ValueError, match="tier"):
            registry.register(ToolSpec("x", "d", Args, lambda a, l: ok(1), "sideways"))

    def test_every_tool_publishes_a_json_schema(self, srv):
        for tool in srv.list_tools():
            assert tool["inputSchema"]["type"] == "object"
            assert tool["description"]
            assert tool["tier"] in ("read", "write")


class TestBoundaryGuarantees:
    def test_no_exception_crosses_the_boundary(self, registry, tmp_path):
        class Args(BaseModel):
            pass

        registry.register(
            ToolSpec(
                "explode",
                "raises",
                Args,
                lambda a, l: (_ for _ in ()).throw(RuntimeError("boom in /etc/shadow")),
                "write",
            )
        )
        srv = McpServer(registry, configure("CRITICAL"), workspace_root=tmp_path)
        payload = srv.call("explode", {})
        assert payload["ok"] is False
        assert payload["code"] == ErrorCode.FAILED_INTERNAL.value

    def test_error_messages_are_sanitised(self, registry, tmp_path):
        class Args(BaseModel):
            pass

        registry.register(
            ToolSpec(
                "leak",
                "leaks",
                Args,
                lambda a, l: (_ for _ in ()).throw(RuntimeError("token=abc123 at /etc/shadow")),
                "write",
            )
        )
        srv = McpServer(registry, configure("CRITICAL"), workspace_root=tmp_path)
        message = srv.call("leak", {})["message"]
        assert "abc123" not in message
        assert "/etc/shadow" not in message

    def test_schema_validation_runs_before_the_handler(self, registry, tmp_path):
        called = []

        class Args(BaseModel):
            count: int

        registry.register(
            ToolSpec("counted", "d", Args, lambda a, l: (called.append(1), ok(1))[1], "read")
        )
        srv = McpServer(registry, configure("CRITICAL"), workspace_root=tmp_path)
        payload = srv.call("counted", {"count": "not a number"})
        assert payload["ok"] is False
        assert called == []  # NFR-SEC-03: no logic ran

    def test_unknown_tool_returns_a_result_not_an_error(self, srv):
        payload = srv.call("no_such_tool", {})
        assert payload["ok"] is False
        assert "list_tools" in payload["remediation"]

    def test_rejections_and_failures_are_distinguishable(self, registry, tmp_path):
        class Args(BaseModel):
            pass

        registry.register(
            ToolSpec("rej", "d", Args, lambda a, l: err(ErrorCode.REJECTED_NO_STEPS, "x"), "write")
        )
        registry.register(
            ToolSpec("fail", "d", Args, lambda a, l: err(ErrorCode.FAILED_TIMEOUT, "x"), "write")
        )
        srv = McpServer(registry, configure("CRITICAL"), workspace_root=tmp_path)
        # The agent must respond differently to "fix your input" and "the system
        # broke". The family is what lets it branch without parsing prose.
        assert srv.call("rej", {})["family"] == "rejected"
        assert srv.call("fail", {})["family"] == "failed"

    def test_every_failure_carries_remediation(self, srv):
        payload = srv.call("feature_get", {})
        assert payload["ok"] is False
        assert payload["remediation"]

    def test_server_opens_no_network_listener(self):
        """NFR-SEC-02: stdio only, no socket bound anywhere in the MCP package.

        Checked by inspecting imports rather than searching for substrings. A naive
        text search for "bind(" matches `logger.bind(...)`, which is correlation
        context, not a socket - and a check that cries wolf gets weakened until it
        stops catching anything.
        """
        import ast
        import pathlib

        import tto_testgen.mcp as mcp_package

        forbidden = {
            "socket", "socketserver", "http", "http.server", "asyncio",
            "uvicorn", "starlette", "fastapi", "flask", "aiohttp",
        }
        offenders = []
        for path in pathlib.Path(mcp_package.__file__).parent.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    root = name.split(".")[0]
                    if root in forbidden or name in forbidden:
                        offenders.append(f"{path.name}: {name}")
        assert offenders == [], f"MCP package imports network machinery: {offenders}"


class TestGateEnforcement:
    def test_unit_begin_issues_a_lease(self, srv):
        payload = srv.call("unit_begin", {"unit_ref": "checkout", "stage": "cases"})
        assert payload["ok"] and payload["value"]["lease_id"]

    def test_in_progress_unit_is_not_silently_resumed(self, srv):
        """US-BAT-03 AC3: the operator decides whether to restart an interrupted unit.

        Since U7, the guidance depends on lease age: a freshly claimed unit is
        reported active and the operator is told to wait, while a stale one is told
        how to restart it. Both refuse; only the advice differs, which is the point
        of classifying rather than issuing one blanket message.
        """
        srv.call("unit_begin", {"unit_ref": "checkout", "stage": "cases"})
        payload = srv.call("unit_begin", {"unit_ref": "checkout", "stage": "cases"})
        assert payload["code"] == ErrorCode.FAILED_LOCKED.value
        assert payload["remediation"]
        assert payload["context"]["lease_status"]["classification"] == "active"

    def test_a_stale_lease_is_told_how_to_restart(self, conn, tmp_path):
        from datetime import datetime, timedelta, timezone

        from tto_testgen.adapters.sqlite.repositories import unit_of_work
        from tto_testgen.mcp.tools_write import register_write_tools
        from tto_testgen.services.runstate import RunStateService

        base = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
        fresh = RunStateService(lambda: unit_of_work(conn), clock=lambda: base)
        later = RunStateService(
            lambda: unit_of_work(conn), clock=lambda: base + timedelta(hours=2)
        )
        fresh.begin_unit("checkout", StageName.CASES)

        reg = ToolRegistry()
        register_write_tools(reg, later)
        srv = McpServer(reg, configure("CRITICAL"), workspace_root=tmp_path)
        payload = srv.call("unit_begin", {"unit_ref": "checkout", "stage": "cases"})
        assert payload["context"]["lease_status"]["classification"] == "stale"
        assert "regenerate=true" in payload["remediation"]

    def test_completed_unit_requires_explicit_regeneration(self, srv):
        lease = srv.call("unit_begin", {"unit_ref": "checkout", "stage": "cases"})["value"]["lease_id"]
        srv.call("unit_complete", {"lease_id": lease, "unit_ref": "checkout", "stage": "cases"})
        blocked = srv.call("unit_begin", {"unit_ref": "checkout", "stage": "cases"})
        assert blocked["code"] == ErrorCode.REJECTED_ALREADY_COMPLETE.value
        allowed = srv.call(
            "unit_begin", {"unit_ref": "checkout", "stage": "cases", "regenerate": True}
        )
        assert allowed["ok"]

    def test_completion_requires_the_matching_lease(self, srv):
        srv.call("unit_begin", {"unit_ref": "checkout", "stage": "cases"})
        payload = srv.call(
            "unit_complete",
            {"lease_id": "not-the-lease", "unit_ref": "checkout", "stage": "cases"},
        )
        assert payload["code"] == ErrorCode.FAILED_LOCKED.value

    def test_completing_a_unit_never_begun_is_refused(self, srv):
        payload = srv.call(
            "unit_complete", {"lease_id": "x", "unit_ref": "never", "stage": "cases"}
        )
        assert payload["ok"] is False

    def test_only_the_test_lead_may_approve_the_coverage_baseline(self, srv):
        # FR-COV-06. The one approval restricted to a single role, enforced rather
        # than merely assigned.
        for role in ("test-analyst", "test-automation-engineer"):
            payload = srv.call(
                "stage_approve",
                {"unit_ref": "checkout", "stage": "coverage", "approver": "sam", "role": role},
            )
            assert payload["code"] == ErrorCode.REJECTED_ROLE_NOT_PERMITTED.value
        allowed = srv.call(
            "stage_approve",
            {"unit_ref": "checkout", "stage": "coverage", "approver": "lead", "role": "test-lead"},
        )
        assert allowed["ok"]

    def test_other_stages_are_not_role_restricted(self, srv):
        payload = srv.call(
            "stage_approve",
            {"unit_ref": "checkout", "stage": "cases", "approver": "sam", "role": "test-analyst"},
        )
        assert payload["ok"]

    def test_approval_binds_to_content(self, srv, conn):
        srv.call(
            "stage_approve",
            {
                "unit_ref": "checkout",
                "stage": "coverage",
                "approver": "lead",
                "role": "test-lead",
                "content_hash": "a" * 64,
            },
        )
        stored = conn.execute(
            "SELECT approved_content_hash FROM unit_state "
            "WHERE unit_ref='checkout' AND stage='coverage'"
        ).fetchone()[0]
        assert stored == "a" * 64

    def test_unknown_stage_is_rejected_with_the_valid_set(self, srv):
        payload = srv.call("unit_begin", {"unit_ref": "checkout", "stage": "invent"})
        assert payload["ok"] is False
        assert "ingest" in payload["remediation"]


class TestReadTier:
    def test_run_status_reports_without_proposing(self, srv):
        # C-12: the operator names the next unit. This tool has no method that
        # could select one.
        payload = srv.call("run_status", {})
        assert payload["ok"]
        assert "reporting only" in payload["value"]["note"]

    def test_page_size_is_hard_capped(self, srv):
        payload = srv.call("testcases_query", {"limit": MAX_PAGE_SIZE})
        assert payload["ok"]
        over = srv.call("testcases_query", {"limit": MAX_PAGE_SIZE + 1})
        assert over["ok"] is False  # schema rejects it before the handler runs

    def test_feature_get_requires_an_identifier(self, srv):
        assert srv.call("feature_get", {})["ok"] is False

    def test_coverage_get_requires_a_scope(self, srv):
        assert srv.call("coverage_get", {})["ok"] is False

    def test_gap_query_shows_empty_categories(self, srv):
        # A silent section is indistinguishable from a missing check.
        categories = srv.call("gap_query", {})["value"]["categories"]
        assert categories
        assert all("count" in v for v in categories.values())

    def test_trace_matrix_reports_uncovered_requirements(self, srv, seeded):
        value = srv.call("trace_matrix", {})["value"]
        assert value["consistent"] is True
        assert "TR-CHECKOUT-00001" in value["uncovered"]

    def test_duplicates_check_does_not_write(self, srv, conn, seeded):
        before = conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0]
        srv.call(
            "duplicates_check",
            {
                "feature_slug": "checkout",
                "test_type": "boundary",
                "step_count": 1,
                "normalised_hash": "b" * 64,
            },
        )
        assert conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == before

    def test_health_check_reports_schema_version(self, srv):
        value = srv.call("health_check", {})["value"]
        assert value["overall"] == "ok"
        assert "schema v" in value["components"][0]["detail"]
