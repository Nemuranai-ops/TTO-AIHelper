"""The composition root - the only module that knows both a protocol and its
implementation.

Everything else depends on protocols. Isolating the wiring here is what lets every
service be constructed in a test with in-memory fakes, and every domain component
need no construction at all. That is the precondition for the property suite.

Requirements: NFR-MNT-01, C-10, NFR-SEC-01, NFR-SEC-02.
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from tto_testgen.adapters.sqlite.backup import backup_before
from tto_testgen.adapters.sqlite.connection import ConnectionSettings, open_checked
from tto_testgen.adapters.sqlite.schema import current_version, ensure_schema, pending
from tto_testgen.mcp.server import McpServer, ToolRegistry
from tto_testgen.mcp.tools_read import register_read_tools
from tto_testgen.mcp.tools_write import register_write_tools
from tto_testgen.platform import config as config_module
from tto_testgen.platform.logging import Logger, configure
from tto_testgen.platform.result import Err, ErrorCode, Ok, Result, err, ok
from tto_testgen.services.analysis import AnalysisService
from tto_testgen.services.coverage import CoverageService
from tto_testgen.services.automation import AutomationService
from tto_testgen.services.generation import GenerationService
from tto_testgen.services.delta import DeltaService
from tto_testgen.services.handover import HandoverService
from tto_testgen.services.reporting import ReportingService
from tto_testgen.services.ingestion import IngestionService
from tto_testgen.services.requirements import TestableRequirementService
from tto_testgen.services.runstate import RunStateService


class _RequirementServiceWithLiveBitbucket:
    """Satisfies the same interface TestableRequirementService already exposes -
    upsert_requirements(feature_slug, payload, run_id=None) - but opens a fresh
    Bitbucket MCP session only when a call actually needs commit-derived keys
    (payload carries a repo_slug), and only for that one call.

    Most calls cite a direct Jira link and never touch this path at all: the
    common case stays exactly as fast as it already was, and the session - which
    is documented to last one call, not the server's life (L6) - is never held
    open across calls that do not need it.
    """

    def __init__(self, uow_factory: Any, config: Any, logger: Any) -> None:
        self._uow_factory = uow_factory
        self._config = config
        self._logger = logger
        self._no_bitbucket = TestableRequirementService(uow_factory, None, logger)

    def upsert_requirements(
        self, feature_slug: str, payload: dict, run_id: int | None = None
    ):
        if not payload.get("repo_slug"):
            return self._no_bitbucket.upsert_requirements(feature_slug, payload, run_id)

        from tto_testgen.adapters.mcp_client import McpClientSession, servers_from_config
        from tto_testgen.adapters.sources.bitbucket import BitbucketSourceAdapter

        with McpClientSession(servers_from_config(self._config), self._logger) as session:
            service = TestableRequirementService(
                self._uow_factory, BitbucketSourceAdapter(session), self._logger,
            )
            return service.upsert_requirements(feature_slug, payload, run_id)


class _ChangeDetectorWithLiveBitbucket:
    """Same interface ChangeDetector already exposes - detect(baseline) - but opens a
    fresh Bitbucket MCP session only for the call itself, per L6's one-call-per-session
    rule. Same reasoning as _RequirementServiceWithLiveBitbucket above: one delta_detect
    call may check several repositories, and all of that is one logical operation, so
    one session covers it rather than one per repository.

    Jira stays None here - U8-NFR-... aside, wiring it needs AtlassianSourceAdapter to
    capture an issue's updated timestamp, which it does not currently do (its
    SourceRecord.metadata has no updated_at field at all). That is a separate,
    unfixed gap: _detect_jira no-ops on a None jira source exactly as it always has.
    """

    def __init__(self, config: Any, logger: Any, *, max_changes: int) -> None:
        self._config = config
        self._logger = logger
        self._max_changes = max_changes

    def detect(self, baseline: Any) -> Any:
        from tto_testgen.adapters.change_detector import ChangeDetector
        from tto_testgen.adapters.mcp_client import McpClientSession, servers_from_config
        from tto_testgen.adapters.sources.bitbucket import BitbucketSourceAdapter

        with McpClientSession(servers_from_config(self._config), self._logger) as session:
            detector = ChangeDetector(
                BitbucketSourceAdapter(session), None, self._logger,
                max_changes=self._max_changes,
            )
            return detector.detect(baseline)


@dataclass(slots=True)
class Application:
    config: config_module.Config
    logger: Logger
    connection: sqlite3.Connection
    server: McpServer
    run_state: RunStateService
    analysis: AnalysisService
    coverage: CoverageService
    # _RequirementServiceWithLiveBitbucket, not TestableRequirementService itself -
    # it satisfies the same upsert_requirements(...) interface, opening a live
    # Bitbucket session only for the calls that actually name a repo_slug.
    requirements: Any
    generation: GenerationService
    automation: AutomationService
    handover: HandoverService
    reporting: ReportingService
    delta: DeltaService

    def close(self) -> None:
        self.connection.close()


def build(
    workspace_root: Path | None = None, environ: dict[str, str] | None = None
) -> Result[Application]:
    """Wire the application. Fails fast, naming what is wrong.

    Order matters: configuration first, so a missing credential surfaces before a
    database file is created; then the connection with its PRAGMAs asserted; then a
    backup if a migration is pending, because OD-01 requires one before any
    schema-changing operation.
    """
    config_result = config_module.load(workspace_root, environ)
    if isinstance(config_result, Err):
        return config_result
    config = config_result.value

    logger = configure(config.log_level).bind(component="composition")

    connection_result = open_checked(
        ConnectionSettings(
            db_path=config.db_path, busy_timeout_ms=config.busy_timeout_ms
        )
    )
    if isinstance(connection_result, Err):
        return connection_result
    connection = connection_result.value

    if pending(connection):
        # U1-NFR-REC-01: back up before any schema-changing operation. Skipped
        # silently on a brand-new database, where there is nothing to lose.
        if current_version(connection) > 0:
            backup = backup_before(connection, "pre-migration", config.backup_dir)
            if isinstance(backup, Err):
                return backup
            logger.info("pre-migration backup taken", path=backup.value.path.name)

    migration = ensure_schema(connection)
    if isinstance(migration, Err):
        return migration
    if migration.value.applied:
        logger.info(
            "schema migrated",
            applied=migration.value.applied,
            version=migration.value.to_version,
        )

    from tto_testgen.adapters.sqlite.repositories import unit_of_work

    run_state = RunStateService(lambda: unit_of_work(connection))
    analysis = AnalysisService(lambda: unit_of_work(connection), logger)
    coverage = CoverageService(lambda: unit_of_work(connection), run_state, logger)

    registry = ToolRegistry()
    register_read_tools(registry, lambda: connection)
    register_write_tools(registry, run_state)

    # U2. Atlassian and Bitbucket need a live MCP session, and that session is
    # meant to last one call, not the life of the server (L6's own docstring) - so
    # ingest_resources and api_model_derive each open one, do their work, and close
    # it, rather than this module holding two subprocesses open indefinitely.
    from tto_testgen.adapters.mcp_client import McpClientSession, servers_from_config
    from tto_testgen.adapters.sources.atlassian import AtlassianSourceAdapter
    from tto_testgen.adapters.sources.bitbucket import BitbucketSourceAdapter
    from tto_testgen.adapters.sources.dispatch import build_source_for
    from tto_testgen.adapters.sources.manifest import ResourceManifestAdapter
    from tto_testgen.mcp.tools_u2 import register_u2_tools
    from tto_testgen.services.ingestion import IngestionService

    def run_ingestion(manifest_path: str | None):
        path = Path(manifest_path) if manifest_path else config.workspace_root / "resources.md"
        with McpClientSession(servers_from_config(config), logger) as session:
            atlassian = AtlassianSourceAdapter(session)
            bitbucket = BitbucketSourceAdapter(session)
            service = IngestionService(
                lambda: unit_of_work(connection),
                ResourceManifestAdapter(path, config.workspace_root),
                build_source_for(atlassian, bitbucket, config.workspace_root),
                logger,
            )
            return service.ingest_resources()

    def derive_api_model_endpoints(repo_slug: str):
        with McpClientSession(servers_from_config(config), logger) as session:
            return BitbucketSourceAdapter(session).endpoints(repo_slug)

    register_u2_tools(registry, run_ingestion, analysis, derive_api_model_endpoints)

    # U3's requirement service needs the same kind of Bitbucket adapter as U2, for
    # commit-derived Jira keys (US-TRC-02) - opened per call, not held open, same
    # reasoning as run_ingestion above. Coverage needs no external source and is
    # registered here regardless.
    from tto_testgen.mcp.tools_u3 import register_u3_tools

    requirements = _RequirementServiceWithLiveBitbucket(
        lambda: unit_of_work(connection), config, logger
    )
    register_u3_tools(registry, requirements, coverage)

    # U4. The renderer is the only adapter this module hands to a service directly;
    # the service knows it through an emitter port, and composition is the one
    # module permitted to know both sides.
    from tto_testgen.adapters.view_renderer import ViewRenderer
    from tto_testgen.mcp.tools_u4 import register_u4_tools

    generation = GenerationService(
        lambda: unit_of_work(connection),
        run_state,
        ViewRenderer(config.views_root),
        logger,
        max_batch=config.max_batch_cases,
        privacy_options={
            "enabled_patterns": config.privacy_patterns,
            "extra_synthetic_domains": config.extra_synthetic_domains,
        },
    )
    register_u4_tools(registry, generation)

    # U5. The emitter and the template environment are adapters; composition is the
    # one module permitted to know both them and the service that uses them.
    from tto_testgen.adapters.playwright_emitter import PlaywrightEmitter
    from tto_testgen.adapters.templates import TemplateEnvironment
    from tto_testgen.mcp.tools_u5 import register_u5_tools

    automation = AutomationService(
        lambda: unit_of_work(connection),
        run_state,
        PlaywrightEmitter(
            config.automation_root,
            TemplateEnvironment(),
            playwright_version=config.playwright_version,
            typescript_version=config.typescript_version,
        ),
        logger,
        max_spec_lines=config.max_spec_lines,
        extra_credential_fields=config.extra_credential_fields,
    )
    register_u5_tools(registry, automation)

    # U6. The command runner is the only module permitted to import subprocess, and
    # an import contract enforces it; composition is where it is handed to S7.
    from tto_testgen.adapters.command_runner import SubprocessCommandRunner
    from tto_testgen.adapters.structural_verifier import StructuralVerifier
    from tto_testgen.mcp.tools_u6 import register_u6_tools

    handover = HandoverService(
        lambda: unit_of_work(connection),
        run_state,
        StructuralVerifier(extra_credential_fields=config.extra_credential_fields),
        SubprocessCommandRunner(
            workspace_root=config.workspace_root,
            output_limit_bytes=config.output_limit_bytes,
        ),
        logger,
        project_root=config.automation_root,
        command_timeout_s=config.command_timeout_s,
        skip_toolchain=config.skip_toolchain,
    )
    register_u6_tools(registry, handover)

    # U8. Reporting needs no external source. The change detector's Bitbucket session
    # is opened per delta run, like U2's and U3's - _ChangeDetectorWithLiveBitbucket
    # builds a fresh ChangeDetector(bitbucket, ...) inside detect(), not here.
    from tto_testgen.adapters.report_renderer import ReportRenderer
    from tto_testgen.mcp.tools_u8 import register_u8_tools

    reporting = ReportingService(
        lambda: unit_of_work(connection),
        ReportRenderer(config.reports_root, config.report_formats),
        logger,
    )
    delta = DeltaService(
        lambda: unit_of_work(connection),
        run_state,
        _ChangeDetectorWithLiveBitbucket(config, logger, max_changes=config.max_changes),
        logger,
    )
    register_u8_tools(registry, reporting, delta)

    if set(config.privacy_patterns) != set(config_module.PATTERN_NAMES):
        # Narrowing a security control is permitted and must never be quiet.
        logger.warning(
            "personal-data screening is narrowed",
            enabled=sorted(config.privacy_patterns),
            disabled=sorted(set(config_module.PATTERN_NAMES) - set(config.privacy_patterns)),
        )

    # U2's tools need live MCP sessions and source adapters, which are constructed
    # per ingestion run rather than held open for the life of the server. They are
    # registered by `wire_u2` at the point the operator starts an ingestion.

    server = McpServer(registry, logger, workspace_root=config.workspace_root)
    logger.info(
        "application ready",
        read_tools=len(registry.by_tier("read")),
        write_tools=len(registry.by_tier("write")),
        schema_version=current_version(connection),
        business_rules=config.business_rule_fingerprint(),
    )
    return ok(
        Application(
            config=config, logger=logger, connection=connection,
            server=server, run_state=run_state, analysis=analysis,
            coverage=coverage, requirements=requirements,
            generation=generation, automation=automation,
            handover=handover, reporting=reporting, delta=delta,
        )
    )


def main() -> int:  # pragma: no cover - process entry point
    """Console entry point. Serves over stdio; no socket is bound."""
    application = build()
    if isinstance(application, Err):
        # Startup failures go to stderr: stdout carries protocol traffic, and a
        # diagnostic written there would corrupt the transport.
        print(
            f"{application.code.value}: {application.message}\n{application.remediation}",
            file=sys.stderr,
        )
        return 1
    try:
        application.value.server.serve_stdio()
    finally:
        application.value.close()
    return 0
