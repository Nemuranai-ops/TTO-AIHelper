"""S3 TestableRequirementService - atomic requirements with risk and traceability.

U3 orchestrates; U1 decides. The risk formula is D6's, the key rules are D3's, the
validation is D7's. Nothing here recomputes any of them - a copy would drift, and the
drift would be silent because both would produce plausible numbers.

Requirements: FR-TRQ-01 to FR-TRQ-05, FR-TRC-02 to FR-TRC-04.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from tto_testgen.adapters.commit_index import CommitIndex, IndexBounds
from tto_testgen.domain.atomicity import check as check_atomicity
from tto_testgen.domain.classification import RiskFactor, rate_risk
from tto_testgen.domain.identity import SequenceState, allocate
from tto_testgen.domain.model import (
    DomainError,
    EntityKind,
    LinkType,
    RiskBand,
    TestableRequirement,
    TraceLink,
    utc_now,
)
from tto_testgen.domain.traceability import Gap as DomainGap
from tto_testgen.domain.traceability import KeyResolution, derive_key_from_commits
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import ErrorCode, Result, err, ok

CATEGORIES = frozenset({
    "ui-behaviour", "api-contract", "business-rule", "validation",
    "integration", "security", "performance", "accessibility",
})

#: BR-U3-1.1. Thresholds live here so they are reviewable in one place rather than
#: scattered through the gathering code.
COMPLEXITY_BANDS = (1, 3, 6, 10)
INTEGRATION_BANDS = (0, 1, 3, 6)
CHANGE_BANDS = (0, 2, 5, 10)


def band(value: int, thresholds: tuple[int, ...]) -> int:
    """Map a count to 1-5. Monotonic non-decreasing by construction."""
    for index, threshold in enumerate(thresholds):
        if value <= threshold:
            return index + 1
    return 5


@dataclass(slots=True)
class RequirementReport:
    accepted: list[str] = field(default_factory=list)
    rejections: list[dict[str, str]] = field(default_factory=list)
    gaps: list[dict[str, str]] = field(default_factory=list)
    derived_links: int = 0
    partial_ratings: int = 0
    index_report: dict[str, Any] = field(default_factory=dict)
    atomicity_overrides: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.rejections

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "accepted": self.accepted,
            "rejections": self.rejections,
            "gaps": self.gaps,
            "derived_links": self.derived_links,
            "partial_ratings": self.partial_ratings,
            "atomicity_overrides": self.atomicity_overrides,
            "index": self.index_report,
        }
        if self.gaps:
            payload["gap_note"] = (
                f"{len(self.gaps)} behaviour(s) could not be traced to a Jira key and "
                f"were recorded as gaps rather than requirements. This is a fact about "
                f"the sources, not a fault in the submission."
            )
        if self.partial_ratings:
            payload["rating_note"] = (
                f"{self.partial_ratings} requirement(s) were rated on fewer than four "
                f"factors. Unavailable factors are excluded from the calculation, not "
                f"scored zero."
            )
        return payload


class TestableRequirementService:
    def __init__(
        self,
        uow_factory: Callable[[], Any],
        bitbucket: Any,
        logger: Logger,
        *,
        bounds: IndexBounds | None = None,
        atomicity_enforced: bool = True,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._bitbucket = bitbucket
        self._logger = logger
        self._bounds = bounds or IndexBounds()
        self._atomicity_enforced = atomicity_enforced
        self._now = clock or (lambda: datetime.now(timezone.utc))

    # --- risk -------------------------------------------------------------

    def _gather_signals(
        self, uow: Any, feature_id: int, payload: dict[str, Any], change_count: int | None
    ) -> dict[RiskFactor, int | None]:
        rules = uow.features.rules_for_feature(feature_id)
        endpoints = [
            e for e in uow.features.list_endpoints() if e["feature_id"] == feature_id
        ]
        criticality = payload.get("business_criticality")
        return {
            # Not derivable from any artefact: a Jira priority is a scheduling
            # signal and an epic label is a grouping. Absent means unavailable.
            RiskFactor.BUSINESS_CRITICALITY: criticality,
            RiskFactor.COMPLEXITY: band(len(rules), COMPLEXITY_BANDS),
            RiskFactor.INTEGRATION_SURFACE: band(len(endpoints), INTEGRATION_BANDS),
            # None, never 0: zero commits and no commit data are different facts,
            # and scoring the second as the first reads as "stable" when it means
            # "unknown" (US-TRQ-02 AC3).
            RiskFactor.CHANGE_FREQUENCY: (
                band(change_count, CHANGE_BANDS) if change_count is not None else None
            ),
        }

    # --- key resolution ---------------------------------------------------

    def _resolve_key(
        self, candidate: dict[str, Any], known_keys: frozenset[str], index: CommitIndex | None
    ) -> KeyResolution | DomainGap | None:
        for link in candidate.get("links", []):
            key = link.get("jira_key")
            if link.get("type") == "direct-story" and key in known_keys:
                return KeyResolution(
                    jira_key=key, link_type=LinkType.DIRECT_STORY,
                    evidence=link.get("evidence", "direct story link"),
                )

        if index is None:
            return None

        attempted = ["direct-story"]
        for path in candidate.get("source_files", []):
            commits = index.commits_for(path)
            if not commits:
                attempted.append(
                    f"commit-derivation ({path}: "
                    f"{'skipped, index limit' if index.was_skipped(path) else 'unreachable' if index.was_unreachable(path) else 'no commits'})"
                )
                continue
            outcome = derive_key_from_commits(
                path, commits, known_keys,
                lookback_days=self._bounds.lookback_days, now=self._now(),
            )
            if isinstance(outcome, KeyResolution):
                return outcome
            attempted.extend(outcome.attempted)

        return DomainGap(
            source_ref=", ".join(candidate.get("source_files", [])) or "(no source files)",
            description=candidate.get("statement", ""),
            attempted=attempted,
        )

    # --- the batch --------------------------------------------------------

    def upsert_requirements(
        self, feature_slug: str, payload: dict[str, Any], run_id: int | None = None
    ) -> Result[RequirementReport]:
        """All-or-nothing per feature, reporting every failure at once.

        A half-populated requirement set is the dangerous outcome: the coverage model
        built from it would be missing items nobody knows are missing, and the Test
        Lead would approve a baseline that silently omits them. A rejected batch is
        obviously incomplete; a partially accepted one looks finished.
        """
        report = RequirementReport()
        candidates = payload.get("requirements", [])

        with self._uow_factory() as uow:
            feature = uow.features.get_by_slug(feature_slug)
            if feature is None:
                return err(
                    ErrorCode.FAILED_INTERNAL, f"Unknown feature: {feature_slug}",
                    remediation="Call features_list to see available features.",
                )
            feature_id = feature["id"]
            known_keys = uow.artefacts.known_jira_keys()
            state = SequenceState.from_existing(
                [r["id"] for r in uow.requirements.query(limit=200).items]
            )

            repo_slug = payload.get("repo_slug")
            index = (
                CommitIndex(self._bitbucket, repo_slug, self._logger,
                            bounds=self._bounds, now=self._now())
                if repo_slug and self._bitbucket
                else None
            )

            prepared: list[tuple[TestableRequirement, TraceLink, dict]] = []

            for candidate in candidates:
                statement = candidate.get("statement", "")
                failures: list[dict[str, str]] = []

                if self._atomicity_enforced:
                    verdict = check_atomicity(
                        statement, force_atomic=candidate.get("force_atomic", False)
                    )
                    if not verdict.is_atomic:
                        failures.append({
                            "subject": statement[:80],
                            "code": ErrorCode.REJECTED_INVALID_STEPS.value,
                            "detail": verdict.detail,
                            "suspected_split": verdict.suspected_split,
                        })
                    elif candidate.get("force_atomic"):
                        report.atomicity_overrides.append(statement[:80])

                if candidate.get("category") not in CATEGORIES:
                    failures.append({
                        "subject": statement[:80],
                        "code": ErrorCode.REJECTED_INVALID_STEPS.value,
                        "detail": f"unknown category: {candidate.get('category')!r}",
                    })

                if not candidate.get("source_artefact_ids"):
                    failures.append({
                        "subject": statement[:80],
                        "code": ErrorCode.REJECTED_NO_JIRA_KEY.value,
                        "detail": "cites no source artefact",
                    })

                if failures:
                    report.rejections.extend(failures)
                    continue

                resolution = self._resolve_key(candidate, known_keys, index)

                if isinstance(resolution, DomainGap):
                    # A gap is not a rejection. A rejected requirement is the agent's
                    # mistake and must be fixed; a gapped behaviour is a fact about
                    # the sources that nothing the agent can do will correct, and
                    # failing the batch for it would leave the agent retrying forever.
                    report.gaps.append({
                        "subject": resolution.description[:120],
                        "source_ref": resolution.source_ref,
                        "attempted": "; ".join(resolution.attempted),
                    })
                    continue

                if resolution is None:
                    report.rejections.append({
                        "subject": statement[:80],
                        "code": ErrorCode.REJECTED_NO_JIRA_KEY.value,
                        "detail": "no resolvable Jira key and no source files to derive from",
                    })
                    continue

                signals = self._gather_signals(
                    uow, feature_id, candidate,
                    len(index.commits_for(candidate["source_files"][0]))
                    if index and candidate.get("source_files") else None,
                )
                rating = rate_risk(signals)
                if rating.is_partial:
                    report.partial_ratings += 1

                requirement_id, state = allocate(EntityKind.REQUIREMENT, feature_slug, state)
                try:
                    requirement = TestableRequirement(
                        id=requirement_id, feature_id=feature_id, statement=statement,
                        classification=candidate.get("classification", "functional"),
                        category=candidate["category"],
                        risk_score=rating.score, risk_band=rating.band,
                        risk_factors={
                            **rating.factors,
                            "criticality_evidence": candidate.get("criticality_evidence", ""),
                        },
                        risk_is_partial=rating.is_partial,
                        source_artefact_ids=candidate["source_artefact_ids"],
                    )
                except DomainError as exc:
                    report.rejections.append({
                        "subject": statement[:80],
                        "code": ErrorCode.FAILED_INTERNAL.value, "detail": str(exc),
                    })
                    continue

                link = resolution.to_link("requirement", requirement_id, resolution.jira_key)
                prepared.append((requirement, link, candidate))

            if index is not None:
                report.index_report = index.report.to_dict()

            if report.rejections:
                self._logger.warning(
                    "requirement batch rejected", count=len(report.rejections)
                )
                return ok(report)

            for requirement, link, _candidate in prepared:
                uow.requirements.upsert(requirement)
                uow.traces.add_many([link])
                report.accepted.append(requirement.id)
                if link.link_type is LinkType.DERIVED_FROM_COMMIT:
                    report.derived_links += 1

            for gap in report.gaps:
                uow.gaps.add_unless_open({
                    "category": "untraceable-behaviour", "subject": gap["subject"],
                    "source_ref": gap["source_ref"],
                    "attempted": gap["attempted"].split("; "),
                    "feature_slug": feature_slug, "detected_at": utc_now(),
                }, run_id)

            for candidate in candidates:
                for boundary in candidate.get("undetermined_boundaries", []):
                    uow.gaps.add_unless_open({
                        "category": "boundaries-undetermined", "subject": boundary,
                        "feature_slug": feature_slug, "detected_at": utc_now(),
                        "detail": "boundaries not stated in any source",
                    }, run_id)

        self._logger.info(
            "requirements stored", accepted=len(report.accepted),
            gaps=len(report.gaps), derived=report.derived_links,
        )
        return ok(report)
