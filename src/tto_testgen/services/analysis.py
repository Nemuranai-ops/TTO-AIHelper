"""S2 AnalysisService - the application model, part reasoned and part derived.

The split is Application Design Q3 applied at method level: the agent supplies what
needs judgement, the toolchain derives what does not.

| Produced by the agent        | Produced here                    |
|------------------------------|----------------------------------|
| Feature hierarchy, journeys  | The entire API model             |
| Business rules read in prose | Discrepancy detection            |
| UI model from live browsing  |                                  |

Requirements: FR-ANA-01 to FR-ANA-08.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from tto_testgen.domain.apimodel import ApiMergeResult, CodeEndpoint, SpecEndpoint, merge
from tto_testgen.domain.discrepancy import Discrepancy, from_merge
from tto_testgen.domain.model import DomainError, Feature, slugify
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import ErrorCode, Result, err, ok


@dataclass(slots=True)
class AnalysisReport:
    features: int = 0
    journeys: int = 0
    business_rules: int = 0
    screens: int = 0
    ui_elements: int = 0
    unverified_locators: int = 0
    discrepancies: int = 0
    unassigned_artefacts: list[str] = field(default_factory=list)
    rejections: list[dict[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.rejections

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "features": self.features,
            "journeys": self.journeys,
            "business_rules": self.business_rules,
            "screens": self.screens,
            "ui_elements": self.ui_elements,
            "unverified_locators": self.unverified_locators,
            "discrepancies": self.discrepancies,
            "unassigned_artefacts": self.unassigned_artefacts,
            "rejections": self.rejections,
        }
        if self.unverified_locators:
            payload["note"] = (
                f"{self.unverified_locators} locator(s) stored unverified. A locator "
                f"that works and one that ought to are different facts; U4 and U5 "
                f"read this flag."
            )
        return payload


def has_cycle(features: list[dict[str, Any]]) -> bool:
    """A feature that is its own ancestor would make the hierarchy untraversable."""
    parents = {f.get("slug"): f.get("parent_slug") for f in features}
    for start in parents:
        seen: set[str | None] = set()
        current = start
        while current is not None:
            if current in seen:
                return True
            seen.add(current)
            current = parents.get(current)
    return False


class AnalysisService:
    def __init__(self, uow_factory: Callable[[], Any], logger: Logger) -> None:
        self._uow_factory = uow_factory
        self._logger = logger

    # --- agent-supplied ---------------------------------------------------

    def upsert_feature_model(self, payload: dict[str, Any]) -> Result[AnalysisReport]:
        """Store the agent's feature hierarchy, journeys and business rules.

        Validation runs over the whole payload before anything is written, so a
        rejection leaves no partial hierarchy behind. A feature citing no source
        artefact is refused: it is an invention, and catching it here costs far less
        than catching it 200 test cases later.
        """
        report = AnalysisReport()
        features = payload.get("features", [])

        with self._uow_factory() as uow:
            known = {row["source_identifier"] for row in uow.artefacts.query(limit=200).items}

            for feature in features:
                slug = feature.get("slug") or slugify(feature.get("name", "unnamed"))
                sources = feature.get("source_artefact_ids") or []
                if not sources:
                    report.rejections.append({
                        "subject": slug,
                        "code": ErrorCode.REJECTED_NO_JIRA_KEY.value,
                        "detail": "feature cites no source artefact",
                    })
                    continue
                unknown = {s for s in sources if known and s not in known}
                if unknown:
                    report.rejections.append({
                        "subject": slug,
                        "code": ErrorCode.REJECTED_UNKNOWN_JIRA_KEY.value,
                        "detail": f"source artefacts not ingested: {sorted(unknown)}",
                    })

            if has_cycle(features):
                report.rejections.append({
                    "subject": "feature-hierarchy",
                    "code": ErrorCode.REJECTED_INVALID_STEPS.value,
                    "detail": "feature hierarchy contains a cycle",
                })

            if report.rejections:
                self._logger.warning(
                    "feature model rejected", rejections=len(report.rejections)
                )
                return ok(report)

            slug_to_id: dict[str, int] = {}
            for feature in features:
                slug = feature.get("slug") or slugify(feature.get("name", "unnamed"))
                try:
                    uow.features.upsert(Feature(
                        slug=slug,
                        name=feature.get("name", slug),
                        description=feature.get("description", ""),
                    ))
                except DomainError as exc:
                    report.rejections.append({
                        "subject": slug,
                        "code": ErrorCode.FAILED_INTERNAL.value,
                        "detail": str(exc),
                    })
                    continue
                row = uow.features.get_by_slug(slug)
                if row is not None:
                    slug_to_id[slug] = row["id"]
                report.features += 1

            for journey in payload.get("journeys", []):
                uow.features.add_journey(
                    journey.get("name", "unnamed"), journey.get("steps", [])
                )
                report.journeys += 1

            for rule in payload.get("business_rules", []):
                feature_id = slug_to_id.get(rule.get("feature_slug", ""))
                if feature_id is None:
                    continue
                uow.features.add_business_rule(
                    feature_id=feature_id,
                    rule_kind=rule.get("rule_kind", "validation"),
                    condition=rule.get("condition", ""),
                    effect=rule.get("effect", ""),
                    # A rule found only as a code branch is worth having, and worth
                    # marking as undocumented.
                    is_documented=rule.get("is_documented", True),
                )
                report.business_rules += 1

            # An artefact mapping to no feature is listed, not forced into the
            # nearest one. A forced link later reads as evidence (US-ANA-01 AC3).
            report.unassigned_artefacts = payload.get("unassigned_artefact_ids", [])

        self._logger.info(
            "feature model stored",
            features=report.features,
            journeys=report.journeys,
            rules=report.business_rules,
        )
        return ok(report)

    def upsert_ui_model(self, payload: dict[str, Any]) -> Result[AnalysisReport]:
        """Store screens and elements from the agent's Playwright exploration.

        `is_verified` is true only for locators confirmed against the running
        application. When the environment is unreachable, every derived locator is
        stored unverified rather than presented as confirmed (US-ANA-04 AC5).
        """
        report = AnalysisReport()

        with self._uow_factory() as uow:
            for screen in payload.get("screens", []):
                feature_row = uow.features.get_by_slug(screen.get("feature_slug", ""))
                screen_id = uow.features.add_screen({
                    "feature_id": feature_row["id"] if feature_row else None,
                    "name": screen.get("name", "unnamed"),
                    "state": screen.get("state", "default"),
                    "route": screen.get("route"),
                    "source": screen.get("source", "figma"),
                })
                report.screens += 1

                for element in screen.get("elements", []):
                    uow.features.add_element(screen_id, element)
                    report.ui_elements += 1
                    if not element.get("is_verified", False):
                        report.unverified_locators += 1

        if report.unverified_locators:
            self._logger.warning(
                "unverified locators stored",
                count=report.unverified_locators,
                note="the AUT may have been unreachable during exploration",
            )
        self._logger.info(
            "ui model stored", screens=report.screens, elements=report.ui_elements
        )
        return ok(report)

    # --- toolchain-derived ------------------------------------------------

    def derive_api_model(
        self,
        code_endpoints: list[CodeEndpoint],
        spec_endpoints: list[SpecEndpoint],
        *,
        feature_slug: str | None = None,
        run_id: int | None = None,
    ) -> Result[dict[str, Any]]:
        """FR-ANA-04. Mechanical, so no agent is involved.

        Code decides existence; the spec decides shapes. An entry in the spec with no
        handler becomes a discrepancy, never an endpoint - otherwise the corpus would
        carry tests for something that returns 404.
        """
        result: ApiMergeResult = merge(code_endpoints, spec_endpoints)
        recorded = [from_merge(d) for d in result.discrepancies]

        with self._uow_factory() as uow:
            feature_row = (
                uow.features.get_by_slug(feature_slug) if feature_slug else None
            )
            feature_id = feature_row["id"] if feature_row else None

            for endpoint in result.endpoints:
                uow.features.add_endpoint({
                    "feature_id": feature_id,
                    "method": endpoint.method,
                    "route": endpoint.route,
                    "file_path": endpoint.file_path,
                    "line": endpoint.line,
                    "symbol": endpoint.symbol,
                    "request_shape": endpoint.request_shape,
                    "response_shapes": endpoint.response_shapes,
                    "status_codes": list(endpoint.status_codes),
                    "auth_requirement": endpoint.auth_requirement.value,
                    "shape_source": endpoint.shape_source.value,
                })

            for discrepancy in recorded:
                uow.discrepancies.add(discrepancy.to_dict(), run_id)

        self._logger.info(
            "api model derived",
            endpoints=len(result.endpoints),
            specified=result.specified_count,
            inferred=result.inferred_count,
            discrepancies=len(recorded),
        )
        return ok({
            "endpoints": len(result.endpoints),
            "specified": result.specified_count,
            "inferred": result.inferred_count,
            "discrepancies": [d.to_dict() for d in recorded],
        })

    def record_discrepancy(
        self, discrepancy: Discrepancy, run_id: int | None = None
    ) -> Result[None]:
        """Record that two sources disagree. Never resolve it.

        Resolution requires knowing intent, which is a human judgement. Nothing here
        writes `resolved_by` or `resolution`.
        """
        with self._uow_factory() as uow:
            uow.discrepancies.add(discrepancy.to_dict(), run_id)
        return ok(None)
