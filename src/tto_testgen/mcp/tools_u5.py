"""U5's tools - automation emission and its report.

Two tools. `automation_emit` writes; `automation_report` reads, and is registered on
the write tier alongside it only because both are served by the same service - the
registry's tier controls approval, not read/write semantics.

Requirements: FR-AUT-01 to FR-AUT-11.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from tto_testgen.mcp.server import ToolRegistry, ToolSpec
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import ErrorCode, Ok, Result, err, ok


class AutomationEmit(BaseModel):
    feature_slug: str = Field(min_length=1)
    include_scaffold: bool = Field(
        default=True,
        description=(
            "Write the project-level files (package.json, playwright.config.ts, "
            "tsconfig.json, .env.example, README.md, fixtures/auth.ts). They are "
            "skipped automatically once you have edited them."
        ),
    )


class AutomationReport(BaseModel):
    feature_slug: str | None = Field(
        default=None, description="Omit for the whole suite."
    )


def register_u5_tools(registry: ToolRegistry, automation_service: Any) -> None:
    def tool(name: str, description: str, schema: type[BaseModel]):
        def decorator(fn):
            registry.register(ToolSpec(name, description, schema, fn, "write"))
            return fn

        return decorator

    @tool(
        "automation_emit",
        "Generate the Playwright project for one feature. Only cases classified "
        "automatable produce a test; needs-review and manual-only cases are listed "
        "with the classifier's reason. A literal credential or environment-specific "
        "URL refuses the whole emission. Files you have edited are skipped and "
        "reported, never overwritten.",
        AutomationEmit,
    )
    def automation_emit(args: AutomationEmit, log: Logger) -> Result[Any]:
        result = automation_service.emit(
            args.feature_slug, include_scaffold=args.include_scaffold
        )
        if not isinstance(result, Ok):
            return result
        report = result.value
        if report.refusals:
            return err(
                ErrorCode.REJECTED_PERSONAL_DATA,
                f"{len(report.refusals)} value(s) may not be written as literals; "
                "nothing was generated",
                remediation=(
                    "Replace each value named below with an environment variable and "
                    "document it in .env.example, then re-run. The generated project "
                    "is pushed to a repository, so a literal credential there is a "
                    "disclosure rather than a style problem."
                ),
                rejections=report.refusals,
            )
        return ok(report.to_dict())

    @tool(
        "automation_report",
        "Generated tests against the corpus, including how many rest on unverified "
        "or fragile locators. At-risk means unconfirmed, not wrong.",
        AutomationReport,
    )
    def automation_report(args: AutomationReport, log: Logger) -> Result[Any]:
        return automation_service.automation_report(args.feature_slug)
