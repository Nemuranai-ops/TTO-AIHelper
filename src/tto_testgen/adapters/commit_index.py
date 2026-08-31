"""L8 CommitIndex - commit history, fetched once per file, bounded.

BR-U3-7.3 and P-U3-01. Scoped to one requirement batch: every requirement in a batch
draws on the same files, so the batch is the natural boundary. A longer-lived index
would serve history that changed since it was built, and there is no event to
invalidate it on - the repository moves independently of the run.

Bounded because the unbounded version fails on the repository that most needs it. A
large monorepo with deep history would hold the whole thing in memory. A gap saying
"commit index limit reached" is honest; a run that crawls and then succeeds is not.

Requirements: U3-NFR-PRF-05, U3-NFR-IDX-01 to -04.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from tto_testgen.domain.traceability import CommitRecord
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import Err

DEFAULT_MAX_FILES = 200
DEFAULT_MAX_COMMITS = 500
DEFAULT_LOOKBACK_DAYS = 180


@dataclass(frozen=True, slots=True)
class IndexBounds:
    max_files: int = DEFAULT_MAX_FILES
    max_commits_per_file: int = DEFAULT_MAX_COMMITS
    lookback_days: int = DEFAULT_LOOKBACK_DAYS


@dataclass(slots=True)
class BoundsReport:
    files_indexed: int = 0
    file_limit_reached: bool = False
    truncated_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    unreachable_files: list[str] = field(default_factory=list)

    @property
    def guidance(self) -> str:
        parts = []
        if self.file_limit_reached:
            parts.append(
                f"{len(self.skipped_files)} file(s) were not indexed because the "
                f"file limit was reached. Their behaviours route to gaps; raise "
                f"TAAS_COMMIT_INDEX_MAX_FILES or narrow the batch."
            )
        if self.truncated_files:
            parts.append(
                f"{len(self.truncated_files)} file(s) had history truncated. Key "
                f"derivation used the most recent commits only."
            )
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_indexed": self.files_indexed,
            "file_limit_reached": self.file_limit_reached,
            # Kept apart because they produce different gaps: a truncated file may
            # still have yielded a key from recent history, whereas a skipped file
            # yielded nothing for a reason unrelated to the repository's Jira
            # discipline. The operator's response to each differs.
            "truncated_files": self.truncated_files,
            "skipped_files": self.skipped_files,
            "unreachable_files": self.unreachable_files,
            "guidance": self.guidance,
        }


class CommitIndex:
    """Per-file commit history for the duration of one batch."""

    __slots__ = ("_source", "_repo_slug", "_bounds", "_logger", "_cache", "_report", "_now")

    def __init__(
        self,
        source: Any,
        repo_slug: str,
        logger: Logger,
        *,
        bounds: IndexBounds | None = None,
        now: datetime | None = None,
    ) -> None:
        self._source = source
        self._repo_slug = repo_slug
        self._bounds = bounds or IndexBounds()
        self._logger = logger
        self._cache: dict[str, list[CommitRecord]] = {}
        self._report = BoundsReport()
        self._now = now or datetime.now(timezone.utc)

    def __enter__(self) -> "CommitIndex":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._cache.clear()
        return False

    @property
    def report(self) -> BoundsReport:
        return self._report

    def commits_for(self, file_path: str) -> list[CommitRecord]:
        """Fetch once per file. Returns empty when a bound or a failure prevents it.

        Empty is not "no commits" - the caller distinguishes them through the report,
        because a file with no keyed commits and a file never fetched are different
        facts and route to different gaps.
        """
        if file_path in self._cache:
            return self._cache[file_path]

        if len(self._cache) >= self._bounds.max_files:
            if file_path not in self._report.skipped_files:
                self._report.file_limit_reached = True
                self._report.skipped_files.append(file_path)
                self._logger.warning(
                    "commit index file limit reached",
                    limit=self._bounds.max_files, skipped=file_path,
                )
            return []

        since = self._now - timedelta(days=self._bounds.lookback_days)
        outcome = self._source.log(self._repo_slug, path=file_path, since=since)

        if isinstance(outcome, Err):
            self._report.unreachable_files.append(file_path)
            self._logger.warning(
                "commit history unavailable", path=file_path, code=outcome.code.value
            )
            self._cache[file_path] = []
            return []

        commits = list(outcome.value)
        if len(commits) > self._bounds.max_commits_per_file:
            # Most recent first: truncation keeps the commits BR-3 actually selects
            # from, since it prefers recency.
            commits.sort(key=lambda c: c.committed_at, reverse=True)
            commits = commits[: self._bounds.max_commits_per_file]
            self._report.truncated_files.append(file_path)

        self._cache[file_path] = commits
        self._report.files_indexed = len(self._cache)
        return commits

    def was_skipped(self, file_path: str) -> bool:
        return file_path in self._report.skipped_files

    def was_unreachable(self, file_path: str) -> bool:
        return file_path in self._report.unreachable_files
