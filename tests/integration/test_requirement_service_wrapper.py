"""_RequirementServiceWithLiveBitbucket - the same fix pattern as U2's
run_ingestion, applied to U3's commit-derived Jira keys (US-TRC-02).

TestableRequirementService's own commit-derivation logic is already covered by
test_u3_services.py's StubBitbucket tests. What is new here, and what actually
had no coverage before this fix, is the *dispatch*: does a call with no repo_slug
stay on the fast, session-free path, and does a call that names one actually open
a live session for just that call.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tto_testgen.composition import _RequirementServiceWithLiveBitbucket
from tto_testgen.platform.logging import configure


@dataclass
class _RecordingSession:
    """Stands in for McpClientSession, recording whether it was ever opened."""

    opened: list[bool] = field(default_factory=list)
    closed: list[bool] = field(default_factory=list)

    def __enter__(self):
        self.opened.append(True)
        return self

    def __exit__(self, *exc):
        self.closed.append(True)
        return False

    def is_available(self, server):
        return True

    def call(self, server, tool, arguments):
        from tto_testgen.platform.result import ok

        if tool == "bitbucket_log":
            return ok({"commits": []})
        return ok({})


def test_a_call_with_no_repo_slug_never_opens_a_session(conn, seeded, monkeypatch):
    """The common case: a direct Jira link. This must stay exactly as fast as it
    already was - no subprocess, no session."""
    from tto_testgen.adapters.sqlite.repositories import unit_of_work

    opened = []
    monkeypatch.setattr(
        "tto_testgen.adapters.mcp_client.McpClientSession",
        lambda *a, **k: opened.append(True) or (_ for _ in ()).throw(
            AssertionError("a session must not be opened when repo_slug is absent")
        ),
    )
    wrapper = _RequirementServiceWithLiveBitbucket(
        lambda: unit_of_work(conn), config=None, logger=configure("CRITICAL"),
    )
    result = wrapper.upsert_requirements("checkout", {"requirements": []})
    assert opened == []
    assert result.ok


def test_a_call_with_a_repo_slug_opens_and_closes_exactly_one_session(conn, seeded, monkeypatch):
    from tto_testgen.adapters.sqlite.repositories import unit_of_work

    recorder = _RecordingSession()
    monkeypatch.setattr(
        "tto_testgen.adapters.mcp_client.McpClientSession", lambda *a, **k: recorder
    )
    monkeypatch.setattr(
        "tto_testgen.adapters.mcp_client.servers_from_config", lambda config: []
    )
    wrapper = _RequirementServiceWithLiveBitbucket(
        lambda: unit_of_work(conn), config=object(), logger=configure("CRITICAL"),
    )
    result = wrapper.upsert_requirements(
        "checkout", {"requirements": [], "repo_slug": "checkout-service"}
    )
    assert result.ok
    assert recorder.opened == [True]
    assert recorder.closed == [True]
