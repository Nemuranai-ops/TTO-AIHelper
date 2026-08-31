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
from tto_testgen.adapters.paging import DEFAULT_CEILING, DEFAULT_PAGE_SIZE, PagedResult, fetch_paged
from tto_testgen.domain.apimodel import AuthRequirement, CodeEndpoint
from tto_testgen.domain.traceability import CommitRecord
from tto_testgen.platform.result import Err, Result, err, ok
from tto_testgen.ports.sources import RepoInfo, SourceRecord

SERVER = "tto-bitbucket"

_AUTH_HINT = re.compile(r"(require[sd]?_?auth|authenticated|@login_required|\[Authorize\])", re.I)
_ANON_HINT = re.compile(r"(allow_anonymous|permit_all|\[AllowAnonymous\])", re.I)


@dataclass(slots=True)
class BitbucketSourceAdapter:
    """Satisfies P2 `BitbucketSource`."""

    session: McpClientSession
    page_size: int = DEFAULT_PAGE_SIZE
    ceiling: int = DEFAULT_CEILING

    def repos(self) -> Result[list[RepoInfo]]:
        result = self.session.call(SERVER, "bitbucket_repos", {})
        if isinstance(result, Err):
            return result
        return ok([
            RepoInfo(
                slug=r.get("repo_slug", ""), project_key=r.get("project_key", ""),
                branch=r.get("branch", ""), head_commit=r.get("head_commit", ""),
                browse_url=r.get("browse_url", ""),
            )
            for r in result.value.get("repos", [])
        ])

    def endpoints(self, repo_slug: str) -> Result[tuple[list[CodeEndpoint], dict | None]]:
        """Returns (endpoints from code, any OpenAPI spec found)."""
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
        return ok((endpoints, payload.get("openapi")))

    def file(self, repo_slug: str, path: str, ref: str) -> Result[SourceRecord]:
        result = self.session.call(
            SERVER, "bitbucket_file", {"repo": repo_slug, "path": path, "ref": ref}
        )
        if isinstance(result, Err):
            return result
        return ok(SourceRecord(
            source_identifier=f"{repo_slug}:{path}@{ref}", kind="source-file",
            content=result.value.get("content", ""),
            metadata={"repo": repo_slug, "path": path, "ref": ref},
        ))

    def grep(self, repo_slug: str, pattern: str, ref: str) -> Result[PagedResult]:
        failure: list[Err] = []

        def page(cursor):
            args: dict[str, Any] = {"repo": repo_slug, "pattern": pattern, "ref": ref}
            if cursor:
                args["cursor"] = cursor
            outcome = self.session.call(SERVER, "bitbucket_grep", args)
            if isinstance(outcome, Err):
                failure.append(outcome)
                return [], None
            return outcome.value.get("matches", []), outcome.value.get("next_cursor")

        paged = fetch_paged(page, page_size=self.page_size, ceiling=self.ceiling)
        return failure[0] if failure else ok(paged)

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

    def changes(self, repo_slug: str, base: str, head: str) -> Result[dict[str, Any]]:
        result = self.session.call(
            SERVER, "bitbucket_changes", {"repo": repo_slug, "base": base, "head": head}
        )
        if isinstance(result, Err):
            return result
        payload = result.value
        return ok({
            "files": payload.get("files", []),
            "commits": payload.get("commits", []),
            "jira_keys": payload.get("jira_keys", []),
            "key_coverage_percent": payload.get("key_coverage_percent"),
        })


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
