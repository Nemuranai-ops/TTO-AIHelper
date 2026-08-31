"""L17 ChangeDetector's Bitbucket path.

Never exercised before this: ChangeDetector was constructed exactly once in the whole
codebase (composition.py, with bitbucket=None), so nothing here had ever run against a
source that returns data. `_detect_bitbucket` called a `.head()` method no adapter has,
and read `.identifier` off a `SourceRecord` that only has `.source_identifier` - both
would have raised on the first real call. These tests exercise the fixed contract:
`BitbucketSourceAdapter` is Result-based, so the stub here is too, matching how
CommitIndex's own StubBitbucket (test_commit_index.py) already stubs the real adapter.
"""

from __future__ import annotations

from tto_testgen.adapters.change_detector import ChangeDetector, DeltaBaseline, _kind_for_status
from tto_testgen.platform.logging import configure
from tto_testgen.platform.result import ErrorCode, err, ok
from tto_testgen.ports.sources import RepoInfo

import pytest


@pytest.fixture
def log():
    return configure("CRITICAL")


class StubBitbucket:
    def __init__(self, repos=None, changes=None, repos_fail=False, fail_changes_for=()):
        self.repos_list = repos or []
        self.changes_by_slug = changes or {}
        self.repos_fail = repos_fail
        self.fail_changes_for = set(fail_changes_for)
        self.changes_calls: list[str] = []

    def repos(self):
        if self.repos_fail:
            return err(ErrorCode.FAILED_MCP_UNREACHABLE, "bitbucket_repos unreachable")
        return ok(list(self.repos_list))

    def changes(self, repo_slug, base, head):
        self.changes_calls.append(repo_slug)
        if repo_slug in self.fail_changes_for:
            return err(ErrorCode.FAILED_MCP_UNREACHABLE, f"{repo_slug} unreachable")
        return ok(self.changes_by_slug.get(repo_slug, []))


def repo(slug, head):
    return RepoInfo(slug=slug, project_key="PAY", branch="main", head_commit=head)


class TestKindMapping:
    @pytest.mark.parametrize("status,expected", [
        ("A", "added"), ("D", "removed"), ("M", "modified"),
        ("R100", "modified"), ("C100", "modified"), ("T", "modified"), ("", "modified"),
    ])
    def test_git_status_codes_map_to_the_three_kinds(self, status, expected):
        assert _kind_for_status(status) == expected


class TestNoBitbucket:
    def test_a_none_source_reports_nothing_and_raises_nothing(self, log):
        detector = ChangeDetector(None, None, log)
        baseline = DeltaBaseline(run_id=1, ended_at="2026-08-30T00:00:00Z")
        result = detector.detect(baseline)
        assert result.changes == []
        assert result.unavailable_sources == []


class TestRepoDiscovery:
    def test_unreachable_repos_call_reports_one_bitbucket_failure(self, log):
        bitbucket = StubBitbucket(repos_fail=True)
        detector = ChangeDetector(bitbucket, None, log)
        baseline = DeltaBaseline(run_id=1, ended_at="2026-08-30T00:00:00Z")

        result = detector.detect(baseline)

        assert result.unavailable_sources == [("bitbucket", "bitbucket_repos unreachable")]
        assert result.changes == []

    def test_every_known_repo_is_checked_when_none_are_named_explicitly(self, log):
        bitbucket = StubBitbucket(
            repos=[repo("orders", "h2"), repo("checkout", "h9")],
            changes={"orders": [("M", "a.py")], "checkout": [("A", "b.py")]},
        )
        detector = ChangeDetector(bitbucket, None, log)
        baseline = DeltaBaseline(
            run_id=1, ended_at="2026-08-30T00:00:00Z",
            head_commits={"orders": "h1", "checkout": "h8"},
        )

        result = detector.detect(baseline)

        assert sorted(bitbucket.changes_calls) == ["checkout", "orders"]
        assert {c.ref for c in result.changes} == {"a.py", "b.py"}
        assert result.head_commits == {"orders": "h2", "checkout": "h9"}

    def test_an_explicit_repo_slugs_list_narrows_which_repos_are_checked(self, log):
        bitbucket = StubBitbucket(
            repos=[repo("orders", "h2"), repo("checkout", "h9")],
            changes={"orders": [("M", "a.py")], "checkout": [("A", "b.py")]},
        )
        detector = ChangeDetector(bitbucket, None, log, repo_slugs=["orders"])
        baseline = DeltaBaseline(
            run_id=1, ended_at="2026-08-30T00:00:00Z",
            head_commits={"orders": "h1", "checkout": "h8"},
        )

        result = detector.detect(baseline)

        assert bitbucket.changes_calls == ["orders"]
        assert result.head_commits == {"orders": "h2"}

    def test_an_unknown_named_repo_is_reported_unavailable_not_a_crash(self, log):
        bitbucket = StubBitbucket(repos=[repo("orders", "h2")])
        detector = ChangeDetector(bitbucket, None, log, repo_slugs=["ghost"])
        baseline = DeltaBaseline(run_id=1, ended_at="2026-08-30T00:00:00Z")

        result = detector.detect(baseline)

        assert result.unavailable_sources == [
            ("bitbucket:ghost", "ghost: not among the repositories bitbucket_repos reported")
        ]


class TestChangeDetection:
    def test_no_baseline_head_for_a_repo_skips_the_comparison(self, log):
        """A repo seen for the first time has nothing to diff against yet - its head is
        recorded so a *future* run can compare, but .changes() is never called now."""
        bitbucket = StubBitbucket(repos=[repo("orders", "h2")])
        detector = ChangeDetector(bitbucket, None, log)
        baseline = DeltaBaseline(run_id=1, ended_at="2026-08-30T00:00:00Z")

        result = detector.detect(baseline)

        assert bitbucket.changes_calls == []
        assert result.head_commits == {"orders": "h2"}
        assert result.changes == []

    def test_an_unchanged_head_skips_the_comparison(self, log):
        bitbucket = StubBitbucket(repos=[repo("orders", "h1")])
        detector = ChangeDetector(bitbucket, None, log)
        baseline = DeltaBaseline(
            run_id=1, ended_at="2026-08-30T00:00:00Z", head_commits={"orders": "h1"}
        )

        result = detector.detect(baseline)

        assert bitbucket.changes_calls == []
        assert result.changes == []

    def test_changes_are_mapped_to_changed_refs_with_the_right_kind(self, log):
        bitbucket = StubBitbucket(
            repos=[repo("orders", "h2")],
            changes={"orders": [("M", "a.py"), ("A", "b.py"), ("D", "c.py")]},
        )
        detector = ChangeDetector(bitbucket, None, log)
        baseline = DeltaBaseline(
            run_id=1, ended_at="2026-08-30T00:00:00Z", head_commits={"orders": "h1"}
        )

        result = detector.detect(baseline)

        by_ref = {c.ref: c.kind for c in result.changes}
        assert by_ref == {"a.py": "modified", "b.py": "added", "c.py": "removed"}
        assert all(c.source == "bitbucket" for c in result.changes)

    def test_one_repos_changes_failure_does_not_lose_the_others(self, log):
        bitbucket = StubBitbucket(
            repos=[repo("orders", "h2"), repo("checkout", "h9")],
            changes={"checkout": [("M", "b.py")]},
            fail_changes_for=["orders"],
        )
        detector = ChangeDetector(bitbucket, None, log)
        baseline = DeltaBaseline(
            run_id=1, ended_at="2026-08-30T00:00:00Z",
            head_commits={"orders": "h1", "checkout": "h8"},
        )

        result = detector.detect(baseline)

        assert {c.ref for c in result.changes} == {"b.py"}
        assert result.unavailable_sources == [("bitbucket:orders", "orders unreachable")]
        # The failed repo's head is not advanced - only checkout's is.
        assert result.head_commits == {"checkout": "h9"}
