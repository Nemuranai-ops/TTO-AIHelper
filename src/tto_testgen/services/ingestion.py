"""S1 IngestionService - declared resources into stored artefacts.

BR-U2-8. One transaction per resource, not per run: this is the one place U1's
all-or-nothing rule is deliberately relaxed, because at 3-10 repositories and hundreds
of issues, one unreachable source must not discard an hour of successful retrieval.

Requirements: FR-ING-01 to FR-ING-10, NFR-REL-04, NFR-PRF-04.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from tto_testgen.adapters.paging import PagedResult
from tto_testgen.adapters.sources.manifest import ClassifiedResource
from tto_testgen.domain.model import Artefact, Resource, ResourceType, content_hash, utc_now
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.resilience import RetryPolicy, isolate, with_retry
from tto_testgen.platform.result import Err, ErrorCode, Ok, Result, err, ok


@dataclass(slots=True)
class IngestionReport:
    """Four outcomes, not two.

    "Failed" and "skipped because nothing changed" are opposite situations, and
    collapsing them would make a healthy re-run look like a broken one.
    """

    succeeded: list[dict[str, Any]] = field(default_factory=list)
    skipped_unchanged: list[dict[str, Any]] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)
    unclassified: list[str] = field(default_factory=list)
    ceiling_notices: list[dict[str, Any]] = field(default_factory=list)

    @property
    def totals(self) -> dict[str, int]:
        return {
            "succeeded": len(self.succeeded),
            "skipped_unchanged": len(self.skipped_unchanged),
            "failed": len(self.failed),
            "unclassified": len(self.unclassified),
            "artefacts_stored": sum(r.get("artefacts", 0) for r in self.succeeded),
            "artefacts_skipped": sum(r.get("artefacts", 0) for r in self.skipped_unchanged),
        }

    @property
    def is_partial(self) -> bool:
        return bool(self.failed or self.unclassified or self.ceiling_notices)

    def to_dict(self) -> dict[str, Any]:
        return {
            "succeeded": self.succeeded,
            "skipped_unchanged": self.skipped_unchanged,
            "failed": self.failed,
            "unclassified": self.unclassified,
            "ceiling_notices": self.ceiling_notices,
            "totals": self.totals,
            "partial": self.is_partial,
            # The system cannot know whether the missing repository mattered.
            # Reporting and stopping is the only honest option (BR-U2-8.2).
            "note": (
                "Review before approving the ingest stage. A partial run is a fact to "
                "weigh, not a verdict."
            ),
        }


class IngestionService:
    def __init__(
        self,
        uow_factory: Callable[[], Any],
        manifest_adapter: Any,
        source_for: Callable[[ResourceType], Any],
        logger: Logger,
        *,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._manifest = manifest_adapter
        self._source_for = source_for
        self._logger = logger
        self._retry = retry_policy or RetryPolicy()

    def ingest_resources(self) -> Result[IngestionReport]:
        parsed = self._manifest.parse()
        if isinstance(parsed, Err):
            return parsed
        classified, unclassifiable = parsed.value

        report = IngestionReport(unclassified=list(unclassifiable))
        if unclassifiable:
            self._logger.warning("unclassifiable entries", count=len(unclassifiable))

        results = isolate(classified, self._ingest_one, self._logger)

        for resource, outcome in results.succeeded:
            stored, skipped, ceiling = outcome
            entry = {
                "raw_ref": resource.raw_ref, "type": resource.type.value,
                "inferred_from": resource.inferred_from, "artefacts": stored,
            }
            # Every non-failed resource lands in exactly one bucket. An earlier
            # version appended conditionally, so a resource that legitimately
            # returned nothing at all appeared in neither and vanished from the
            # report - the one outcome an operator would most want to see.
            if stored:
                report.succeeded.append(entry)
            elif skipped:
                report.skipped_unchanged.append({**entry, "artefacts": skipped})
            else:
                report.succeeded.append({**entry, "artefacts": 0, "note": "no records returned"})
            if ceiling:
                report.ceiling_notices.append(
                    {"raw_ref": resource.raw_ref, "guidance": ceiling}
                )

        for resource, failure in results.failed:
            report.failed.append({
                "raw_ref": resource.raw_ref, "type": resource.type.value,
                "code": failure.code.value, "message": failure.message,
                "failure_class": failure.context.get("failure_class", "error"),
                "remediation": failure.remediation,
            })

        return ok(report)

    def _ingest_one(self, resource: ClassifiedResource) -> Result[tuple[int, int, str]]:
        """One resource, one transaction. Returns (stored, skipped, ceiling guidance)."""
        source = self._source_for(resource.type)
        if source is None:
            return err(
                ErrorCode.FAILED_INTERNAL,
                f"No adapter for resource type {resource.type.value}",
            )

        fetched = with_retry(
            lambda: source.fetch(resource), self._retry, self._logger
        )
        if isinstance(fetched, Err):
            return fetched

        payload = fetched.value
        records = payload.records if isinstance(payload, PagedResult) else payload
        guidance = payload.guidance if isinstance(payload, PagedResult) else ""

        stored = skipped = 0
        with self._uow_factory() as uow:
            uow.resources.upsert(Resource(
                raw_ref=resource.raw_ref, type=resource.type,
                inferred_from=resource.inferred_from, status="ingested",
                last_ingested_at=utc_now(),
            ))
            resource_id = uow.resources.id_for(resource.raw_ref)
            if resource_id is None:
                return err(
                    ErrorCode.FAILED_INTERNAL,
                    f"resource {resource.raw_ref} was not persisted",
                )

            for record in records:
                digest = content_hash(record.content)
                if uow.artefacts.get_by_hash(digest) is not None:
                    skipped += 1              # NFR-PRF-04: no store, no re-fetch next run
                    continue
                uow.artefacts.upsert(Artefact(
                    resource_id=resource_id, kind=record.kind,
                    source_identifier=record.source_identifier,
                    content=record.content, content_hash=digest,
                    metadata=dict(record.metadata), detail_level=record.detail_level,
                ))
                stored += 1

        self._logger.info(
            "resource ingested", raw_ref=resource.raw_ref,
            stored=stored, skipped=skipped,
        )
        return ok((stored, skipped, guidance))
