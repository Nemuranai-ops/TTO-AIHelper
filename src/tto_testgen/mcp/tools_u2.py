"""U2's write-tier tools.

Four tools, all named in U7's chat modes before this unit existed. U7's consistency
check listed them as "future" and will now confirm they are real.

Kept in their own module rather than appended to `tools_write.py`: that file is U7's,
and eight units appending to one file is how a merge conflict becomes a weekly event.

Requirements: FR-ING-01 to FR-ING-10, FR-ANA-01 to FR-ANA-08.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from tto_testgen.domain.apimodel import AuthRequirement, CodeEndpoint, SpecEndpoint
from tto_testgen.mcp.server import ToolRegistry, ToolSpec
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import ErrorCode, Ok, Result, err, ok


class IngestResources(BaseModel):
    manifest_path: str | None = Field(
        default=None, description="Defaults to resources.md in the workspace root"
    )


class AnalysisUpsert(BaseModel):
    features: list[dict[str, Any]] = Field(default_factory=list)
    journeys: list[dict[str, Any]] = Field(default_factory=list)
    business_rules: list[dict[str, Any]] = Field(default_factory=list)
    unassigned_artefact_ids: list[str] = Field(default_factory=list)


class ApiModelDerive(BaseModel):
    repo_slugs: list[str] = Field(min_length=1)
    feature_slug: str | None = None


class UiModelUpsert(BaseModel):
    screens: list[dict[str, Any]] = Field(min_length=1)


def register_u2_tools(
    registry: ToolRegistry,
    ingestion_runner: Any,
    analysis_service: Any,
    api_model_deriver: Any,
) -> None:
    """`ingestion_runner` and `api_model_deriver` are callables, not live objects.

    Both need a live MCP session to Atlassian/Bitbucket, and that session is meant
    to last one ingestion run, not the life of the server (L6's own docstring).
    Accepting callables lets composition.py open a fresh session per call and
    close it in a finally, rather than this module holding one open indefinitely
    or reaching into composition's wiring itself.

        ingestion_runner: Callable[[str | None], Result[IngestionReport]]
        api_model_deriver: Callable[[str], Result[tuple[list[CodeEndpoint], dict | None]]]
    """
    def tool(name: str, description: str, schema: type[BaseModel]):
        def decorator(fn):
            registry.register(ToolSpec(name, description, schema, fn, "write"))
            return fn

        return decorator

    @tool(
        "ingest_resources",
        "Ingest every resource declared in resources.md. Reports successes, "
        "unchanged skips, failures and unclassifiable entries together.",
        IngestResources,
    )
    def ingest_resources(args: IngestResources, log: Logger) -> Result[Any]:
        result = ingestion_runner(args.manifest_path)
        if isinstance(result, Ok):
            report = result.value
            log.info("ingestion complete", **report.totals)
            return ok(report.to_dict())
        return result

    @tool(
        "analysis_upsert",
        "Store the reasoned application model: features, journeys and business "
        "rules. Every feature must cite at least one ingested source artefact.",
        AnalysisUpsert,
    )
    def analysis_upsert(args: AnalysisUpsert, log: Logger) -> Result[Any]:
        result = analysis_service.upsert_feature_model(args.model_dump())
        if isinstance(result, Ok):
            report = result.value
            if not report.ok:
                # Rejections are returned as a successful call carrying failures, so
                # the agent sees every problem at once rather than one per round trip.
                return err(
                    ErrorCode.REJECTED_NO_JIRA_KEY,
                    f"{len(report.rejections)} feature(s) rejected",
                    remediation=(
                        "Every feature must cite at least one ingested source "
                        "artefact, and the hierarchy must be acyclic."
                    ),
                    rejections=report.rejections,
                )
            return ok(report.to_dict())
        return result

    @tool(
        "api_model_derive",
        "Derive the API model from code and any OpenAPI spec. Deterministic: the "
        "code decides which endpoints exist, the spec decides their shapes.",
        ApiModelDerive,
    )
    def api_model_derive(args: ApiModelDerive, log: Logger) -> Result[Any]:
        code: list[CodeEndpoint] = []
        spec: list[SpecEndpoint] = []

        for slug in args.repo_slugs:
            outcome = api_model_deriver(slug)
            if not isinstance(outcome, Ok):
                return outcome
            endpoints, openapi = outcome.value
            code.extend(endpoints)
            if openapi:
                spec.extend(_spec_endpoints(openapi))

        return analysis_service.derive_api_model(
            code, spec, feature_slug=args.feature_slug
        )

    @tool(
        "ui_model_upsert",
        "Store screens and elements from live exploration. A locator is verified "
        "only when confirmed against the running application.",
        UiModelUpsert,
    )
    def ui_model_upsert(args: UiModelUpsert, log: Logger) -> Result[Any]:
        result = analysis_service.upsert_ui_model(args.model_dump())
        return ok(result.value.to_dict()) if isinstance(result, Ok) else result


def _spec_endpoints(document: dict[str, Any]) -> list[SpecEndpoint]:
    """Read an OpenAPI document by plain traversal.

    No spec library: a document that fails formal validation is still evidence of
    intended shapes, and BR-U2-5 already treats the spec as advisory about shapes and
    never authoritative about existence. A validator would let us discard exactly the
    spec whose disagreement with the code is worth recording.

    Cross-document `$ref` is left unresolved rather than fetched - resolving it would
    mean an HTTP request to a URL chosen by the spec's author.
    """
    endpoints: list[SpecEndpoint] = []
    global_security = bool(document.get("security"))

    for route, operations in (document.get("paths") or {}).items():
        if not isinstance(operations, dict):
            continue
        for method, operation in operations.items():
            if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
                continue
            if not isinstance(operation, dict):
                continue

            responses = operation.get("responses") or {}
            codes = tuple(
                sorted(int(c) for c in responses if str(c).isdigit())
            )
            has_security = "security" in operation
            secured = bool(operation.get("security")) if has_security else global_security

            endpoints.append(SpecEndpoint(
                method=method.upper(),
                route=route,
                request_shape=_request_shape(operation),
                response_shapes={str(k): v for k, v in responses.items()},
                status_codes=codes,
                auth_requirement=(
                    AuthRequirement.REQUIRED if secured
                    else AuthRequirement.NONE if has_security or "security" in document
                    else AuthRequirement.UNKNOWN
                ),
            ))
    return endpoints


def _request_shape(operation: dict[str, Any]) -> dict[str, Any] | None:
    body = operation.get("requestBody") or {}
    content = body.get("content") or {}
    for media_type in ("application/json", *content):
        if media_type in content:
            schema = content[media_type].get("schema")
            if schema is not None:
                return schema
    parameters = operation.get("parameters") or []
    if parameters:
        return {p.get("name"): p.get("schema", {}) for p in parameters if p.get("name")}
    return None
