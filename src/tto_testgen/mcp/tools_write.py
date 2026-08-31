"""M2 write tier - coarse, transactional.

One call performs one complete unit of work and owns its transaction. Writes carry
the invariants and partial failure does real damage, so they belong in a single
transactional call rather than a sequence the agent has to get right across a
context boundary.

U1 registered `unit_begin`, `unit_complete` and `stage_approve` as thin wrappers over
the repository. U7 rewires them to delegate to S10 RunStateService, which owns lease
policy and gate evaluation. Tool names and schemas are unchanged, so the agent layer
written against them stays valid - the change is entirely behind the surface.

The remaining 17 write tools are registered by the units that own their services.

Requirements: US-ENB-02, FR-BAT-01 to FR-BAT-07.
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any, Callable

from pydantic import BaseModel, Field

from tto_testgen.domain.gates import Role
from tto_testgen.domain.model import StageName
from tto_testgen.mcp.server import ToolRegistry, ToolSpec
from tto_testgen.platform.logging import Logger, UnitMetrics
from tto_testgen.platform.result import ErrorCode, Ok, Result, err, ok
from tto_testgen.services.runstate import RunStateService

ConnFactory = Callable[[], sqlite3.Connection]


class UnitBegin(BaseModel):
    unit_ref: str = Field(min_length=1, description="Feature slug or unit name")
    stage: str = Field(description="ingest|analyse|requirements|coverage|cases|automation|handover")
    regenerate: bool = Field(
        default=False,
        description="Re-run a completed unit. Required explicitly; never assumed.",
    )


class UnitComplete(BaseModel):
    lease_id: str = Field(min_length=1)
    unit_ref: str = Field(min_length=1)
    stage: str
    duration_ms: int = Field(default=0, ge=0)
    artefacts_consumed: int = Field(default=0, ge=0)
    cases_produced: int = Field(default=0, ge=0)
    failures: int = Field(default=0, ge=0)


class StageApprove(BaseModel):
    unit_ref: str = Field(min_length=1)
    stage: str
    approver: str = Field(min_length=1)
    role: str = Field(description="test-analyst|test-automation-engineer|test-lead")
    content_hash: str | None = None


class UnitFail(BaseModel):
    lease_id: str = Field(min_length=1)
    unit_ref: str = Field(min_length=1)
    stage: str
    reason: str = Field(min_length=1)


class UnitHeartbeat(BaseModel):
    lease_id: str = Field(min_length=1)
    unit_ref: str = Field(min_length=1)
    stage: str


def _parse_stage(value: str) -> StageName | None:
    try:
        return StageName(value)
    except ValueError:
        return None


def _stage_error(value: str) -> Result[Any]:
    return err(
        ErrorCode.FAILED_INTERNAL,
        f"Unknown stage: {value}",
        remediation=f"Use one of: {', '.join(s.value for s in StageName)}.",
    )


def _parse_role(value: str) -> Role | None:
    """An unrecognised role is invalid, not unauthorised.

    U1 accepted this as a free string. A typo such as `testlead` would have failed
    the coverage restriction closed - the right outcome for the wrong reason, telling
    the operator they lack authority when in fact they mistyped.
    """
    try:
        return Role(value)
    except ValueError:
        return None


def register_write_tools(
    registry: ToolRegistry, service: RunStateService
) -> None:
    """Register the write-tier tools U7 owns, delegating to S10."""

    def tool(name: str, description: str, schema: type[BaseModel]):
        def decorator(fn):
            registry.register(ToolSpec(name, description, schema, fn, "write"))
            return fn

        return decorator

    @tool(
        "unit_begin",
        "Claim a unit and stage for work. Refuses a completed unit unless "
        "regenerate is set explicitly, and reports lease staleness when one is held.",
        UnitBegin,
    )
    def unit_begin(args: UnitBegin, log: Logger) -> Result[Any]:
        stage = _parse_stage(args.stage)
        if stage is None:
            return _stage_error(args.stage)
        result = service.begin_unit(
            args.unit_ref, stage, regenerate=args.regenerate, holder=log._context.get(
                "correlation_id"
            ) if hasattr(log, "_context") else None,
        )
        if isinstance(result, Ok):
            log.info("unit claimed", unit_ref=args.unit_ref, stage=stage.value)
        return result

    @tool(
        "unit_complete",
        "Mark a claimed unit complete. Requires the lease issued by unit_begin.",
        UnitComplete,
    )
    def unit_complete(args: UnitComplete, log: Logger) -> Result[Any]:
        stage = _parse_stage(args.stage)
        if stage is None:
            return _stage_error(args.stage)
        metrics = UnitMetrics(
            duration_ms=args.duration_ms,
            artefacts_consumed=args.artefacts_consumed,
            cases_produced=args.cases_produced,
            failures=args.failures,
        )
        result = service.complete_unit(
            args.lease_id, args.unit_ref, stage,
            {
                "duration_ms": metrics.duration_ms,
                "artefacts_consumed": metrics.artefacts_consumed,
                "cases_produced": metrics.cases_produced,
                "failures": metrics.failures,
            },
        )
        if isinstance(result, Ok):
            log.record_metrics(args.unit_ref, stage.value, metrics)
            return ok({"unit_ref": args.unit_ref, "stage": stage.value, "state": "completed"})
        return result

    @tool("unit_fail", "Record a unit as failed, with a reason.", UnitFail)
    def unit_fail(args: UnitFail, log: Logger) -> Result[Any]:
        stage = _parse_stage(args.stage)
        if stage is None:
            return _stage_error(args.stage)
        result = service.fail_unit(args.lease_id, args.unit_ref, stage, args.reason)
        if isinstance(result, Ok):
            log.warning("unit failed", unit_ref=args.unit_ref, stage=stage.value)
            return ok({"unit_ref": args.unit_ref, "stage": stage.value, "state": "failed"})
        return result

    @tool(
        "unit_heartbeat",
        "Refresh the lease on a claimed unit, so a long-running unit is not "
        "reported stale.",
        UnitHeartbeat,
    )
    def unit_heartbeat(args: UnitHeartbeat, log: Logger) -> Result[Any]:
        stage = _parse_stage(args.stage)
        if stage is None:
            return _stage_error(args.stage)
        result = service.heartbeat(args.lease_id, args.unit_ref, stage)
        if isinstance(result, Ok):
            return ok({"unit_ref": args.unit_ref, "stage": stage.value, "heartbeat": "refreshed"})
        return result

    @tool(
        "stage_approve",
        "Record a human gate approval. Binds to the content approved, so a later "
        "edit invalidates it.",
        StageApprove,
    )
    def stage_approve(args: StageApprove, log: Logger) -> Result[Any]:
        stage = _parse_stage(args.stage)
        if stage is None:
            return _stage_error(args.stage)
        role = _parse_role(args.role)
        if role is None:
            return err(
                ErrorCode.FAILED_INTERNAL,
                f"Unknown role: {args.role}",
                remediation=f"Use one of: {', '.join(r.value for r in Role)}.",
            )
        result = service.approve_stage(
            args.unit_ref, stage, args.approver, role, args.content_hash
        )
        if isinstance(result, Ok):
            log.info("stage approved", unit_ref=args.unit_ref, stage=stage.value,
                     approver=args.approver)
        else:
            log.warning("approval refused", unit_ref=args.unit_ref, stage=stage.value,
                        role=role.value, code=result.code.value)
        return result
