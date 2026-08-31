"""U4's tools - generation, view emission, and volume reporting.

Three write-tier tools. The matrix stays where it already lives, in `tools_read`:
it is built on demand from `trace_link` and stores nothing, so it belongs to the
read tier by the same rule that put every other query there.

Requirements: FR-TCG-01 to FR-TCG-10, FR-TRC-05, FR-TRC-06.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from tto_testgen.mcp.server import ToolRegistry, ToolSpec
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import ErrorCode, Ok, Result, err, ok


class CasesUpsert(BaseModel):
    feature_slug: str = Field(min_length=1)
    cases: list[dict[str, Any]] = Field(
        min_length=1,
        description=(
            "Each case: coverage_item_id, title, test_type, priority, preconditions, "
            "steps [{ordinal, action, expected}], test_data [{field, value, "
            "equivalence_class, boundary_relation?, step_ordinal?}], tags, "
            "trace_links [{type, jira_key, evidence}], referenced_screen_ids, and "
            "the four automatability booleans. No identifier field: the toolchain "
            "allocates it."
        ),
    )


class ViewsEmit(BaseModel):
    feature_slug: str = Field(min_length=1)


class VolumeReport(BaseModel):
    feature_slug: str | None = Field(
        default=None,
        description="Omit for the whole corpus; name a feature for per-coverage-item detail.",
    )


def register_u4_tools(registry: ToolRegistry, generation_service: Any) -> None:
    def tool(name: str, description: str, schema: type[BaseModel]):
        def decorator(fn):
            registry.register(ToolSpec(name, description, schema, fn, "write"))
            return fn

        return decorator

    @tool(
        "testcases_upsert",
        "Generate test cases for one feature. The batch is accepted entirely or not "
        "at all, with every failure reported together and no identifier allocated on "
        "rejection. Duplicates, unknown Jira keys, missing equivalence classes and "
        "real personal data in test values are all refused. Views for the feature "
        "are re-emitted on success, skipping any the operator has edited.",
        CasesUpsert,
    )
    def testcases_upsert(args: CasesUpsert, log: Logger) -> Result[Any]:
        result = generation_service.upsert_cases(args.feature_slug, args.cases)
        if not isinstance(result, Ok):
            return result
        report = result.value
        if report.rejections:
            return err(
                ErrorCode.REJECTED_INVALID_STEPS,
                f"{len(report.rejections)} case(s) rejected; nothing was stored",
                remediation=(
                    "Correct every case named below and resubmit the batch. Each "
                    "rejection names its own remedy: personal data is replaced with a "
                    "documented synthetic value, a duplicate is varied or dropped, and "
                    "an unknown Jira key is either corrected or ingested first."
                ),
                rejections=report.rejections,
            )
        return ok(report.to_dict())

    @tool(
        "views_emit",
        "Re-emit the Markdown and YAML views for one feature. Reports three "
        "outcomes: written, unchanged, and hand-edited. A hand-edited file is "
        "skipped and never overwritten - the corpus is the system of record, but "
        "the edit is not derivable from it.",
        ViewsEmit,
    )
    def views_emit(args: ViewsEmit, log: Logger) -> Result[Any]:
        return generation_service.emit_views(args.feature_slug)

    @tool(
        "volume_report",
        "Generated cases against the planned coverage model, per feature and per "
        "coverage item. A shortfall is reported with its reasons and never closed "
        "by padding.",
        VolumeReport,
    )
    def volume_report(args: VolumeReport, log: Logger) -> Result[Any]:
        return generation_service.volume_report(args.feature_slug)
