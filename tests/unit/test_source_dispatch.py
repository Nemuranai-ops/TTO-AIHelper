"""A8 SourceDispatch - source_for(type).fetch(resource).

Tests the concrete extraction-then-call chain end to end against real
AtlassianSourceAdapter/BitbucketSourceAdapter, backed by a fake transport - not
against the fakes in tests/fakes, which satisfy the abstract port protocol
(plain values) rather than the concrete adapters' Result-wrapped shape this
module actually depends on.
"""

from __future__ import annotations

import json

import pytest

from tto_testgen.adapters.sources.atlassian import AtlassianSourceAdapter
from tto_testgen.adapters.sources.bitbucket import BitbucketSourceAdapter
from tto_testgen.adapters.sources.dispatch import (
    BitbucketRepoFetcher,
    ConfluencePageFetcher,
    ConfluenceSpaceFetcher,
    DesignFolderFetcher,
    JiraIssueFetcher,
    JiraQueryFetcher,
    build_source_for,
)
from tto_testgen.adapters.sources.manifest import ClassifiedResource
from tto_testgen.domain.model import ResourceType
from tto_testgen.platform.result import ok


class FakeSession:
    """The same stand-in test_source_adapters.py uses for L6."""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls: list[tuple[str, str, dict]] = []

    def is_available(self, server):
        return True

    def call(self, server, tool, arguments):
        self.calls.append((server, tool, arguments))
        return ok(self.responses.get(tool, {}))


def resource(raw_ref: str, rtype: ResourceType, rule=1, pattern="") -> ClassifiedResource:
    return ClassifiedResource(raw_ref, rtype, rule, pattern)


# --- Jira issue -----------------------------------------------------------------

class TestJiraIssueFetcher:
    def test_extracts_the_key_from_a_browse_url(self):
        session = FakeSession({"jira_get_issue": {
            "key": "PAY-12", "summary": "Checkout", "description": "Body",
            "comments": [],
        }})
        fetcher = JiraIssueFetcher(AtlassianSourceAdapter(session))
        result = fetcher.fetch(resource(
            "https://your-org.atlassian.net/browse/PAY-12", ResourceType.JIRA_ISSUE
        ))
        assert result.ok
        assert result.value[0].source_identifier == "PAY-12"
        assert session.calls[0] == ("tto-atlassian", "jira_get_issue", {"issue_key": "PAY-12"})

    def test_extracts_the_key_from_a_bare_reference(self):
        session = FakeSession({"jira_get_issue": {"key": "PAY-13", "summary": "s",
                                                   "description": "d", "comments": []}})
        fetcher = JiraIssueFetcher(AtlassianSourceAdapter(session))
        result = fetcher.fetch(resource("PAY-13", ResourceType.JIRA_ISSUE, rule=2))
        assert result.ok
        assert result.value[0].source_identifier == "PAY-13"

    def test_a_reference_with_no_key_fails_honestly(self):
        fetcher = JiraIssueFetcher(AtlassianSourceAdapter(FakeSession()))
        result = fetcher.fetch(resource("not-a-key-at-all", ResourceType.JIRA_ISSUE))
        assert not result.ok
        assert "Jira key" in result.message

    def test_an_upstream_failure_is_returned_not_swallowed(self):
        session = FakeSession()
        session.call = lambda *a, **k: __import__(
            "tto_testgen.platform.result", fromlist=["err", "ErrorCode"]
        ).err(
            __import__("tto_testgen.platform.result", fromlist=["ErrorCode"]).ErrorCode.FAILED_MCP_UNREACHABLE,
            "boom",
        )
        fetcher = JiraIssueFetcher(AtlassianSourceAdapter(session))
        result = fetcher.fetch(resource("PAY-12", ResourceType.JIRA_ISSUE, rule=2))
        assert not result.ok


# --- Jira query --------------------------------------------------------------------

class TestJiraQueryFetcher:
    def test_extracts_jql_from_a_url_parameter(self):
        session = FakeSession({"jira_search_issues": {"issues": [], "next_cursor": None}})
        fetcher = JiraQueryFetcher(AtlassianSourceAdapter(session))
        ref = "https://x.atlassian.net/issues/?jql=project%3DPAY+AND+labels%3D%22checkout%22"
        result = fetcher.fetch(resource(ref, ResourceType.JIRA_QUERY, rule=3))
        assert result.ok
        called_jql = session.calls[0][2]["jql"]
        assert called_jql == 'project=PAY AND labels="checkout"'

    def test_a_bare_jql_string_is_used_directly(self):
        session = FakeSession({"jira_search_issues": {"issues": [], "next_cursor": None}})
        fetcher = JiraQueryFetcher(AtlassianSourceAdapter(session))
        result = fetcher.fetch(resource(
            "project = PAY AND labels = checkout", ResourceType.JIRA_QUERY, rule=3
        ))
        assert result.ok
        assert session.calls[0][2]["jql"] == "project = PAY AND labels = checkout"


# --- Confluence -----------------------------------------------------------------------

class TestConfluencePageFetcher:
    def test_extracts_the_page_id_from_a_pages_path(self):
        session = FakeSession({"confluence_get_page": {
            "id": "123456789", "title": "Checkout Rules", "text": "rules",
        }})
        fetcher = ConfluencePageFetcher(AtlassianSourceAdapter(session))
        ref = "https://x.atlassian.net/wiki/spaces/PAY/pages/123456789/Checkout-Rules"
        result = fetcher.fetch(resource(ref, ResourceType.CONFLUENCE_PAGE, rule=4))
        assert result.ok
        assert session.calls[0][2]["page_id"] == "123456789"

    def test_extracts_the_page_id_from_a_query_parameter(self):
        session = FakeSession({"confluence_get_page": {"id": "42", "title": "t", "text": ""}})
        fetcher = ConfluencePageFetcher(AtlassianSourceAdapter(session))
        result = fetcher.fetch(resource(
            "https://x.atlassian.net/pages/viewpage.action?pageId=42",
            ResourceType.CONFLUENCE_PAGE, rule=4,
        ))
        assert result.ok
        assert session.calls[0][2]["page_id"] == "42"


class TestConfluenceSpaceFetcher:
    def test_scopes_the_search_to_the_space(self):
        session = FakeSession({"confluence_search": {"results": []}})
        fetcher = ConfluenceSpaceFetcher(AtlassianSourceAdapter(session))
        result = fetcher.fetch(resource(
            "https://x.atlassian.net/wiki/spaces/PAY", ResourceType.CONFLUENCE_SPACE, rule=5
        ))
        assert result.ok
        cql = session.calls[0][2]["cql"]
        assert 'space = "PAY"' in cql and "type = page" in cql


# --- Bitbucket --------------------------------------------------------------------------

class TestBitbucketRepoFetcher:
    def test_a_readable_repo_is_confirmed_and_recorded(self):
        session = FakeSession({"bitbucket_repos": {"repos": [
            {"repo": "checkout-service", "project": "PAY", "branch": "main",
             "head_sha": "a" * 40, "web_url": "https://bitbucket.org/x/checkout-service"},
        ]}})
        fetcher = BitbucketRepoFetcher(BitbucketSourceAdapter(session))
        result = fetcher.fetch(resource(
            "https://bitbucket.org/your-org/checkout-service",
            ResourceType.BITBUCKET_REPO, rule=6,
        ))
        assert result.ok
        assert result.value[0].source_identifier == "checkout-service"
        assert "a" * 40 in result.value[0].content

    def test_a_repo_the_server_cannot_see_is_refused_with_a_useful_remedy(self):
        session = FakeSession({"bitbucket_repos": {"repos": []}})
        fetcher = BitbucketRepoFetcher(BitbucketSourceAdapter(session))
        result = fetcher.fetch(resource(
            "https://bitbucket.org/your-org/checkout-service",
            ResourceType.BITBUCKET_REPO, rule=6,
        ))
        assert not result.ok
        assert "checkout-service" in result.message
        assert "BITBUCKET_REPO_ROOT" in result.remediation

    def test_the_project_repos_url_form_also_extracts_correctly(self):
        session = FakeSession({"bitbucket_repos": {"repos": [
            {"repo": "checkout-service", "project": "PAY", "branch": "main",
             "head_sha": "b" * 40},
        ]}})
        fetcher = BitbucketRepoFetcher(BitbucketSourceAdapter(session))
        result = fetcher.fetch(resource(
            "https://bitbucket.example.com/projects/PAY/repos/checkout-service/browse",
            ResourceType.BITBUCKET_REPO, rule=6,
        ))
        assert result.ok
        assert result.value[0].source_identifier == "checkout-service"


# --- Design folder (the Figma screenshot case) -----------------------------------------------

class TestDesignFolderFetcher:
    def test_associated_screenshots_become_records(self, tmp_path):
        folder = tmp_path / "designs"
        folder.mkdir()
        (folder / "checkout__basket.png").write_bytes(b"fake-png-bytes-1")
        (folder / "checkout__basket__empty.png").write_bytes(b"fake-png-bytes-2")

        fetcher = DesignFolderFetcher(workspace_root=tmp_path)
        result = fetcher.fetch(resource("designs", ResourceType.DESIGN_FOLDER, rule=8))

        assert result.ok
        names = {r.source_identifier for r in result.value.records}
        assert names == {"checkout__basket.png", "checkout__basket__empty.png"}
        record = next(r for r in result.value.records if "empty" in r.source_identifier)
        assert record.metadata["feature"] == "checkout"
        assert record.metadata["screen"] == "basket"
        assert record.metadata["state"] == "empty"

    def test_a_manifest_overrides_field_by_field(self, tmp_path):
        folder = tmp_path / "designs"
        folder.mkdir()
        (folder / "checkout__basket.png").write_bytes(b"x")
        (folder / "screens.manifest.yaml").write_text(
            "checkout__basket.png:\n  jira_key: PAY-12\n  route: /basket\n",
            encoding="utf-8",
        )
        fetcher = DesignFolderFetcher(workspace_root=tmp_path)
        result = fetcher.fetch(resource("designs", ResourceType.DESIGN_FOLDER, rule=8))
        record = result.value.records[0]
        assert record.metadata["jira_key"] == "PAY-12"
        assert record.metadata["route"] == "/basket"
        # The manifest overrides only the fields it names - feature/screen still
        # come from the filename (BR-U2-4.2, field by field, not wholesale).
        assert record.metadata["feature"] == "checkout"

    def test_unassociated_files_are_reported_never_dropped(self, tmp_path):
        folder = tmp_path / "designs"
        folder.mkdir()
        (folder / "random-export.png").write_bytes(b"x")
        fetcher = DesignFolderFetcher(workspace_root=tmp_path)
        result = fetcher.fetch(resource("designs", ResourceType.DESIGN_FOLDER, rule=8))
        assert result.ok
        assert result.value.records == []
        assert "random-export.png" in result.value.guidance
        assert "1 file" in result.value.guidance

    def test_re_uploading_a_changed_image_under_the_same_name_changes_the_hash(self, tmp_path):
        """BR-U2-3.1 applied to a binary file: the artefact-level content hash
        must move when the image bytes change, even though the filename didn't."""
        from tto_testgen.domain.model import content_hash

        folder = tmp_path / "designs"
        folder.mkdir()
        path = folder / "checkout__basket.png"
        path.write_bytes(b"version one")
        first = DesignFolderFetcher(tmp_path).fetch(
            resource("designs", ResourceType.DESIGN_FOLDER, rule=8)
        ).value.records[0]

        path.write_bytes(b"version two, materially different")
        second = DesignFolderFetcher(tmp_path).fetch(
            resource("designs", ResourceType.DESIGN_FOLDER, rule=8)
        ).value.records[0]

        assert content_hash(first.content) != content_hash(second.content)

    def test_a_relative_folder_resolves_against_the_workspace_root(self, tmp_path):
        (tmp_path / "designs").mkdir()
        (tmp_path / "designs" / "checkout__basket.png").write_bytes(b"x")
        fetcher = DesignFolderFetcher(workspace_root=tmp_path)
        result = fetcher.fetch(resource("./designs", ResourceType.DESIGN_FOLDER, rule=8))
        assert result.ok and len(result.value.records) == 1

    def test_a_missing_folder_is_reported_clearly(self, tmp_path):
        fetcher = DesignFolderFetcher(workspace_root=tmp_path)
        result = fetcher.fetch(resource("nowhere", ResourceType.DESIGN_FOLDER, rule=8))
        assert not result.ok
        assert "not found" in result.message


# --- the dispatch table -----------------------------------------------------------------------

class TestBuildSourceFor:
    def test_every_fetchable_type_resolves_to_a_fetcher(self, tmp_path):
        source_for = build_source_for(object(), object(), tmp_path)
        for rtype in (
            ResourceType.JIRA_ISSUE, ResourceType.JIRA_QUERY,
            ResourceType.CONFLUENCE_PAGE, ResourceType.CONFLUENCE_SPACE,
            ResourceType.BITBUCKET_REPO, ResourceType.DESIGN_FOLDER,
        ):
            assert source_for(rtype) is not None, rtype

    def test_openapi_spec_has_no_fetcher_by_design(self, tmp_path):
        """This system has no generic HTTP fetcher. FR-ING-06 already routes specs
        through api_model_derive against a Bitbucket repo instead."""
        source_for = build_source_for(object(), object(), tmp_path)
        assert source_for(ResourceType.OPENAPI_SPEC) is None

    def test_unclassified_has_no_fetcher(self, tmp_path):
        source_for = build_source_for(object(), object(), tmp_path)
        assert source_for(ResourceType.UNCLASSIFIED) is None
