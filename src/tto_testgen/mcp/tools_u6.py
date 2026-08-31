"""U6's tools - handover assembly and verification.

Two tools, both named in U7's chat modes before this unit existed. **Neither pushes,
branches, nor writes CI configuration**: the service behind them has no such method,
so the constraint holds by absence rather than by the tools declining to expose it
(FR-HND-04).

Requirements: FR-HND-01 to FR-HND-06.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from tto_testgen.mcp.server import ToolRegistry, ToolSpec
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import Ok, Result, ok


class Empty(BaseModel):
    pass


def register_u6_tools(registry: ToolRegistry, handover_service: Any) -> None:
    def tool(name: str, description: str, schema: type[BaseModel]):
        def decorator(fn):
            registry.register(ToolSpec(name, description, schema, fn, "write"))
            return fn

        return decorator

    @tool(
        "handover_assemble",
        "Assemble the handover: add .gitignore, generate the lockfile if npm is "
        "available, write the manifest, then verify. Structural checks always run; "
        "compilation and enumeration run only when Node is present and are reported "
        "as skipped otherwise. Does not push, branch, or configure Jenkins - that "
        "stays with the operator.",
        Empty,
    )
    def handover_assemble(args: Empty, log: Logger) -> Result[Any]:
        result = handover_service.assemble()
        if not isinstance(result, Ok):
            return result
        return ok(result.value.to_dict())

    @tool(
        "handover_verify",
        "Re-run every handover check without rewriting the manifest. Nothing is "
        "cached between runs, so a fix is reflected immediately.",
        Empty,
    )
    def handover_verify(args: Empty, log: Logger) -> Result[Any]:
        result = handover_service.verify()
        if not isinstance(result, Ok):
            return result
        return ok(result.value.to_dict())
