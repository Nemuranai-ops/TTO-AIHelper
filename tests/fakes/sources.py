"""In-memory sources satisfying P2. Read-only, like the protocols they implement."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from tto_testgen.ports.sources import RepoInfo, SourceRecord


@dataclass(slots=True)
class FakeJiraSource:
    issues: dict[str, SourceRecord] = field(default_factory=dict)
    fail_on: set[str] = field(default_factory=set)

    def get_issue(self, key: str) -> SourceRecord:
        if key in self.fail_on:
            raise ConnectionError(f"simulated Jira outage for {key}")
        if key not in self.issues:
            raise KeyError(key)
        return self.issues[key]

    def search(self, jql: str, *, cursor: str | None = None):
        return list(self.issues.values()), None

    def updated_since(self, since: datetime, project: str) -> list[SourceRecord]:
        return list(self.issues.values())


@dataclass(slots=True)
class FakeConfluenceSource:
    pages: dict[str, SourceRecord] = field(default_factory=dict)

    def get_page(self, page_id=None, *, title=None, space_key=None) -> SourceRecord:
        if page_id and page_id in self.pages:
            return self.pages[page_id]
        raise KeyError(page_id or title)

    def search(self, cql: str) -> list[SourceRecord]:
        return list(self.pages.values())


@dataclass(slots=True)
class FakeBitbucketSource:
    repositories: list[RepoInfo] = field(default_factory=list)
    endpoint_records: dict[str, list[SourceRecord]] = field(default_factory=dict)
    commit_records: list[SourceRecord] = field(default_factory=list)
    unreachable: set[str] = field(default_factory=set)

    def repos(self) -> list[RepoInfo]:
        return list(self.repositories)

    def endpoints(self, repo_slug: str) -> list[SourceRecord]:
        if repo_slug in self.unreachable:
            raise ConnectionError(f"simulated Bitbucket outage for {repo_slug}")
        return self.endpoint_records.get(repo_slug, [])

    def log(self, repo_slug: str, *, path=None, since=None) -> list[SourceRecord]:
        return list(self.commit_records)

    def changes(self, repo_slug: str, base: str, head: str) -> list[SourceRecord]:
        return []


@dataclass(slots=True)
class FakeDesignAssetSource:
    records: list[SourceRecord] = field(default_factory=list)
    unassociated_files: list[str] = field(default_factory=list)

    def screenshots(self) -> list[SourceRecord]:
        return list(self.records)

    def unassociated(self) -> list[str]:
        return list(self.unassociated_files)


@dataclass(slots=True)
class FakeResourceManifestSource:
    entries: list[SourceRecord] = field(default_factory=list)
    unclassifiable: list[str] = field(default_factory=list)

    def parse(self) -> tuple[list[SourceRecord], list[str]]:
        return list(self.entries), list(self.unclassifiable)
