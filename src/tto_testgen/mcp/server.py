"""M1 McpServer - the toolchain's surface to the Copilot agent.

stdio only, no network listener (NFR-SEC-02). Every input is validated against a
Pydantic schema before any handler runs (NFR-SEC-03). No exception crosses the
boundary: everything becomes a structured Result the agent can branch on without
parsing prose (NFR-SEC-07).

Requirements: C-10, US-ENB-02.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from tto_testgen.platform.logging import Logger, new_correlation_id
from tto_testgen.platform.result import (
    Err,
    ErrorCode,
    Ok,
    Result,
    err,
    sanitise,
)

#: A tool handler receives validated arguments and a request-scoped logger.
Handler = Callable[[BaseModel, Logger], Result[Any]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    schema: type[BaseModel]
    handler: Handler
    tier: str  # "read" | "write"

    def json_schema(self) -> dict[str, Any]:
        return self.schema.model_json_schema()


@dataclass(slots=True)
class ToolRegistry:
    """M2. Two tiers, deliberately asymmetric.

    Write tools are coarse and transactional: one call performs one complete unit
    of work and owns its transaction, because writes carry the invariants and
    partial failure does real damage. Read tools are fine-grained: they carry no
    invariants and benefit from flexibility.
    """

    tools: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self.tools:
            raise ValueError(f"Tool {spec.name!r} is already registered")
        if spec.tier not in ("read", "write"):
            raise ValueError(f"Unknown tier {spec.tier!r} for tool {spec.name!r}")
        self.tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self.tools.get(name)

    def by_tier(self, tier: str) -> list[ToolSpec]:
        return sorted(
            (t for t in self.tools.values() if t.tier == tier), key=lambda t: t.name
        )

    def manifest(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "tier": spec.tier,
                "inputSchema": spec.json_schema(),
            }
            for spec in sorted(self.tools.values(), key=lambda t: t.name)
        ]


def _result_payload(result: Result[Any], workspace_root: Path | None) -> dict[str, Any]:
    """Convert a Result into the response the agent receives.

    The error code is the actionable part: `REJECTED_*` means fix the input,
    `FAILED_*` means the system had a problem. The agent branches on the code, not
    on the message text.
    """
    if isinstance(result, Ok):
        value = result.value
        if hasattr(value, "to_dict"):
            value = value.to_dict()
        elif hasattr(value, "__dict__") and not isinstance(value, (dict, list, str, int, float, bool)):
            value = {
                k: v for k, v in vars(value).items() if not k.startswith("_")
            }
        return {"ok": True, "value": value}
    return {
        "ok": False,
        "code": result.code.value,
        "family": "rejected" if result.is_rejection else "failed",
        "message": sanitise(result.message, workspace_root),
        "remediation": result.remediation,
        "context": result.context,
    }


class McpServer:
    """Dispatches validated tool calls and guarantees a structured response."""

    def __init__(
        self,
        registry: ToolRegistry,
        logger: Logger,
        *,
        workspace_root: Path | None = None,
    ) -> None:
        self._registry = registry
        self._logger = logger
        self._workspace_root = workspace_root

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    def list_tools(self) -> list[dict[str, Any]]:
        return self._registry.manifest()

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Validate, dispatch, and return a structured payload. Never raises."""
        correlation_id = new_correlation_id()
        log = self._logger.bind(correlation_id=correlation_id, tool=name)

        spec = self._registry.get(name)
        if spec is None:
            log.warning("unknown tool requested")
            return _result_payload(
                err(
                    ErrorCode.FAILED_INTERNAL,
                    f"Unknown tool: {name}",
                    remediation="Call list_tools to see the available tools.",
                ),
                self._workspace_root,
            )

        try:
            validated = spec.schema.model_validate(arguments or {})
        except ValidationError as exc:
            # Schema validation runs before any logic, so a malformed payload never
            # reaches a handler (NFR-SEC-03).
            log.warning("input failed schema validation", errors=exc.error_count())
            return _result_payload(
                err(
                    ErrorCode.FAILED_INTERNAL,
                    f"Invalid arguments for {name}: {_summarise(exc)}",
                    remediation="Correct the arguments to match the tool's inputSchema.",
                ),
                self._workspace_root,
            )

        log.info("tool invoked", tier=spec.tier)
        try:
            result = spec.handler(validated, log)
        except Exception as exc:  # noqa: BLE001 - the global boundary handler
            # Nothing propagates past here. An unhandled exception becomes a
            # FAILED_INTERNAL the agent can respond to, with no stack detail and no
            # path outside the workspace.
            log.error("tool raised", error=type(exc).__name__)
            return _result_payload(
                err(ErrorCode.FAILED_INTERNAL, f"{type(exc).__name__}: {exc}"),
                self._workspace_root,
            )

        if isinstance(result, Err):
            log.warning("tool returned failure", code=result.code.value)
        return _result_payload(result, self._workspace_root)

    def serve_stdio(self) -> None:  # pragma: no cover - transport wiring
        """Run over stdio, speaking the real Model Context Protocol.

        Bridges to `mcp`'s own async server loop with `anyio.run` - list_tools() and
        call() above stay plain synchronous methods, tested and called directly by
        every other test in this suite; only this function needs to know an event
        loop exists at all. Every actual request is one call, sequential (a single
        agent, one stdio pipe), so a blocking call inside the handler (SQLite, a
        subprocess wait for an MCP client call) costs nothing here that a real
        concurrent server would pay for.
        """
        import anyio

        anyio.run(self._serve_mcp)

    async def _serve_mcp(self) -> None:  # pragma: no cover - transport wiring
        import mcp.types as types
        from mcp.server.lowlevel import Server
        from mcp.server.stdio import stdio_server

        app: Server = Server("tto-testgen", version="0.1.0")

        @app.list_tools()
        async def _list_tools() -> list[types.Tool]:
            return [
                types.Tool(
                    name=spec["name"],
                    description=f"[{spec['tier']}] {spec['description']}",
                    inputSchema=spec["inputSchema"],
                )
                for spec in self.list_tools()
            ]

        @app.call_tool(validate_input=False)
        async def _call_tool(name: str, arguments: dict[str, Any]) -> "types.CallToolResult":
            # validate_input=False: McpServer.call() already validates against the
            # same pydantic schema and returns a structured, agent-branchable error
            # on failure (NFR-SEC-03) - a second, jsonschema-based validation layer
            # here would only risk rejecting something pydantic's defaults accept.
            payload = self.call(name, arguments or {})
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(payload, default=str))],
                # The agent branches on payload["code"], not message text (see
                # _result_payload's docstring) - structuredContent carries that
                # contract unchanged, rather than reshaping it into something new.
                structuredContent=payload,
                isError=not payload.get("ok", False),
            )

        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())


def _summarise(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors()[:3]:
        location = ".".join(str(p) for p in error["loc"]) or "(root)"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)
