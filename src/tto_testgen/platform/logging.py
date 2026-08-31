"""X2 StructuredLogger - correlation-bound structured logging with redaction.

Requirements: NFR-SEC-06, NFR-OBS-01, NFR-OBS-03. Pattern: P-OBS-01, P-OBS-03.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from tto_testgen.platform.config import SecretStr
from tto_testgen.platform.result import sanitise

_REDACT_KEYS = {"token", "secret", "password", "api_key", "apikey", "authorization"}


def _scrub(value: Any) -> Any:
    """Defence in depth alongside SecretStr: a raw credential passed as a log
    field is masked by key name even if it was never wrapped."""
    if isinstance(value, SecretStr):
        return "**********"
    if isinstance(value, dict):
        return {
            k: ("**********" if k.lower() in _REDACT_KEYS else _scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    if isinstance(value, str):
        return sanitise(value)
    return value


@dataclass(slots=True)
class UnitMetrics:
    duration_ms: int
    artefacts_consumed: int
    cases_produced: int
    failures: int


class Logger:
    """Context-bound logger. Correlation id and unit reference travel with it."""

    __slots__ = ("_log", "_context")

    def __init__(self, log: logging.Logger, context: dict[str, Any]) -> None:
        self._log = log
        self._context = context

    def bind(self, **fields: Any) -> "Logger":
        return Logger(self._log, {**self._context, **fields})

    def _emit(self, level: int, message: str, fields: dict[str, Any]) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": logging.getLevelName(level),
            "message": sanitise(message),
            **_scrub({**self._context, **fields}),
        }
        self._log.log(level, json.dumps(record, default=str, sort_keys=True))

    def debug(self, message: str, **fields: Any) -> None:
        self._emit(logging.DEBUG, message, fields)

    def info(self, message: str, **fields: Any) -> None:
        self._emit(logging.INFO, message, fields)

    def warning(self, message: str, **fields: Any) -> None:
        self._emit(logging.WARNING, message, fields)

    def error(self, message: str, **fields: Any) -> None:
        self._emit(logging.ERROR, message, fields)

    def record_metrics(self, unit_ref: str, stage: str, metrics: UnitMetrics) -> None:
        self._emit(
            logging.INFO,
            "unit metrics",
            {"unit_ref": unit_ref, "stage": stage, "metrics": asdict(metrics)},
        )


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def configure(level: str = "INFO") -> Logger:
    """Configure the root logger to emit to stderr.

    stderr, not stdout: the MCP server owns stdout for protocol traffic, and a log
    line written there would corrupt the transport.
    """
    root = logging.getLogger("tto_testgen")
    root.handlers.clear()
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.propagate = False
    return Logger(root, {})
