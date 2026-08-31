"""L6 McpClientSession against a REAL subprocess.

Every other test of this session's adapters uses FakeSession, which fakes call()
already unwrapped - it never had an MCP envelope to unwrap. That is exactly why the
bug this file exists to catch went undetected for as long as it did: call() returned
result.get("result", {}) directly, which is {content, structuredContent, isError} -
never the tool's own payload - and never checked isError at all, so a tool that ran
and reported its own failure was silently read as ok({}).

tt-bitbucket-mcp is the one vendored server that needs no credentials and touches no
network (git-based, reads clones already on disk), so it is the one a unit test can
spawn directly and cheaply.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tto_testgen.adapters.mcp_client import McpClientSession, ServerSpec
from tto_testgen.platform.logging import configure
from tto_testgen.platform.result import ErrorCode

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_SCRIPT = REPO_ROOT / "src" / "tt-bitbucket-mcp" / "bitbucket_mcp_server.py"


@pytest.fixture
def log():
    return configure("CRITICAL")


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "orders"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    (repo / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "a.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "PAY-1 initial"], cwd=repo, check=True)
    return repo


def spec() -> ServerSpec:
    assert SERVER_SCRIPT.is_file(), f"vendored server missing: {SERVER_SCRIPT}"
    return ServerSpec(name="tto-bitbucket", command=sys.executable, args=[str(SERVER_SCRIPT)])


class TestEnvelopeUnwrapping:
    def test_a_successful_call_returns_the_tools_own_payload_not_the_envelope(self, log, tmp_path, git_repo):
        with McpClientSession([spec()], log) as session:
            result = session.call("tto-bitbucket", "bitbucket_repos", {"root": str(tmp_path)})

        assert result.ok, getattr(result, "message", "")
        # The raw envelope has content/structuredContent/isError at the top level;
        # a caller reading result.value must see the tool's own fields directly.
        assert "content" not in result.value
        assert "structuredContent" not in result.value
        assert "repos" in result.value
        assert result.value["repos"][0]["repo"] == "orders"

    def test_a_tool_reported_failure_is_an_err_not_a_silent_ok(self, log, git_repo):
        """bitbucket_file on a path that does not exist raises ToolError server-side,
        which arrives as isError=true with no structuredContent at all - before this
        was checked, call() returned ok({}), and a missing file read as an empty one."""
        with McpClientSession([spec()], log) as session:
            result = session.call(
                "tto-bitbucket", "bitbucket_file",
                {"repo": str(git_repo), "path": "does-not-exist.py"},
            )

        assert not result.ok
        assert result.code is ErrorCode.FAILED_INTERNAL
        assert "does-not-exist.py" in result.message or "path" in result.message.lower()

    def test_an_unknown_tool_is_a_protocol_level_error(self, log, git_repo):
        with McpClientSession([spec()], log) as session:
            result = session.call("tto-bitbucket", "not_a_real_tool", {})

        assert not result.ok
        assert result.code is ErrorCode.FAILED_MCP_UNREACHABLE

    def test_a_real_change_between_two_commits_round_trips_through_the_envelope(self, log, git_repo):
        """The exact shape ChangeDetector now depends on: changes() reads
        result.value["changes"], a list of {"status", "file"} - proven here against
        the real server's actual bitbucket_changes output, not an assumption of it."""
        with McpClientSession([spec()], log) as session:
            repos = session.call("tto-bitbucket", "bitbucket_repos", {"root": str(git_repo.parent)})
            assert repos.ok
            head1 = repos.value["repos"][0]["head_sha"]

            (git_repo / "a.py").write_text("x = 2\n")
            subprocess.run(["git", "add", "a.py"], cwd=git_repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "PAY-2 change"], cwd=git_repo, check=True)

            changes = session.call(
                "tto-bitbucket", "bitbucket_changes",
                {"repo": str(git_repo), "base": head1, "head": "HEAD"},
            )

        assert changes.ok, getattr(changes, "message", "")
        assert changes.value["changes"] == [{"status": "M", "file": "a.py"}]


class TestSessionLifecycle:
    def test_is_available_before_and_after_close(self, log, git_repo):
        session = McpClientSession([spec()], log)
        session.__enter__()
        try:
            assert session.is_available("tto-bitbucket")
        finally:
            session.close()
        assert not session.is_available("tto-bitbucket")
