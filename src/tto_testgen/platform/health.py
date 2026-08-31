"""X5 HealthCheck - can the system work right now?

Each component reports independently. One unreachable MCP server does not read as
total failure: the operator can see that Jira is down while Bitbucket is fine, and
choose to proceed with what works.

Requirements: NFR-OBS-02, RESILIENCY-06. Pattern: P-OBS-02.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class Status(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    name: str
    status: Status
    detail: str = ""


@dataclass(slots=True)
class HealthReport:
    components: list[ComponentHealth] = field(default_factory=list)

    @property
    def overall(self) -> Status:
        """UNAVAILABLE only when nothing works.

        A run can proceed with one external server down - ingestion of the other
        sources still succeeds - so partial failure is DEGRADED, not UNAVAILABLE.
        Collapsing the two would tell the operator to stop when they could continue.
        """
        if not self.components:
            return Status.UNAVAILABLE
        statuses = {c.status for c in self.components}
        if statuses == {Status.OK}:
            return Status.OK
        if Status.OK in statuses or Status.DEGRADED in statuses:
            return Status.DEGRADED
        return Status.UNAVAILABLE

    def to_dict(self) -> dict[str, object]:
        return {
            "overall": self.overall.value,
            "components": [
                {"name": c.name, "status": c.status.value, "detail": c.detail}
                for c in self.components
            ],
        }


Probe = Callable[[], ComponentHealth]


def check(probes: dict[str, Probe]) -> HealthReport:
    """Run every probe. A probe that raises reports UNAVAILABLE rather than
    aborting the check, so one broken probe cannot hide the state of the others."""
    report = HealthReport()
    for name, probe in probes.items():
        try:
            report.components.append(probe())
        except Exception as exc:  # noqa: BLE001 - a probe must never break the check
            report.components.append(
                ComponentHealth(name=name, status=Status.UNAVAILABLE, detail=str(exc)[:200])
            )
    return report
