"""L8 CommitIndex. Requirements: U3-NFR-PRF-05, U3-NFR-IDX-01 to -04."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tto_testgen.adapters.commit_index import CommitIndex, IndexBounds
from tto_testgen.domain.traceability import CommitRecord
from tto_testgen.platform.logging import configure
from tto_testgen.platform.result import ErrorCode, err, ok

NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)


class StubBitbucket:
    def __init__(self, per_file=None, fail_for=None):
        self.per_file = per_file or {}
        self.fail_for = fail_for or set()
        self.calls: list[str] = []

    def log(self, repo_slug, *, path=None, since=None):
        self.calls.append(path)
        if path in self.fail_for:
            return err(ErrorCode.FAILED_MCP_UNREACHABLE, "repository unreachable")
        count = self.per_file.get(path, 3)
        return ok([
            CommitRecord(
                sha=f"{path}-{i}", message=f"PAY-{i} change",
                committed_at=NOW - timedelta(days=i), lines_changed=i,
            )
            for i in range(count)
        ])


@pytest.fixture
def log():
    return configure("CRITICAL")


class TestCaching:
    def test_history_is_fetched_once_per_file(self, log):
        # At 500 requirements over 50 files, per-requirement fetching would make 490
        # redundant calls.
        source = StubBitbucket()
        with CommitIndex(source, "orders", log, now=NOW) as index:
            for _ in range(10):
                index.commits_for("src/pay.py")
        assert source.calls == ["src/pay.py"]

    def test_distinct_files_are_fetched_separately(self, log):
        source = StubBitbucket()
        with CommitIndex(source, "orders", log, now=NOW) as index:
            index.commits_for("a.py")
            index.commits_for("b.py")
        assert source.calls == ["a.py", "b.py"]

    def test_the_cache_is_discarded_on_exit(self, log):
        source = StubBitbucket()
        index = CommitIndex(source, "orders", log, now=NOW)
        with index:
            index.commits_for("a.py")
        # A longer-lived index would serve history that changed since it was built,
        # and there is no event to invalidate it on.
        assert index._cache == {}


class TestFileBound:
    def test_files_beyond_the_limit_are_skipped_and_reported(self, log):
        source = StubBitbucket()
        with CommitIndex(source, "orders", log, bounds=IndexBounds(max_files=2),
                         now=NOW) as index:
            index.commits_for("a.py")
            index.commits_for("b.py")
            assert index.commits_for("c.py") == []
        assert index.report.file_limit_reached
        assert index.report.skipped_files == ["c.py"]

    def test_a_skipped_file_is_not_fetched(self, log):
        source = StubBitbucket()
        with CommitIndex(source, "orders", log, bounds=IndexBounds(max_files=1),
                         now=NOW) as index:
            index.commits_for("a.py")
            index.commits_for("b.py")
        assert source.calls == ["a.py"]

    def test_guidance_names_the_setting(self, log):
        with CommitIndex(StubBitbucket(), "orders", log,
                         bounds=IndexBounds(max_files=1), now=NOW) as index:
            index.commits_for("a.py")
            index.commits_for("b.py")
        assert "TAAS_COMMIT_INDEX_MAX_FILES" in index.report.guidance


class TestCommitBound:
    def test_history_is_truncated_and_reported(self, log):
        source = StubBitbucket(per_file={"big.py": 40})
        with CommitIndex(source, "orders", log,
                         bounds=IndexBounds(max_commits_per_file=10), now=NOW) as index:
            commits = index.commits_for("big.py")
        assert len(commits) == 10
        assert index.report.truncated_files == ["big.py"]

    def test_truncation_keeps_the_most_recent(self, log):
        # BR-3 prefers recency, so truncation must keep the commits it selects from.
        source = StubBitbucket(per_file={"big.py": 40})
        with CommitIndex(source, "orders", log,
                         bounds=IndexBounds(max_commits_per_file=5), now=NOW) as index:
            commits = index.commits_for("big.py")
        assert commits[0].committed_at > commits[-1].committed_at
        assert commits[0].committed_at == max(c.committed_at for c in commits)


class TestSeparateFailureModes:
    """Truncated, skipped and unreachable are three different facts."""

    def test_unreachable_is_distinct_from_skipped(self, log):
        source = StubBitbucket(fail_for={"gone.py"})
        with CommitIndex(source, "orders", log, now=NOW) as index:
            assert index.commits_for("gone.py") == []
        assert index.report.unreachable_files == ["gone.py"]
        assert index.report.skipped_files == []
        assert index.was_unreachable("gone.py")
        assert not index.was_skipped("gone.py")

    def test_a_truncated_file_still_yields_commits(self, log):
        source = StubBitbucket(per_file={"big.py": 40})
        with CommitIndex(source, "orders", log,
                         bounds=IndexBounds(max_commits_per_file=5), now=NOW) as index:
            assert index.commits_for("big.py")
        # A truncated file may still have yielded a key; a skipped one yielded
        # nothing for an unrelated reason.
        assert index.report.truncated_files and not index.report.skipped_files

    def test_an_unreachable_file_is_not_refetched(self, log):
        source = StubBitbucket(fail_for={"gone.py"})
        with CommitIndex(source, "orders", log, now=NOW) as index:
            index.commits_for("gone.py")
            index.commits_for("gone.py")
        assert source.calls == ["gone.py"]

    def test_report_is_serialisable_and_keeps_the_three_apart(self, log):
        with CommitIndex(StubBitbucket(), "orders", log, now=NOW) as index:
            index.commits_for("a.py")
        payload = index.report.to_dict()
        assert set(payload) >= {"truncated_files", "skipped_files", "unreachable_files"}


class TestLookback:
    def test_the_since_argument_uses_the_configured_window(self, log):
        class Recording(StubBitbucket):
            def __init__(self):
                super().__init__()
                self.since = None

            def log(self, repo_slug, *, path=None, since=None):
                self.since = since
                return super().log(repo_slug, path=path, since=since)

        source = Recording()
        with CommitIndex(source, "orders", log,
                         bounds=IndexBounds(lookback_days=90), now=NOW) as index:
            index.commits_for("a.py")
        assert source.since == NOW - timedelta(days=90)
