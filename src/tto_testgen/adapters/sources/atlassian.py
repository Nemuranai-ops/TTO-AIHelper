"""A3 AtlassianSourceAdapter - Jira and Confluence, read-only.

This module names only read tools. NFR-SEC-14 requires the read-only posture, and
since L6 exposes a general `call`, absence of write capability is no longer visible
from a method signature - so it is asserted by a test over this module's source.

Requirements: FR-ING-03, FR-ING-04, C-05, U2-NFR-SEC-03. BR-U2-2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from tto_testgen.adapters.mcp_client import McpClientSession
from tto_testgen.adapters.paging import DEFAULT_CEILING, DEFAULT_PAGE_SIZE, PagedResult, fetch_paged
from tto_testgen.platform.result import Err, Ok, Result, err, ok
from tto_testgen.ports.sources import SourceRecord

SERVER = "tto-atlassian"

#: BR-U2-2.2. Low when the description is short AND criteria are absent. Both,
#: because a short story with clear criteria is perfectly usable and flagging it
#: would cry wolf.
THIN_DESCRIPTION_CHARS = 200

_CRITERIA_HEADING = re.compile(
    r"(acceptance\s+criteria|given\s+.*when\s+.*then)", re.I | re.S
)


def detail_level(description: str, acceptance_criteria: str | None) -> str:
    has_criteria = bool(acceptance_criteria and acceptance_criteria.strip()) or bool(
        _CRITERIA_HEADING.search(description or "")
    )
    if len(description or "") < THIN_DESCRIPTION_CHARS and not has_criteria:
        return "low"
    return "full"


def _classify_failure(message: str) -> str:
    """Not-found and not-authorised call for different actions: fix the reference,
    or fix the permissions (US-ING-02 AC6)."""
    lowered = message.lower()
    if "not found" in lowered or "404" in lowered or "does not exist" in lowered:
        return "not-found"
    if any(w in lowered for w in ("forbidden", "unauthor", "permission", "401", "403")):
        return "not-authorised"
    return "error"


@dataclass(slots=True)
class AtlassianSourceAdapter:
    """Satisfies P2 `JiraSource` and `ConfluenceSource`."""

    session: McpClientSession
    page_size: int = DEFAULT_PAGE_SIZE
    ceiling: int = DEFAULT_CEILING

    # --- Jira -------------------------------------------------------------

    def get_issue(self, key: str) -> Result[SourceRecord]:
        result = self.session.call(SERVER, "jira_get_issue", {"issue_key": key})
        if isinstance(result, Err):
            return err(result.code, result.message,
                       remediation=result.remediation,
                       failure_class=_classify_failure(result.message), key=key)
        return ok(self._to_issue_record(result.value))

    def search(self, jql: str) -> Result[PagedResult]:
        """Paged, bounded, and reporting when the ceiling stops it."""
        failure: list[Err] = []

        def page(cursor):
            args: dict[str, Any] = {"jql": jql, "limit": self.page_size}
            if cursor:
                args["cursor"] = cursor
            outcome = self.session.call(SERVER, "jira_search_issues", args)
            if isinstance(outcome, Err):
                failure.append(outcome)
                return [], None
            payload = outcome.value
            return payload.get("issues", []), payload.get("next_cursor")

        paged = fetch_paged(page, page_size=self.page_size, ceiling=self.ceiling)
        if failure:
            return failure[0]
        paged.records = [self._to_issue_record(issue) for issue in paged.records]
        return ok(paged)

    def updated_since(self, since: datetime, project: str) -> Result[PagedResult]:
        stamp = since.strftime("%Y-%m-%d %H:%M")
        return self.search(f'project = "{project}" AND updated >= "{stamp}"')

    def _to_issue_record(self, payload: dict[str, Any]) -> SourceRecord:
        description = payload.get("description") or ""
        criteria = payload.get("acceptance_criteria")
        comments = payload.get("comments") or []
        # BR-U2-3.1: content only. Labels, status and assignee are metadata and are
        # excluded, so a label change does not re-ingest and re-analyse everything.
        content = "\n\n".join(
            [payload.get("summary", ""), description, criteria or "",
             *(c.get("body", "") for c in comments)]
        ).strip()
        return SourceRecord(
            source_identifier=payload.get("key", ""),
            kind="jira-issue",
            content=content,
            metadata={
                "issue_type": payload.get("issue_type"),
                "status": payload.get("status"),
                "labels": payload.get("labels", []),
                "parent": payload.get("parent"),
                "comment_count": len(comments),
            },
            detail_level=detail_level(description, criteria),
        )

    # --- Confluence -------------------------------------------------------

    def get_page(
        self, page_id: str | None = None, *, title: str | None = None,
        space_key: str | None = None,
    ) -> Result[SourceRecord]:
        args = {k: v for k, v in
                {"page_id": page_id, "title": title, "space_key": space_key}.items()
                if v is not None}
        result = self.session.call(SERVER, "confluence_get_page", args)
        if isinstance(result, Err):
            return err(result.code, result.message, remediation=result.remediation,
                       failure_class=_classify_failure(result.message))
        return ok(self._to_page_record(result.value))

    def search_pages(self, cql: str) -> Result[PagedResult]:
        failure: list[Err] = []

        def page(cursor):
            args: dict[str, Any] = {"cql": cql, "limit": self.page_size}
            if cursor:
                args["cursor"] = cursor
            outcome = self.session.call(SERVER, "confluence_search", args)
            if isinstance(outcome, Err):
                failure.append(outcome)
                return [], None
            payload = outcome.value
            return payload.get("pages", []), payload.get("next_cursor")

        paged = fetch_paged(page, page_size=self.page_size, ceiling=self.ceiling)
        if failure:
            return failure[0]
        paged.records = [self._to_page_record(p) for p in paged.records]
        return ok(paged)

    def _to_page_record(self, payload: dict[str, Any]) -> SourceRecord:
        # BR-U2-2.3: tables preserved as structured rows. A table of validation rules
        # is the most directly useful thing a Confluence page can hold, and
        # flattening it into prose destroys exactly that.
        tables = payload.get("tables") or []
        body = payload.get("text") or payload.get("body") or ""
        content = body if not tables else f"{body}\n\n{_render_tables(tables)}"
        return SourceRecord(
            source_identifier=str(payload.get("id", payload.get("title", ""))),
            kind="confluence-page",
            content=content.strip(),
            metadata={
                "title": payload.get("title"),
                "space_key": payload.get("space_key"),
                "labels": payload.get("labels", []),
                "table_count": len(tables),
            },
        )


def _render_tables(tables: list[Any]) -> str:
    blocks = []
    for index, table in enumerate(tables, start=1):
        rows = table if isinstance(table, list) else table.get("rows", [])
        rendered = "\n".join(" | ".join(str(cell) for cell in row) for row in rows)
        blocks.append(f"[table {index}]\n{rendered}")
    return "\n\n".join(blocks)
