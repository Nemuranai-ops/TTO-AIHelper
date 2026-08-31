"""A3, A4, A5, A6. Requirements: FR-ING-01 to FR-ING-07, U2-NFR-SEC-03."""

from __future__ import annotations

import ast
import pathlib
import re
from datetime import datetime, timezone

import pytest

from tto_testgen.adapters.sources import atlassian, bitbucket
from tto_testgen.adapters.sources.atlassian import (
    AtlassianSourceAdapter,
    THIN_DESCRIPTION_CHARS,
    _classify_failure,
    detail_level,
)
from tto_testgen.adapters.sources.bitbucket import BitbucketSourceAdapter, _infer_auth
from tto_testgen.adapters.sources.design_assets import (
    DesignAssetAdapter,
    parse_filename,
    slugify,
)
from tto_testgen.adapters.sources.manifest import (
    RULES,
    ResourceManifestAdapter,
    classify,
    extract_links,
)
from tto_testgen.domain.apimodel import AuthRequirement
from tto_testgen.domain.model import ResourceType
from tto_testgen.platform.result import ErrorCode, ok


class FakeSession:
    """Stands in for L6. Records calls so the read-only posture can be observed."""

    def __init__(self, responses=None, fail_with=None):
        self.responses = responses or {}
        self.fail_with = fail_with
        self.calls: list[tuple[str, str, dict]] = []

    def is_available(self, server):
        return True

    def call(self, server, tool, arguments):
        self.calls.append((server, tool, arguments))
        if self.fail_with:
            from tto_testgen.platform.result import err

            return err(*self.fail_with)
        return ok(self.responses.get(tool, {}))


# --------------------------------------------------------------------------
# A6 ResourceManifestAdapter
# --------------------------------------------------------------------------


class TestResourceInference:
    @pytest.mark.parametrize(
        "ref,expected,rule",
        [
            ("https://x.atlassian.net/browse/PAY-12", ResourceType.JIRA_ISSUE, 1),
            ("PAY-12", ResourceType.JIRA_ISSUE, 2),
            ("https://x.atlassian.net/issues/?jql=project%20=%20PAY", ResourceType.JIRA_QUERY, 3),
            ("https://x.atlassian.net/wiki/spaces/ENG/pages/1/Checkout",
             ResourceType.CONFLUENCE_PAGE, 4),
            ("https://x.atlassian.net/wiki/spaces/ENG", ResourceType.CONFLUENCE_SPACE, 5),
            ("https://bb.corp/projects/PAY/repos/orders", ResourceType.BITBUCKET_REPO, 6),
            ("api/openapi.yaml", ResourceType.OPENAPI_SPEC, 7),
            ("total nonsense here", ResourceType.UNCLASSIFIED, 9),
        ],
    )
    def test_each_rule_fires_for_its_pattern(self, ref, expected, rule):
        result = classify(ref)
        assert result.type is expected
        assert result.rule_number == rule

    def test_the_matching_rule_is_recorded(self):
        # A wrong inference is otherwise a guess among nine rules.
        assert "rule 1" in classify("https://x.atlassian.net/browse/PAY-12").inferred_from

    def test_rule_order_is_significant(self):
        """Rule 2 matches a bare PROJ-123 and would swallow a JQL containing one.

        Asserting the ordering means a future edit that reorders them innocently
        fails here rather than silently misclassifying queries as issues.
        """
        numbers = [r.number for r in RULES]
        assert numbers == sorted(numbers)
        jql = 'project = PAY AND key = PAY-12'
        assert classify(jql).type is ResourceType.JIRA_QUERY

    def test_directory_detection_needs_the_filesystem(self, tmp_path):
        (tmp_path / "design-assets").mkdir()
        assert classify("design-assets", tmp_path).type is ResourceType.DESIGN_FOLDER
        assert classify("no-such-dir", tmp_path).type is ResourceType.UNCLASSIFIED

    def test_prose_lines_are_skipped(self):
        refs = extract_links("# Heading\nSome prose that is not a link at all.\n- PAY-12\n")
        assert refs == ["PAY-12"]

    def test_markdown_and_autolinks_are_extracted(self):
        refs = extract_links("- [Epic](https://x/browse/PAY-1)\n- <https://bb/acme/orders>\n")
        assert refs == ["https://x/browse/PAY-1", "https://bb/acme/orders"]

    def test_duplicates_are_stored_once(self, tmp_path):
        (tmp_path / "resources.md").write_text("- PAY-12\n- PAY-12\n")
        classified, _ = ResourceManifestAdapter(tmp_path / "resources.md", tmp_path).parse().value
        assert len(classified) == 1

    def test_unclassifiable_entries_are_reported_not_dropped(self, tmp_path):
        (tmp_path / "resources.md").write_text("- PAY-12\n- total nonsense here\n")
        classified, unclassifiable = ResourceManifestAdapter(
            tmp_path / "resources.md", tmp_path
        ).parse().value
        assert len(classified) == 1
        assert unclassifiable == ["total nonsense here"]

    def test_missing_manifest_creates_no_partial_state(self, tmp_path):
        result = ResourceManifestAdapter(tmp_path / "nope.md", tmp_path).parse()
        assert result.code is ErrorCode.FAILED_INTERNAL
        assert "nope.md" in result.remediation
        assert not any(tmp_path.iterdir())  # no partial state created


# --------------------------------------------------------------------------
# A3 AtlassianSourceAdapter
# --------------------------------------------------------------------------


class TestDetailLevel:
    def test_short_without_criteria_is_low(self):
        assert detail_level("Too short.", None) == "low"

    def test_short_with_criteria_is_full(self):
        # A short story with clear criteria is perfectly usable; flagging it would
        # cry wolf.
        assert detail_level("Short.", "Given X When Y Then Z") == "full"

    def test_long_without_criteria_is_full(self):
        """Both conditions must hold for `low`.

        A long description without formal criteria usually carries enough narrative
        to work from. Flagging it too would fire on half the backlog, and a flag that
        common stops being read.
        """
        assert detail_level("x" * (THIN_DESCRIPTION_CHARS + 50), None) == "full"

    def test_only_short_and_criteria_free_is_low(self):
        assert detail_level("Short.", None) == "low"
        assert detail_level("Short.", "Given X When Y Then Z") == "full"
        assert detail_level("x" * 300, None) == "full"

    def test_criteria_detected_inside_the_description(self):
        assert detail_level("Acceptance Criteria: given a cart, when...", None) == "full"


class TestAtlassianAdapter:
    def test_issue_content_excludes_metadata(self):
        # BR-U2-3.1: a label change must not re-ingest and re-analyse everything.
        session = FakeSession({"jira_get_issue": {
            "key": "PAY-12", "summary": "Checkout", "description": "Body text",
            "labels": ["backend"], "status": "Done", "comments": [],
        }})
        record = AtlassianSourceAdapter(session).get_issue("PAY-12").value
        assert "backend" not in record.content
        assert "Done" not in record.content
        assert record.metadata["labels"] == ["backend"]

    @pytest.mark.parametrize(
        "message,expected",
        [("Issue does not exist", "not-found"), ("403 Forbidden", "not-authorised"),
         ("connection reset", "error")],
    )
    def test_not_found_is_distinguished_from_not_authorised(self, message, expected):
        assert _classify_failure(message) == expected

    def test_search_stops_at_the_ceiling_and_reports(self):
        pages = {"issues": [{"key": f"PAY-{i}", "summary": "s", "description": "d"}
                            for i in range(100)], "next_cursor": "more"}
        session = FakeSession({"jira_search_issues": pages})
        paged = AtlassianSourceAdapter(session, ceiling=250).search("project = PAY").value
        assert paged.count == 250
        assert paged.ceiling_reached
        assert "Narrow the query" in paged.guidance

    def test_confluence_tables_are_preserved_as_rows(self):
        session = FakeSession({"confluence_get_page": {
            "id": "1", "title": "Rules", "text": "intro",
            "tables": [[["field", "rule"], ["qty", "1-99"]]],
        }})
        record = AtlassianSourceAdapter(session).get_page("1").value
        assert "field | rule" in record.content
        assert "qty | 1-99" in record.content


# --------------------------------------------------------------------------
# A4 BitbucketSourceAdapter
# --------------------------------------------------------------------------


class TestBitbucketAdapter:
    def test_repos_carry_the_head_commit_for_delta_detection(self):
        """bitbucket_repos' real per-entry fields (repo_summary): "repo" (the clone's
        folder name, not "repo_slug"), "head_sha" (not "head_commit"), "project" and
        "web_url" (parsed from the remote, not "project_key"/"browse_url")."""
        session = FakeSession({"bitbucket_repos": {"repos": [
            {"repo": "orders", "project": "PAY", "branch": "main",
             "head_sha": "a" * 40, "web_url": "https://bitbucket.org/pay/orders"}]}})
        repos = BitbucketSourceAdapter(session).repos().value
        assert repos[0].slug == "orders"
        assert repos[0].head_commit == "a" * 40
        assert repos[0].project_key == "PAY"
        assert repos[0].browse_url == "https://bitbucket.org/pay/orders"

    def test_endpoints_and_spec_file_paths_are_returned_together(self):
        """bitbucket_endpoints' real field is "api_spec_files", a list of paths -
        there is no "openapi" key carrying parsed content at all (the server has no
        tool that returns raw file content, only a line-numbered human snippet)."""
        session = FakeSession({"bitbucket_endpoints": {
            "endpoints": [{"method": "get", "route": "/orders", "file": "api.py",
                           "line": 10, "symbol": "list_orders"}],
            "api_spec_files": ["openapi.yaml"],
        }})
        endpoints, spec_files = BitbucketSourceAdapter(session).endpoints("orders").value
        assert endpoints[0].route == "/orders"
        assert spec_files == ["openapi.yaml"]

    def test_no_spec_files_found_is_an_empty_list_not_none(self):
        session = FakeSession({"bitbucket_endpoints": {"endpoints": []}})
        _, spec_files = BitbucketSourceAdapter(session).endpoints("orders").value
        assert spec_files == []

    @pytest.mark.parametrize(
        "context,expected",
        [("@login_required", AuthRequirement.REQUIRED),
         ("[AllowAnonymous]", AuthRequirement.NONE),
         ("", AuthRequirement.UNKNOWN),
         ("def handler(request):", AuthRequirement.UNKNOWN)],
    )
    def test_auth_is_never_guessed_from_absence(self, context, expected):
        # Defaulting an undetermined requirement to public hides a security gap.
        assert _infer_auth(context) is expected

    def test_log_returns_commit_records_for_key_derivation(self):
        # tt-bitbucket-mcp's real bitbucket_log response: "subject" and "date"
        # (--date=short), never "message" or "committed_at" - an earlier version
        # of this test asserted the wrong contract and the mismatch went
        # undetected because nothing ever ran it against the real server.
        session = FakeSession({"bitbucket_log": {"commits": [
            {"sha": "a" * 40, "subject": "PAY-12 fix", "date": "2026-08-01"}]}})
        commits = BitbucketSourceAdapter(session).log("orders").value
        assert commits[0].jira_keys == ["PAY-12"]

    def test_a_bare_date_is_treated_as_utc_not_left_naive(self):
        """--date=short has no offset. derive_key_from_commits compares against an
        aware cutoff, and Python refuses to compare a naive datetime to an aware
        one at all - not silently wrong, an outright exception on every commit."""
        session = FakeSession({"bitbucket_log": {"commits": [
            {"sha": "a" * 40, "subject": "PAY-12 fix", "date": "2026-08-01"}]}})
        commit = BitbucketSourceAdapter(session).log("orders").value[0]
        assert commit.committed_at.tzinfo is not None

    def test_malformed_commit_timestamps_are_skipped_not_fatal(self):
        session = FakeSession({"bitbucket_log": {"commits": [
            {"sha": "a" * 40, "subject": "PAY-1", "date": "not a date"},
            {"sha": "b" * 40, "subject": "PAY-2", "date": "2026-08-01"}]}})
        commits = BitbucketSourceAdapter(session).log("orders").value
        assert len(commits) == 1

    def test_changes_returns_status_file_pairs(self):
        """bitbucket_changes' real field is "changes", each entry {"status", "file"} -
        never "files" (bitbucket_mcp_server.py, bitbucket_changes)."""
        session = FakeSession({"bitbucket_changes": {
            "changes": [{"status": "M", "file": "a.py"}, {"status": "D", "file": "b.py"}],
            "jira_keys": ["PAY-1"], "jira_key_coverage_pct": 87}})
        result = BitbucketSourceAdapter(session).changes("orders", "v1", "v2").value
        assert result == [("M", "a.py"), ("D", "b.py")]


# --------------------------------------------------------------------------
# A5 DesignAssetAdapter
# --------------------------------------------------------------------------


def write_png(folder, name):
    (folder / name).write_bytes(b"\x89PNG\r\n\x1a\n" + name.encode())


class TestDesignAssets:
    def test_two_segments_default_the_state(self):
        assert parse_filename("checkout__cart") == {
            "feature": "checkout", "screen": "cart", "state": "default"}

    def test_three_segments_supply_all(self):
        assert parse_filename("checkout__cart__empty")["state"] == "empty"

    @pytest.mark.parametrize("stem", ["single", "a__b__c__d"])
    def test_other_shapes_are_unparseable(self, stem):
        assert parse_filename(stem) is None

    def test_unassociated_files_are_reported(self, tmp_path):
        write_png(tmp_path, "single.png")
        parse = DesignAssetAdapter(tmp_path).screenshots().value
        assert parse.unassociated == ["single.png"]

    def test_manifest_overrides_field_by_field(self, tmp_path):
        # Wholesale replacement would force restating the other fields, and a
        # restatement is a chance to introduce an error.
        write_png(tmp_path, "checkout__cart__empty.png")
        (tmp_path / "screens.manifest.yaml").write_text(
            "checkout__cart__empty.png:\n  feature: payments\n  route: /cart\n"
        )
        asset = DesignAssetAdapter(tmp_path).screenshots().value.associated[0]
        assert asset.feature == "payments"      # overridden
        assert asset.screen == "cart"           # from the filename
        assert asset.state == "empty"           # from the filename
        assert asset.route == "/cart"           # manifest-only field
        assert asset.origin["feature"] == "manifest"
        assert asset.origin["screen"] == "filename"

    def test_manifest_can_rescue_an_unparseable_filename(self, tmp_path):
        write_png(tmp_path, "screenshot-001.png")
        (tmp_path / "screens.manifest.yaml").write_text(
            "screenshot-001.png:\n  feature: checkout\n  screen: cart\n"
        )
        parse = DesignAssetAdapter(tmp_path).screenshots().value
        assert parse.unassociated == []
        assert parse.associated[0].feature == "checkout"

    def test_content_hash_supports_change_detection(self, tmp_path):
        write_png(tmp_path, "checkout__cart.png")
        asset = DesignAssetAdapter(tmp_path).screenshots().value.associated[0]
        assert len(asset.content_hash) == 64

    def test_missing_folder_is_a_configuration_error(self, tmp_path):
        result = DesignAssetAdapter(tmp_path / "absent").screenshots()
        assert not result.ok
        assert "resources.md" in result.remediation

    def test_malformed_manifest_is_reported_not_ignored(self, tmp_path):
        write_png(tmp_path, "checkout__cart.png")
        (tmp_path / "screens.manifest.yaml").write_text("a:\n  b: [unclosed\n")
        result = DesignAssetAdapter(tmp_path).screenshots()
        assert not result.ok
        assert "not valid YAML" in result.message

    def test_non_image_files_are_ignored(self, tmp_path):
        write_png(tmp_path, "checkout__cart.png")
        (tmp_path / "notes.txt").write_text("ignore me")
        parse = DesignAssetAdapter(tmp_path).screenshots().value
        assert parse.total == 1

    def test_slugify_normalises(self):
        assert slugify("Check Out!  Cart") == "check-out-cart"


# --------------------------------------------------------------------------
# Read-only posture
# --------------------------------------------------------------------------


class TestReadOnlyPosture:
    """U2-NFR-SEC-03.

    U1 enforced the read-only posture by absent methods: the source protocols
    declared no write operation, so none could be called. L6 exposes a general
    `call(server, tool, arguments)`, which is necessary - a transport that cannot
    name a tool cannot be a transport - but it means absence is no longer visible
    from a signature. This test is the compensating check, and it is why the
    weakening was acceptable.
    """

    WRITE_TOOLS = (
        "jira_create_issue", "jira_update_issue", "jira_transition_issue",
        "confluence_create_page", "confluence_update_page",
    )

    @pytest.mark.parametrize("module", [atlassian, bitbucket])
    def test_no_write_tool_is_named_anywhere_in_the_source(self, module):
        source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        offenders = [tool for tool in self.WRITE_TOOLS if tool in source]
        assert offenders == [], f"{module.__name__} names write tools: {offenders}"

    @pytest.mark.parametrize("module", [atlassian, bitbucket])
    def test_every_tool_string_passed_to_call_is_a_known_read_tool(self, module):
        """Stronger than a denylist: enumerate what is actually called.

        A denylist only catches the write tools that exist today. This catches any
        tool name the adapter passes that is not on the known-read list.
        """
        known_reads = {
            "jira_get_issue", "jira_search_issues", "jira_get_transitions",
            "confluence_get_page", "confluence_search",
            "bitbucket_repos", "bitbucket_log", "bitbucket_tags", "bitbucket_changes",
            "bitbucket_endpoints",
        }
        tree = ast.parse(pathlib.Path(module.__file__).read_text(encoding="utf-8"))
        called: set[str] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "call"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
            ):
                called.add(node.args[1].value)
        unknown = called - known_reads
        assert unknown == set(), f"{module.__name__} calls unknown tools: {unknown}"
        assert called, f"{module.__name__} calls no tool at all - did the check break?"

    def test_the_session_records_only_read_calls_in_practice(self):
        session = FakeSession({"bitbucket_repos": {"repos": []}})
        BitbucketSourceAdapter(session).repos()
        assert [tool for _, tool, _ in session.calls] == ["bitbucket_repos"]
