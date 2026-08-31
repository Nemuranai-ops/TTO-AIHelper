"""L17 ChangeDetector - what changed since the baseline, and what could not be reached.

Two sources, detected independently under U1's isolation. The result carries both the
changes found **and the sources that did not answer**, because P-U8-01's guard depends
on knowing which - and if that fact lived only in a log, the guard would have to infer
it from an empty change list, which is ambiguous: no changes and no connection look
identical from outside.

Read-only against both sources, structurally: P2's source protocols declare no write
method, so C-05 and C-06 hold because the capability is absent (U8-NFR-SEC-04).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from tto_testgen.domain.impact import ChangedRef
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.resilience import isolate
from tto_testgen.platform.result import Result, ok


@dataclass(slots=True)
class DeltaBaseline:
    """What the last completed run saw. None when no run has completed."""

    run_id: int
    ended_at: str
    head_commits: dict[str, str] = field(default_factory=dict)
    jira_watermark: str | None = None


@dataclass(slots=True)
class DetectionResult:
    changes: list[ChangedRef] = field(default_factory=list)
    head_commits: dict[str, str] = field(default_factory=dict)
    jira_watermark: str | None = None
    #: (source, reason) per source that did not answer. A field rather than a log
    #: line, because the baseline guard reads it as a fact.
    unavailable_sources: list[tuple[str, str]] = field(default_factory=list)
    truncated: bool = False

    @property
    def complete(self) -> bool:
        return not self.unavailable_sources

    def to_dict(self) -> dict[str, Any]:
        return {
            "changes": len(self.changes),
            "head_commits": dict(sorted(self.head_commits.items())),
            "jira_watermark": self.jira_watermark,
            "unavailable_sources": [
                {"source": s, "reason": r} for s, r in self.unavailable_sources
            ],
            "complete": self.complete,
            "truncated": self.truncated,
        }


class ChangeDetector:
    """Per-source detection. Decides nothing about what the changes mean."""

    def __init__(
        self,
        bitbucket: Any,
        jira: Any,
        logger: Logger,
        *,
        repo_slugs: Sequence[str] = (),
        max_changes: int = 500,
    ) -> None:
        self._bitbucket = bitbucket
        self._jira = jira
        self._logger = logger
        self._repo_slugs = tuple(repo_slugs)
        self._max_changes = max_changes

    def detect(self, baseline: DeltaBaseline) -> DetectionResult:
        result = DetectionResult()
        self._detect_bitbucket(baseline, result)
        self._detect_jira(baseline, result)

        if len(result.changes) > self._max_changes:
            # Reported, never silently truncated - the same rule as U3's commit
            # index bounds. A run that processed the first 500 of 900 and said
            # nothing would look complete.
            result.changes = result.changes[: self._max_changes]
            result.truncated = True
        return result

    def _detect_bitbucket(self, baseline: DeltaBaseline, result: DetectionResult) -> None:
        """One repository per isolated item, so one outage does not lose the rest."""
        if self._bitbucket is None or not self._repo_slugs:
            return

        def for_repo(slug: str) -> Result[tuple[str, str, list[ChangedRef]]]:
            head = self._bitbucket.head(slug)
            base = baseline.head_commits.get(slug)
            found: list[ChangedRef] = []
            if base and base != head:
                for record in self._bitbucket.changes(slug, base, head):
                    found.append(
                        ChangedRef(
                            ref=record.identifier,
                            source="bitbucket",
                            kind=str(getattr(record, "kind", "modified")),
                        )
                    )
            return ok((slug, head, found))

        outcome = isolate(self._repo_slugs, for_repo, self._logger)
        for _, value in outcome.succeeded:
            slug, head, found = value
            result.changes += found
            # Recorded only for a repository that answered. A source that failed
            # contributes no head commit, so the guard cannot advance on a value it
            # never confirmed (PBT-U8-12).
            result.head_commits[slug] = head
        for slug, failure in outcome.failed:
            result.unavailable_sources.append(
                (f"bitbucket:{slug}", getattr(failure, "message", "unreachable"))
            )

    def _detect_jira(self, baseline: DeltaBaseline, result: DetectionResult) -> None:
        if self._jira is None:
            return

        def fetch(_: str) -> Result[tuple[list[ChangedRef], str | None]]:
            found: list[ChangedRef] = []
            watermark = baseline.jira_watermark
            for issue in self._jira.updated_since(baseline.jira_watermark):
                found.append(
                    ChangedRef(ref=issue.identifier, source="jira", kind="modified")
                )
                updated = str(getattr(issue, "updated_at", "") or "")
                if updated and (watermark is None or updated > watermark):
                    watermark = updated
            return ok((found, watermark))

        outcome = isolate(["jira"], fetch, self._logger)
        for _, value in outcome.succeeded:
            found, watermark = value
            result.changes += found
            result.jira_watermark = watermark
        for _, failure in outcome.failed:
            result.unavailable_sources.append(
                ("jira", getattr(failure, "message", "unreachable"))
            )
