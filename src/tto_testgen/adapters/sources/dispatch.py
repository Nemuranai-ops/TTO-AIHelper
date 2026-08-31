"""A8 SourceDispatch - source_for(type).fetch(resource), completing U2's approved
design (business-logic-model.md §2.2: `source_for(entry.type).fetch(entry)`).

Classification (`manifest.py`) decides *what kind* a resource is. This decides *how
to fetch one of that kind* - which needs its own extraction from the raw reference,
because the classification patterns exist to detect a type, not to capture an
identifier out of it: rule 4's Confluence pattern, for instance, has no capture
group at all.

Requirements: FR-ING-01 to FR-ING-10. Pattern: matches the shape IngestionService
already expects, from `aidlc-docs/construction/u2-ingestion-analysis/functional-
design/business-logic-model.md`.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from tto_testgen.adapters.paging import PagedResult
from tto_testgen.adapters.sources.design_assets import DesignAssetAdapter
from tto_testgen.adapters.sources.manifest import ClassifiedResource
from tto_testgen.domain.model import ResourceType
from tto_testgen.platform.result import ErrorCode, Result, err, ok
from tto_testgen.ports.sources import SourceRecord

_JIRA_KEY = re.compile(r"([A-Z][A-Z0-9]{1,9}-\d+)")
_JQL_PARAM = re.compile(r"[?&]jql=([^&]+)")
_CONFLUENCE_PAGE_ID = re.compile(r"/pages/(\d+)|[?&]pageId=(\d+)")
_CONFLUENCE_SPACE = re.compile(r"/wiki/spaces/([^/]+)")
_BITBUCKET_PROJECT_REPO = re.compile(r"/projects/[^/]+/repos/([^/]+)")
_BITBUCKET_OWNER_REPO = re.compile(r"bitbucket[^/]*/[^/]+/([^/]+)")


def _extraction_failure(raw_ref: str, looking_for: str) -> Result[Any]:
    return err(
        ErrorCode.FAILED_INTERNAL,
        f"could not find {looking_for} in {raw_ref!r}",
        remediation="Check the link in resources.md matches the documented pattern.",
    )


@dataclass(slots=True)
class JiraIssueFetcher:
    """Rule 1 (browse/REST URL) or rule 2 (bare key) - both contain a literal key."""

    atlassian: Any

    def fetch(self, resource: ClassifiedResource) -> Result[list[SourceRecord]]:
        match = _JIRA_KEY.search(resource.raw_ref)
        if not match:
            return _extraction_failure(resource.raw_ref, "a Jira key")
        result = self.atlassian.get_issue(match.group(1))
        return result if not result.ok else ok([result.value])


@dataclass(slots=True)
class JiraQueryFetcher:
    """A `jql=` URL parameter, or the raw ref itself is already a bare JQL string."""

    atlassian: Any

    def fetch(self, resource: ClassifiedResource) -> Result[PagedResult]:
        match = _JQL_PARAM.search(resource.raw_ref)
        jql = urllib.parse.unquote_plus(match.group(1)) if match else resource.raw_ref
        return self.atlassian.search(jql)


@dataclass(slots=True)
class ConfluencePageFetcher:
    atlassian: Any

    def fetch(self, resource: ClassifiedResource) -> Result[list[SourceRecord]]:
        match = _CONFLUENCE_PAGE_ID.search(resource.raw_ref)
        if not match:
            return _extraction_failure(resource.raw_ref, "a page id")
        page_id = match.group(1) or match.group(2)
        result = self.atlassian.get_page(page_id=page_id)
        return result if not result.ok else ok([result.value])


@dataclass(slots=True)
class ConfluenceSpaceFetcher:
    """A whole space - every page in it. CQL scoped by space rather than a page id."""

    atlassian: Any

    def fetch(self, resource: ClassifiedResource) -> Result[PagedResult]:
        match = _CONFLUENCE_SPACE.search(resource.raw_ref)
        if not match:
            return _extraction_failure(resource.raw_ref, "a space key")
        space_key = match.group(1)
        return self.atlassian.search_pages(f'space = "{space_key}" AND type = page')


@dataclass(slots=True)
class BitbucketRepoFetcher:
    """Confirms the repository is one tt-bitbucket-mcp can actually read.

    A resources.md entry naming a repository the server cannot see is exactly the
    kind of mismatch worth catching here rather than three stages later, when
    api_model_derive fails against a slug nobody checked existed.
    """

    bitbucket: Any

    def fetch(self, resource: ClassifiedResource) -> Result[list[SourceRecord]]:
        match = (
            _BITBUCKET_PROJECT_REPO.search(resource.raw_ref)
            or _BITBUCKET_OWNER_REPO.search(resource.raw_ref)
        )
        if not match:
            return _extraction_failure(resource.raw_ref, "a repository slug")
        slug = match.group(1)

        result = self.bitbucket.repos()
        if not result.ok:
            return result
        found = next((r for r in result.value if r.slug == slug), None)
        if found is None:
            return err(
                ErrorCode.FAILED_INTERNAL,
                f"{slug!r} is not among the repositories tt-bitbucket-mcp can read",
                remediation=(
                    "Check BITBUCKET_REPO_ROOT in src/tt-bitbucket-mcp's own .env - "
                    "it only sees clones already on disk under that path."
                ),
            )
        record = SourceRecord(
            source_identifier=found.slug,
            kind="bitbucket-repo",
            content=f"branch={found.branch} head={found.head_commit}",
            metadata={"project_key": found.project_key, "browse_url": found.browse_url},
        )
        return ok([record])


@dataclass(slots=True)
class DesignFolderFetcher:
    """The Figma screenshot folder. BR-U2-4."""

    workspace_root: Path

    def fetch(self, resource: ClassifiedResource) -> Result[PagedResult]:
        folder = Path(resource.raw_ref)
        if not folder.is_absolute():
            folder = self.workspace_root / folder

        result = DesignAssetAdapter(folder).screenshots()
        if not result.ok:
            return result
        parse = result.value

        records = [
            SourceRecord(
                source_identifier=asset.filename,
                kind="screenshot",
                # The image bytes never pass through this string - only their hash
                # does (asset.content_hash) - so content_hash() downstream changes
                # if and only if the mapping OR the underlying image actually
                # changed, which is BR-U2-3.1's rule applied correctly to a binary
                # file rather than skipped for one.
                content=(
                    f"feature={asset.feature} screen={asset.screen} "
                    f"state={asset.state} route={asset.route or ''} "
                    f"jira_key={asset.jira_key or ''} image={asset.content_hash}"
                ),
                metadata={
                    "feature": asset.feature, "screen": asset.screen,
                    "state": asset.state, "route": asset.route,
                    "jira_key": asset.jira_key, "origin": asset.origin,
                },
            )
            for asset in parse.associated
        ]

        # Unassociated files are reported, never guessed at or dropped (BR-U2-4.3).
        # There is no dedicated slot for a sub-resource notice in the ingestion
        # report, so it rides the same guidance channel every other resource's
        # ceiling notice already surfaces through.
        guidance = ""
        if parse.unassociated:
            shown = ", ".join(parse.unassociated[:5])
            more = (
                f" and {len(parse.unassociated) - 5} more"
                if len(parse.unassociated) > 5 else ""
            )
            guidance = (
                f"{len(parse.unassociated)} file(s) not associated with a "
                f"feature/screen: {shown}{more}"
            )

        return ok(PagedResult(records=records, guidance=guidance))


def build_source_for(
    atlassian: Any, bitbucket: Any, workspace_root: Path
) -> Callable[[ResourceType], Any]:
    """`source_for` from the approved design. Returns None for a type with no
    fetcher, which IngestionService already turns into a clear "no adapter for
    this type" error - the existing, designed fallback rather than a new one.

    OpenAPI specs are deliberately absent: this system has no generic HTTP
    fetcher, and FR-ING-06 already routes them through `api_model_derive` against
    a Bitbucket repository. A spec declared standalone in resources.md gets that
    same honest fallback rather than a fetch this system was never built to make.
    """
    table: dict[ResourceType, Any] = {
        ResourceType.JIRA_ISSUE: JiraIssueFetcher(atlassian),
        ResourceType.JIRA_QUERY: JiraQueryFetcher(atlassian),
        ResourceType.CONFLUENCE_PAGE: ConfluencePageFetcher(atlassian),
        ResourceType.CONFLUENCE_SPACE: ConfluenceSpaceFetcher(atlassian),
        ResourceType.BITBUCKET_REPO: BitbucketRepoFetcher(bitbucket),
        ResourceType.DESIGN_FOLDER: DesignFolderFetcher(workspace_root),
    }

    def source_for(resource_type: ResourceType) -> Any:
        return table.get(resource_type)

    return source_for
