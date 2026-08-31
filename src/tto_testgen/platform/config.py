"""X3 ConfigAndSecrets - configuration resolved once, secrets that cannot leak.

Environment variables are primary; the OS credential store overrides where present.
Everything resolves at startup into a frozen object, so no component reads the
environment at call time and no value can change mid-run.

Requirements: NFR-SEC-01, U1-NFR-SEC-01, FR-AUT-07. Pattern: P-SEC-02.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from tto_testgen.platform.result import ErrorCode, Err, Ok, Result, err, ok


class SecretStr:
    """A string that will not print itself.

    The wrapper is the point: repr and str both return a mask, so a credential
    cannot reach a log line, an exception message or a serialised payload by
    accident. NFR-SEC-06 then holds under a future careless log statement rather
    than depending on nobody writing one.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        """Explicit access. Grep for `.reveal()` to audit every use."""
        return self._value

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "SecretStr('**********')"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return "**********"

    def __bool__(self) -> bool:
        return bool(self._value)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SecretStr) and self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)


@dataclass(frozen=True, slots=True)
class Config:
    workspace_root: Path

    # Storage
    db_path: Path
    backup_dir: Path
    export_dir: Path
    backup_keep: int
    busy_timeout_ms: int

    # Resilience
    retry_attempts: int
    retry_base_ms: int

    # Scalability
    page_size: int

    # Business rules. Configurable because tuning them is legitimate; the defaults
    # are the values decided in business-rules.md. A change alters the corpus, so
    # the effective values are recorded in run metadata.
    similarity_threshold: float
    commit_lookback_days: int
    max_batch_cases: int
    views_root: Path
    automation_root: Path
    playwright_version: str
    typescript_version: str
    max_spec_lines: int
    extra_credential_fields: frozenset[str]
    command_timeout_s: int
    output_limit_bytes: int
    skip_toolchain: bool
    reports_root: Path
    report_formats: tuple[str, ...]
    max_changes: int
    privacy_patterns: tuple[str, ...]
    extra_synthetic_domains: frozenset[str]

    # Observability
    log_level: str

    # The two real MCP servers the toolchain drives for bulk reads, vendored at
    # src/tt-atlassian-mcp and src/tt-bitbucket-mcp so the whole system is one
    # repository. Neither takes a credential from TAAS: tt-bitbucket-mcp reads git
    # clones already on disk and never contacts Bitbucket at all; tt-atlassian-mcp
    # does call Jira and Confluence, but authenticates from its own .env file
    # (ATLASSIAN_API_TOKEN) next to its script, which TAAS never reads.
    atlassian_mcp_command: str
    atlassian_mcp_script: Path
    atlassian_env_file: Path | None
    bitbucket_mcp_command: str
    bitbucket_mcp_script: Path
    bitbucket_env_file: Path | None

    def business_rule_fingerprint(self) -> dict[str, object]:
        """The tunables that change the corpus, for recording alongside a run."""
        return {
            "similarity_threshold": self.similarity_threshold,
            "commit_lookback_days": self.commit_lookback_days,
            "max_batch_cases": self.max_batch_cases,
            # A narrowed pattern set changes what may enter the corpus, so it
            # belongs in the fingerprint beside the rules that change its shape.
            "privacy_patterns": sorted(self.privacy_patterns),
            # The emitted Playwright version changes the generated project, so two
            # runs on different versions are not comparable artefacts.
            "playwright_version": self.playwright_version,
        }


#: Valid values for TAAS_PRIVACY_PATTERNS. Restated here rather than imported from
#: the domain: `platform` is the bottom layer and importing upward would break the
#: layering contract. `test_platform_config` asserts the two lists agree, so the
#: duplication cannot drift silently.
PATTERN_NAMES = ("email", "phone", "nino", "ssn", "card")

# Nothing is required by default any more: both MCP server scripts are vendored
# inside the workspace at a fixed path, so TAAS_ATLASSIAN_MCP_SCRIPT and
# TAAS_BITBUCKET_MCP_SCRIPT default to finding them there. Override either only to
# point at a different copy.
REQUIRED: tuple[str, ...] = ()

DEFAULTS: dict[str, str] = {
    "TAAS_DB_PATH": ".taas/taas.db",
    "TAAS_BACKUP_DIR": ".taas/backups",
    "TAAS_EXPORT_DIR": "generated/exports",
    "TAAS_BACKUP_KEEP": "10",
    "TAAS_BUSY_TIMEOUT_MS": "5000",
    "TAAS_RETRY_ATTEMPTS": "3",
    "TAAS_RETRY_BASE_MS": "1000",
    "TAAS_PAGE_SIZE": "200",
    "TAAS_SIMILARITY_THRESHOLD": "0.90",
    "TAAS_COMMIT_LOOKBACK_DAYS": "180",
    "TAAS_LOG_LEVEL": "INFO",
    "TAAS_ATLASSIAN_MCP_COMMAND": "python3",
    "TAAS_BITBUCKET_MCP_COMMAND": "python3",
    "TAAS_ATLASSIAN_MCP_SCRIPT": "src/tt-atlassian-mcp/atlassian_mcp_server.py",
    "TAAS_BITBUCKET_MCP_SCRIPT": "src/tt-bitbucket-mcp/bitbucket_mcp_server.py",
    "TAAS_MAX_BATCH_CASES": "200",
    "TAAS_VIEWS_ROOT": "generated/testcases",
    "TAAS_PRIVACY_PATTERNS": "email,phone,nino,ssn,card",
    "TAAS_EXTRA_SYNTHETIC_DOMAINS": "",
    "TAAS_AUTOMATION_ROOT": "generated/automation",
    # Pinned exactly, not a range. Version drift between the generator and the
    # Jenkins agent is the classic source of "passes locally, fails in CI", and the
    # library version is the part this system can control.
    "TAAS_PLAYWRIGHT_VERSION": "1.49.1",
    "TAAS_TYPESCRIPT_VERSION": "5.7.2",
    "TAAS_MAX_SPEC_LINES": "5000",
    "TAAS_EXTRA_CREDENTIAL_FIELDS": "",
    "TAAS_COMMAND_TIMEOUT_S": "300",
    "TAAS_OUTPUT_LIMIT_BYTES": "65536",
    # For the case where Node is present but the registry is not reachable - an
    # air-gapped workstation, a VPN that is down. Produces the same honest `skipped`
    # result rather than a five-minute wait for a timeout.
    "TAAS_SKIP_TOOLCHAIN": "false",
    "TAAS_REPORTS_ROOT": "generated/reports",
    "TAAS_REPORT_FORMATS": "markdown,csv",
    "TAAS_MAX_CHANGES": "500",
}


def _keyring_get(name: str) -> str | None:
    """Optional OS credential store override. Absent keyring is not an error."""
    try:
        import keyring  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:  # pragma: no cover - depends on host keyring
        return keyring.get_password("tto-testgen", name)
    except Exception:
        return None


def load(
    workspace_root: Path | None = None,
    environ: dict[str, str] | None = None,
) -> Result[Config]:
    """Resolve configuration once. Fails naming every missing variable at once.

    Reporting all missing variables together rather than the first matters on a
    fresh workstation, where several are typically unset: one pass through the
    error, not five.
    """
    env = dict(os.environ if environ is None else environ)
    root = (workspace_root or Path.cwd()).resolve()

    def value(name: str) -> str:
        return _keyring_get(name) or env.get(name) or DEFAULTS.get(name, "")

    missing = [name for name in REQUIRED if not value(name)]
    if missing:
        return err(
            ErrorCode.FAILED_INTERNAL,
            f"Missing required configuration: {', '.join(missing)}",
            remediation=(
                f"Set {', '.join(missing)} in the environment or the OS credential store. "
                "See .env.example."
            ),
        )

    def as_path(name: str) -> Path:
        raw = Path(value(name))
        return raw if raw.is_absolute() else root / raw

    try:
        cfg = Config(
            workspace_root=root,
            db_path=as_path("TAAS_DB_PATH"),
            backup_dir=as_path("TAAS_BACKUP_DIR"),
            export_dir=as_path("TAAS_EXPORT_DIR"),
            backup_keep=int(value("TAAS_BACKUP_KEEP")),
            busy_timeout_ms=int(value("TAAS_BUSY_TIMEOUT_MS")),
            retry_attempts=int(value("TAAS_RETRY_ATTEMPTS")),
            retry_base_ms=int(value("TAAS_RETRY_BASE_MS")),
            page_size=int(value("TAAS_PAGE_SIZE")),
            similarity_threshold=float(value("TAAS_SIMILARITY_THRESHOLD")),
            commit_lookback_days=int(value("TAAS_COMMIT_LOOKBACK_DAYS")),
            max_batch_cases=int(value("TAAS_MAX_BATCH_CASES")),
            views_root=as_path("TAAS_VIEWS_ROOT"),
            privacy_patterns=tuple(
                p.strip() for p in value("TAAS_PRIVACY_PATTERNS").split(",") if p.strip()
            ),
            automation_root=as_path("TAAS_AUTOMATION_ROOT"),
            playwright_version=value("TAAS_PLAYWRIGHT_VERSION"),
            typescript_version=value("TAAS_TYPESCRIPT_VERSION"),
            max_spec_lines=int(value("TAAS_MAX_SPEC_LINES")),
            extra_credential_fields=frozenset(
                f.strip().lower()
                for f in value("TAAS_EXTRA_CREDENTIAL_FIELDS").split(",")
                if f.strip()
            ),
            reports_root=as_path("TAAS_REPORTS_ROOT"),
            report_formats=tuple(
                f.strip().lower() for f in value("TAAS_REPORT_FORMATS").split(",")
                if f.strip()
            ),
            max_changes=int(value("TAAS_MAX_CHANGES")),
            command_timeout_s=int(value("TAAS_COMMAND_TIMEOUT_S")),
            output_limit_bytes=int(value("TAAS_OUTPUT_LIMIT_BYTES")),
            skip_toolchain=value("TAAS_SKIP_TOOLCHAIN").strip().lower()
            in {"1", "true", "yes"},
            extra_synthetic_domains=frozenset(
                d.strip().lower()
                for d in value("TAAS_EXTRA_SYNTHETIC_DOMAINS").split(",")
                if d.strip()
            ),
            log_level=value("TAAS_LOG_LEVEL").upper(),
            atlassian_mcp_command=value("TAAS_ATLASSIAN_MCP_COMMAND"),
            atlassian_mcp_script=as_path("TAAS_ATLASSIAN_MCP_SCRIPT"),
            # Unset by default: the real server already looks for a `.env` next to
            # its own script before falling back to cwd, so TAAS only needs to
            # override this when that default would resolve to the wrong file.
            atlassian_env_file=(
                as_path("TAAS_ATLASSIAN_ENV_FILE")
                if value("TAAS_ATLASSIAN_ENV_FILE") else None
            ),
            bitbucket_mcp_command=value("TAAS_BITBUCKET_MCP_COMMAND"),
            bitbucket_mcp_script=as_path("TAAS_BITBUCKET_MCP_SCRIPT"),
            bitbucket_env_file=(
                as_path("TAAS_BITBUCKET_ENV_FILE")
                if value("TAAS_BITBUCKET_ENV_FILE") else None
            ),
        )
    except ValueError as exc:
        return err(ErrorCode.FAILED_INTERNAL, f"Invalid configuration value: {exc}")

    if not 0.0 <= cfg.similarity_threshold <= 1.0:
        return err(
            ErrorCode.FAILED_INTERNAL,
            f"TAAS_SIMILARITY_THRESHOLD must be in [0.0, 1.0], got {cfg.similarity_threshold}",
        )
    if cfg.page_size < 1:
        return err(ErrorCode.FAILED_INTERNAL, "TAAS_PAGE_SIZE must be at least 1")
    if cfg.max_batch_cases < 1:
        return err(ErrorCode.FAILED_INTERNAL, "TAAS_MAX_BATCH_CASES must be at least 1")
    for name, version in (
        ("TAAS_PLAYWRIGHT_VERSION", cfg.playwright_version),
        ("TAAS_TYPESCRIPT_VERSION", cfg.typescript_version),
    ):
        # A range would let two regenerations resolve to different versions, which
        # makes the generated project non-reproducible in the one dimension U5
        # cannot control after handover.
        if not version or not version[0].isdigit():
            return err(
                ErrorCode.FAILED_INTERNAL,
                f"{name} must be an exact version, got {version!r}",
                remediation="Use an exact version such as 1.49.1, not a range.",
            )

    if cfg.command_timeout_s < 1:
        return err(ErrorCode.FAILED_INTERNAL, "TAAS_COMMAND_TIMEOUT_S must be at least 1")
    if cfg.output_limit_bytes < 1024:
        return err(
            ErrorCode.FAILED_INTERNAL,
            "TAAS_OUTPUT_LIMIT_BYTES must be at least 1024",
            remediation="A smaller bound would truncate away the error message itself.",
        )

    unsupported = set(cfg.report_formats) - {"markdown", "csv"}
    if unsupported:
        return err(
            ErrorCode.FAILED_INTERNAL,
            f"TAAS_REPORT_FORMATS names unsupported format(s): {sorted(unsupported)}",
            remediation="Valid formats are: markdown, csv.",
        )
    if cfg.max_changes < 1:
        return err(ErrorCode.FAILED_INTERNAL, "TAAS_MAX_CHANGES must be at least 1")

    for name, script in (
        ("TAAS_ATLASSIAN_MCP_SCRIPT", cfg.atlassian_mcp_script),
        ("TAAS_BITBUCKET_MCP_SCRIPT", cfg.bitbucket_mcp_script),
    ):
        # A wrong path should fail at startup, in one place, rather than as the
        # first ingestion call's mysterious "server unavailable".
        if not script.exists():
            return err(
                ErrorCode.FAILED_INTERNAL,
                f"{name} does not exist: {script}",
                remediation="Point it at the real *_mcp_server.py script on this machine.",
            )

    unknown = set(cfg.privacy_patterns) - set(PATTERN_NAMES)
    if unknown:
        return err(
            ErrorCode.FAILED_INTERNAL,
            f"TAAS_PRIVACY_PATTERNS names unknown pattern(s): {sorted(unknown)}",
            remediation=f"Valid patterns are: {', '.join(PATTERN_NAMES)}.",
        )

    return ok(cfg)
