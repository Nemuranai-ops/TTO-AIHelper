"""A4 BitbucketSourceAdapter - repositories, endpoints, files, history. Read-only.

Names only read tools. The read-only posture is asserted by a test over this source.

Requirements: FR-ING-05, FR-ING-06, FR-TRC-02, FR-TRC-06, FR-DLT-01, C-06.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from tto_testgen.adapters.mcp_client import McpClientSession
from tto_testgen.domain.apimodel import AuthRequirement, CodeEndpoint
from tto_testgen.domain.traceability import CommitRecord
from tto_testgen.platform.result import Err, Result, ok
from tto_testgen.ports.sources import RepoInfo

SERVER = "tto-bitbucket"

_AUTH_HINT = re.compile(r"(require[sd]?_?auth|authenticated|@login_required|\[Authorize\])", re.I)
_ANON_HINT = re.compile(r"(allow_anonymous|permit_all|\[AllowAnonymous\])", re.I)


@dataclass(slots=True)
class BitbucketSourceAdapter:
    """Satisfies P2 `BitbucketSource`."""

    session: McpClientSession

    def repos(self) -> Result[list[RepoInfo]]:
        """tt-bitbucket-mcp's own response shape (bitbucket_mcp_server.py, repo_summary):
        "repo" is the clone's folder name - what resolve_repo() accepts as `repo` in
        every other tool call, so it is what `slug` must be, never "repo_slug". The
        head commit is "head_sha", never "head_commit". "project" and "web_url" come
        from parsing the remote URL (bitbucket_coordinates) - "slug" also exists there,
        but names Bitbucket's own remote-side slug, a different thing from the local
        folder name every other tool call needs.
        """
        result = self.session.call(SERVER, "bitbucket_repos", {})
        if isinstance(result, Err):
            return result
        return ok([
            RepoInfo(
                slug=r.get("repo", ""), project_key=r.get("project", ""),
                branch=r.get("branch", ""), head_commit=r.get("head_sha", ""),
                browse_url=r.get("web_url", ""),
            )
            for r in result.value.get("repos", [])
        ])

    def endpoints(self, repo_slug: str) -> Result[tuple[list[CodeEndpoint], list[str]]]:
        """Returns (endpoints from code, paths to any OpenAPI/Swagger spec files found).

        tt-bitbucket-mcp's own response shape (bitbucket_mcp_server.py,
        bitbucket_endpoints): the spec paths are "api_spec_files" - there is no key
        named "openapi" at all, so this always returned None before. A path is all
        this server can offer: it has no tool that returns a file's raw content -
        bitbucket_file's structured payload carries no content field, and its text
        output is a line-numbered human-readable snippet, not parseable source. A
        spec's location can be surfaced; fetching and parsing its shapes cannot,
        without a raw-content capability this server does not currently expose.

        Each endpoint entry also carries no "status_codes" or "context" field in the
        real payload - status_codes stays () and auth_requirement stays UNKNOWN by
        their own correct defaults, not a bug: UNKNOWN is what BR-U2 requires when
        there is no evidence either way, and both would start working the moment a
        real payload ever carries those fields.
        """
        result = self.session.call(SERVER, "bitbucket_endpoints", {"repo": repo_slug})
        if isinstance(result, Err):
            return result
        payload = result.value
        endpoints = [
            CodeEndpoint(
                method=e.get("method", "GET"), route=e.get("route", ""),
                file_path=e.get("file", ""), line=int(e.get("line", 0)),
                symbol=e.get("symbol", ""),
                status_codes=tuple(e.get("status_codes", ())),
                auth_requirement=_infer_auth(e.get("context", "")),
            )
            for e in payload.get("endpoints", [])
        ]
        return ok((endpoints, list(payload.get("api_spec_files", []))))

    def log(
        self, repo_slug: str, *, path: str | None = None, since: datetime | None = None
    ) -> Result[list[CommitRecord]]:
        """Commit history, shaped for D3's commit-to-key derivation.

        The Bitbucket MCP reports Jira keys per commit, which is what makes BR-3
        possible at all - deriving provenance for behaviour no story names.
        """
        args: dict[str, Any] = {"repo": repo_slug}
        if path:
            args["path"] = path
        if since:
            args["since"] = since.isoformat()
        result = self.session.call(SERVER, "bitbucket_log", args)
        if isinstance(result, Err):
            return result

        # tt-bitbucket-mcp's own response shape (bitbucket_mcp_server.py,
        # bitbucket_log): "subject" and "date" (--date=short, so a bare
        # YYYY-MM-DD - fromisoformat accepts a date-only string directly), never
        # "message" or "committed_at". The server has no line-count field for this
        # tool at all, so lines_changed stays at its default; derive_key_from_
        # commits only uses it as a tie-breaker beneath timestamp, so the absence
        # degrades tie-breaking precision rather than correctness.
        commits = []
        for c in result.value.get("commits", []):
            try:
                committed_at = datetime.fromisoformat(c.get("date", ""))
            except ValueError:
                continue
            if committed_at.tzinfo is None:
                # A bare YYYY-MM-DD from --date=short carries no offset.
                # derive_key_from_commits compares against an aware cutoff
                # (datetime.now(timezone.utc)), and Python refuses to compare a
                # naive datetime to an aware one at all - not silently wrong,
                # an outright exception on every commit, every time.
                committed_at = committed_at.replace(tzinfo=timezone.utc)
            commits.append(CommitRecord(
                sha=c.get("sha", ""), message=c.get("subject", ""),
                committed_at=committed_at,
            ))
        return ok(commits)

    def changes(self, repo_slug: str, base: str, head: str) -> Result[list[tuple[str, str]]]:
        """(status, file) pairs changed between base and head, for D17's delta detection.

        tt-bitbucket-mcp's own response shape (bitbucket_mcp_server.py, bitbucket_changes):
        the per-file list is "changes", each entry {"status", "file"} from `git diff
        --name-status`, never "files". "commits" here is a COUNT of commits in the range,
        not the commits themselves - bitbucket_log is the source for actual commit
        records, and the field name is shared between the two tools for two different
        meanings. "jira_key_coverage_pct", not "key_coverage_percent".
        """
        result = self.session.call(
            SERVER, "bitbucket_changes", {"repo": repo_slug, "base": base, "head": head}
        )
        if isinstance(result, Err):
            return result
        return ok([
            (c.get("status", ""), c.get("file", "")) for c in result.value.get("changes", [])
        ])


def _infer_auth(context: str) -> AuthRequirement:
    """Never guesses NONE from absence of evidence.

    An undetermined auth requirement stays UNKNOWN. Defaulting it to public would
    hide a security-relevant gap (US-ANA-03 AC3).
    """
    if _ANON_HINT.search(context):
        return AuthRequirement.NONE
    if _AUTH_HINT.search(context):
        return AuthRequirement.REQUIRED
    return AuthRequirement.UNKNOWN
