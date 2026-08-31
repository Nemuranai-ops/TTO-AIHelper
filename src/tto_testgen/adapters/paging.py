"""L7 PagedFetcher - bounded page-by-page retrieval.

The ceiling is enforced here rather than in the service, because this is the only
place that knows a further page exists. Stopping here means the excess is never
fetched, transferred, parsed or held.

Requirements: U2-NFR-SCL-02 to -05. Pattern: P-U2-02.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 100
DEFAULT_CEILING = 2000

#: (cursor) -> (records, next_cursor). Supplied by the caller, so this component
#: knows nothing about Jira, Confluence or Bitbucket.
FetchPage = Callable[[str | None], tuple[list[Any], str | None]]


@dataclass(slots=True)
class PagedResult:
    records: list[Any] = field(default_factory=list)
    ceiling_reached: bool = False
    pages_fetched: int = 0
    ceiling: int = DEFAULT_CEILING
    guidance: str = ""

    @property
    def count(self) -> int:
        return len(self.records)

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "pages_fetched": self.pages_fetched,
            "ceiling_reached": self.ceiling_reached,
            "ceiling": self.ceiling,
            "guidance": self.guidance,
        }


def fetch_paged(
    fetch_page: FetchPage,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    ceiling: int = DEFAULT_CEILING,
) -> PagedResult:
    """Page until exhausted or the ceiling is reached.

    A ceiling without a report is worse than no ceiling: the run appears to succeed,
    the corpus is quietly built on a fraction of the input, and nobody finds out until
    coverage looks inexplicably thin. `guidance` is populated here rather than by the
    caller, so every adapter gives the operator the same actionable message.
    """
    if ceiling < 1:
        raise ValueError(f"ceiling must be at least 1, got {ceiling}")

    result = PagedResult(ceiling=ceiling)
    cursor: str | None = None

    while True:
        records, cursor = fetch_page(cursor)
        result.pages_fetched += 1
        result.records.extend(records)

        if len(result.records) >= ceiling:
            more = cursor is not None or len(result.records) > ceiling
            result.records = result.records[:ceiling]
            result.ceiling_reached = True
            if more:
                result.guidance = (
                    f"Stopped at the {ceiling}-artefact ceiling with more available. "
                    f"Narrow the query, or raise TAAS_INGEST_MAX_PER_RESOURCE if this "
                    f"volume is intended."
                )
            return result

        if cursor is None or not records:
            return result
