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

from tto_testgen.domain.apimodel import CodeEndpoint
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
        api_model_deriver: Callable[[str], Result[tuple[list[CodeEndpoint], list[str]]]]
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
        "Derive the API model from code. Endpoints come from a deterministic scan "
        "of the repository; an OpenAPI/Swagger spec's file path is reported when "
        "bitbucket_endpoints finds one, but tt-bitbucket-mcp has no tool that "
        "returns a file's raw content, so a spec's shapes are not auto-derived - "
        "open the reported path directly to compare it against the code.",
        ApiModelDerive,
    )
    def api_model_derive(args: ApiModelDerive, log: Logger) -> Result[Any]:
        code: list[CodeEndpoint] = []
        spec_files: list[str] = []

        for slug in args.repo_slugs:
            outcome = api_model_deriver(slug)
            if not isinstance(outcome, Ok):
                return outcome
            endpoints, files = outcome.value
            code.extend(endpoints)
            spec_files.extend(f"{slug}:{path}" for path in files)

        result = analysis_service.derive_api_model(
            code, [], feature_slug=args.feature_slug
        )
        if isinstance(result, Ok) and spec_files:
            result.value["spec_files_found"] = spec_files
        return result

    @tool(
        "ui_model_upsert",
        "Store screens and elements from live exploration. A locator is verified "
        "only when confirmed against the running application.",
        UiModelUpsert,
    )
    def ui_model_upsert(args: UiModelUpsert, log: Logger) -> Result[Any]:
        result = analysis_service.upsert_ui_model(args.model_dump())
        return ok(result.value.to_dict()) if isinstance(result, Ok) else result


