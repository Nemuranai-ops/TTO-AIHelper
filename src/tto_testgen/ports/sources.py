"""P2 SourcePorts - external artefact retrieval contracts.

Every protocol here is read-only, and that is enforced structurally: there is no
write method to call. C-05, C-06 and NFR-SEC-14 therefore cannot be violated by a
component that forgets the rule, because the capability does not exist.

That is the strongest available form of the control. A policy can be forgotten, a
review can miss a line, a test can be deleted. A method that is not there cannot
be invoked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """A normalised external artefact with its provenance."""

    source_identifier: str
    kind: str
    content: str
    metadata: dict[str, object] = field(default_factory=dict)
    detail_level: str = "full"


@runtime_checkable
class JiraSource(Protocol):
    def get_issue(self, key: str) -> SourceRecord: ...
    def search(self, jql: str, *, cursor: str | None = None) -> tuple[list[SourceRecord], str | None]: ...
    def updated_since(self, since: datetime, project: str) -> list[SourceRecord]: ...


@runtime_checkable
class ConfluenceSource(Protocol):
    def get_page(self, page_id: str | None = None, *, title: str | None = None,
                 space_key: str | None = None) -> SourceRecord: ...
    def search(self, cql: str) -> list[SourceRecord]: ...


@dataclass(frozen=True, slots=True)
class RepoInfo:
    slug: str
    project_key: str
    branch: str
    head_commit: str
    browse_url: str = ""


@runtime_checkable
class BitbucketSource(Protocol):
    def repos(self) -> list[RepoInfo]: ...
    def endpoints(self, repo_slug: str) -> list[SourceRecord]: ...
    def file(self, repo_slug: str, path: str, ref: str) -> SourceRecord: ...
    def grep(self, repo_slug: str, pattern: str, ref: str) -> list[SourceRecord]: ...
    def log(self, repo_slug: str, *, path: str | None = None,
            since: datetime | None = None) -> list[SourceRecord]: ...
    def changes(self, repo_slug: str, base: str, head: str) -> list[SourceRecord]: ...


@runtime_checkable
class DesignAssetSource(Protocol):
    def screenshots(self) -> list[SourceRecord]: ...
    def unassociated(self) -> list[str]: ...


@runtime_checkable
class ResourceManifestSource(Protocol):
    def parse(self) -> tuple[list[SourceRecord], list[str]]:
        """Returns (classified entries, unclassifiable raw refs).

        Unclassifiable entries are returned rather than dropped: a link the system
        cannot type is reported, never guessed at (FR-ING-02).
        """
        ...
