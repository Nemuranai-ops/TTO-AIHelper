"""U8's tools - reports and the delta pipeline.

Three tools. `delta_detect` retires obsolete cases and reports the rest; there is no
tool that regenerates, because the service behind it has no such method (FR-DLT-06).

Requirements: FR-RPT-01 to FR-RPT-05, FR-DLT-01 to FR-DLT-07.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from tto_testgen.mcp.server import ToolRegistry, ToolSpec
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import Ok, Result, ok


class ReportsGenerate(BaseModel):
    reports: list[str] = Field(
        default_factory=list,
        description=(
            "coverage, gaps, automation, delta. Omit for all four. A section that "
            "cannot be computed is named with the stage that would supply it, and "
            "does not fail the report."
        ),
    )


class Empty(BaseModel):
    pass


def register_u8_tools(
    registry: ToolRegistry, reporting_service: Any, delta_service: Any
) -> None:
    def tool(name: str, description: str, schema: type[BaseModel], tier: str = "write"):
        def decorator(fn):
            registry.register(ToolSpec(name, description, schema, fn, tier))
            return fn

        return decorator

    @tool(
        "reports_generate",
        "Generate the coverage, gap, automation and delta reports from SQLite. Every "
        "figure is a query result with its derivation stated; none is composed by a "
        "model. Sections that cannot yet be computed are named along with the stage "
        "that would supply them.",
        ReportsGenerate,
    )
    def reports_generate(args: ReportsGenerate, log: Logger) -> Result[Any]:
        return reporting_service.generate(args.reports or None)

    @tool(
        "delta_detect",
        "Detect changes since the last completed run, map them through the "
        "traceability graph, classify each affected case, and retire the obsolete. "
        "Cases needing an update are reported and left untouched - regenerating them "
        "re-enters the pipeline at the requirements stage through the normal gates. "
        "A source that could not be reached is named, and the baseline is not "
        "advanced until every source has answered.",
        Empty,
    )
    def delta_detect(args: Empty, log: Logger) -> Result[Any]:
        result = delta_service.detect()
        if not isinstance(result, Ok):
            return result
        return ok(result.value.to_dict())

    @tool(
        "delta_status",
        "The baseline the next delta run would compare against: the last completed "
        "run, its head commits and its Jira watermark.",
        Empty,
        tier="read",
    )
    def delta_status(args: Empty, log: Logger) -> Result[Any]:
        return delta_service.baseline_status()
