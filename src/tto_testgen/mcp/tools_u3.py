"""U3's write-tier tools.

Four tools, all named in U7's chat modes before this unit existed.

Requirements: FR-TRQ-01 to -05, FR-COV-01 to -07, FR-TRC-02 to -04.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from tto_testgen.domain.gates import Role
from tto_testgen.mcp.server import ToolRegistry, ToolSpec
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import ErrorCode, Ok, Result, err, ok


class RequirementsUpsert(BaseModel):
    feature_slug: str = Field(min_length=1)
    repo_slug: str | None = Field(
        default=None,
        description="Enables commit-derived Jira keys for behaviour with no direct link",
    )
    requirements: list[dict[str, Any]] = Field(min_length=1)


class CoverageBuild(BaseModel):
    feature_slug: str = Field(min_length=1)
    technique_inputs: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Per requirement id: valid_classes, boundaries, decision_rules, etc.",
    )


class CoverageApprove(BaseModel):
    feature_slug: str = Field(min_length=1)
    approver: str = Field(min_length=1)
    role: str = Field(description="test-analyst|test-automation-engineer|test-lead")


class CoverageReduce(BaseModel):
    feature_slug: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    decided_by: str = Field(min_length=1)
    override: bool = Field(
        default=False,
        description="Required for a high or critical risk feature. The contradiction is recorded.",
    )


def register_u3_tools(
    registry: ToolRegistry, requirement_service: Any, coverage_service: Any
) -> None:
    def tool(name: str, description: str, schema: type[BaseModel]):
        def decorator(fn):
            registry.register(ToolSpec(name, description, schema, fn, "write"))
            return fn

        return decorator

    @tool(
        "requirements_upsert",
        "Store atomic testable requirements for one feature. Accepted entirely or "
        "not at all, with every failure reported together. Behaviour that cannot be "
        "traced to a Jira key becomes a gap, not a rejection.",
        RequirementsUpsert,
    )
    def requirements_upsert(args: RequirementsUpsert, log: Logger) -> Result[Any]:
        result = requirement_service.upsert_requirements(
            args.feature_slug,
            {"requirements": args.requirements, "repo_slug": args.repo_slug},
        )
        if not isinstance(result, Ok):
            return result
        report = result.value
        if not report.ok:
            return err(
                ErrorCode.REJECTED_INVALID_STEPS,
                f"{len(report.rejections)} requirement(s) rejected",
                remediation=(
                    "Each requirement must state a single behaviour, carry a known "
                    "category, and cite at least one ingested source artefact. Pass "
                    "force_atomic=true on a requirement if the atomicity check is wrong."
                ),
                rejections=report.rejections,
            )
        return ok(report.to_dict())

    @tool(
        "coverage_build",
        "Build the coverage model for one feature. Reports the planned yield with "
        "its derivation, and whether a prior approval has been invalidated.",
        CoverageBuild,
    )
    def coverage_build(args: CoverageBuild, log: Logger) -> Result[Any]:
        result = coverage_service.build_model(args.feature_slug, args.technique_inputs)
        if not isinstance(result, Ok):
            return result
        build = result.value
        if build.approval_invalidated:
            log.warning(
                "coverage approval invalidated", feature=args.feature_slug,
                previous_approver=build.previous_approver,
            )
        return ok(build.to_dict())

    @tool(
        "coverage_approve",
        "Approve the coverage baseline for one feature. Test Lead only. The "
        "approval binds to the model's content, so a later change invalidates it.",
        CoverageApprove,
    )
    def coverage_approve(args: CoverageApprove, log: Logger) -> Result[Any]:
        try:
            role = Role(args.role)
        except ValueError:
            # An invalid role and an unauthorised one are different. A typo should
            # be refused as a typo, not read as a lack of authority.
            return err(
                ErrorCode.FAILED_INTERNAL,
                f"Unknown role: {args.role}",
                remediation=f"Use one of: {', '.join(r.value for r in Role)}.",
            )
        return coverage_service.approve_baseline(args.feature_slug, args.approver, role)

    @tool(
        "coverage_reduce",
        "Mark a feature reduced-depth. Records both the full and reduced yields, "
        "and invalidates any prior approval. A high-risk feature needs override=true.",
        CoverageReduce,
    )
    def coverage_reduce(args: CoverageReduce, log: Logger) -> Result[Any]:
        result = coverage_service.apply_reduction(
            args.feature_slug, args.reason, args.decided_by, override=args.override
        )
        return ok(result.value.to_dict()) if isinstance(result, Ok) else result
