"""D1 DomainModel - the entity types the whole system speaks in.

Pure: stdlib only, no pydantic, no sqlite. The import-linter contract enforces this,
because the property suite depends on the domain being constructible without a
database or a network.

A value object that cannot be constructed validly does not exist. That removes a
whole class of downstream checking: nothing has to ask "is this step list empty?"
because a TestCase with an empty step list was never created.

Requirements: requirements.md 10.2 and 10.3, FR-TCG-01, FR-TCG-02.
PBT target: PBT-02 round-trip - from_dict(to_dict(x)) == x for every entity.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Self

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class LinkType(str, Enum):
    DIRECT_STORY = "direct-story"
    DERIVED_FROM_COMMIT = "derived-from-commit"
    CONFLUENCE = "confluence"
    CODE_SYMBOL = "code-symbol"
    SCREENSHOT = "screenshot"

    @property
    def resolves_jira_key(self) -> bool:
        return self in (LinkType.DIRECT_STORY, LinkType.DERIVED_FROM_COMMIT)


#: BR-8.1 precedence, strongest first. Used to pick the primary link when several
#: exist for one target; all links are retained regardless.
LINK_TYPE_PRECEDENCE: tuple[LinkType, ...] = (
    LinkType.DIRECT_STORY,
    LinkType.DERIVED_FROM_COMMIT,
    LinkType.CONFLUENCE,
    LinkType.CODE_SYMBOL,
    LinkType.SCREENSHOT,
)


class TestType(str, Enum):
    FUNCTIONAL_POSITIVE = "functional-positive"
    FUNCTIONAL_NEGATIVE = "functional-negative"
    BOUNDARY = "boundary"
    VALIDATION = "validation"
    UI_BEHAVIOUR = "ui-behaviour"
    API_CONTRACT = "api-contract"
    INTEGRATION = "integration"
    PERMISSIONS = "permissions"
    ERROR_HANDLING = "error-handling"


class AutomatabilityClass(str, Enum):
    AUTOMATABLE = "automatable"
    MANUAL_ONLY = "manual-only"
    NEEDS_REVIEW = "needs-review"


class RiskBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class UnitState(str, Enum):
    NOT_STARTED = "not-started"
    IN_PROGRESS = "in-progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs-review"


class StageName(str, Enum):
    INGEST = "ingest"
    ANALYSE = "analyse"
    REQUIREMENTS = "requirements"
    COVERAGE = "coverage"
    CASES = "cases"
    AUTOMATION = "automation"
    HANDOVER = "handover"


class ChangeClassification(str, Enum):
    UNCHANGED = "unchanged"
    REQUIRES_UPDATE = "requires-update"
    OBSOLETE = "obsolete"


class ResourceType(str, Enum):
    JIRA_ISSUE = "jira-issue"
    JIRA_QUERY = "jira-query"
    CONFLUENCE_PAGE = "confluence-page"
    CONFLUENCE_SPACE = "confluence-space"
    BITBUCKET_REPO = "bitbucket-repo"
    OPENAPI_SPEC = "openapi-spec"
    DESIGN_FOLDER = "design-folder"
    UNCLASSIFIED = "unclassified"


class CoverageTechnique(str, Enum):
    EQUIVALENCE_PARTITIONING = "equivalence-partitioning"
    BOUNDARY_VALUE_ANALYSIS = "boundary-value-analysis"
    DECISION_TABLE = "decision-table"
    STATE_TRANSITION = "state-transition"
    DIRECT = "direct"


class EntityKind(str, Enum):
    """Identifier namespaces. BR-6.1."""

    TEST_CASE = "TC"
    REQUIREMENT = "TR"
    COVERAGE_ITEM = "CI"
    AUTOMATED_TEST = "AT"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


class DomainError(ValueError):
    """Raised when a value object or entity cannot be validly constructed."""


_JIRA_KEY = re.compile(r"^[A-Z]{2,10}-[1-9]\d*$")
_FEATURE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ENTITY_ID = re.compile(r"^(TC|TR|CI|AT)-([A-Z0-9]+(?:-[A-Z0-9]+)*)-(\d{5})$")
_CONTENT_HASH = re.compile(r"^[0-9a-f]{64}$")


def jira_key(value: str) -> str:
    """`<PROJECT>-<n>`. Rejecting the shape here means an invented key cannot
    silently satisfy the traceability rule at a later layer."""
    if not _JIRA_KEY.match(value):
        raise DomainError(f"Invalid Jira key: {value!r}. Expected <PROJECT>-<number>.")
    return value


def feature_slug(value: str) -> str:
    if not _FEATURE_SLUG.match(value) or len(value) > 60:
        raise DomainError(
            f"Invalid feature slug: {value!r}. Expected lowercase hyphenated, 1-60 chars."
        )
    return value


def slugify(name: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]
    if not out:
        raise DomainError(f"Cannot derive a feature slug from {name!r}")
    return out


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_content_hash(value: str) -> str:
    if not _CONTENT_HASH.match(value):
        raise DomainError(f"Invalid content hash: {value!r}. Expected 64 hex characters.")
    return value


def encode_id(kind: EntityKind, slug: str, sequence: int) -> str:
    """BR-6.1. `TC-<FEATURE_SLUG>-<00001>`, uppercased."""
    feature_slug(slug)
    if not 1 <= sequence <= 99999:
        raise DomainError(f"Sequence {sequence} out of range 1..99999")
    return f"{kind.value}-{slug.upper()}-{sequence:05d}"


def decode_id(value: str) -> tuple[EntityKind, str, int]:
    """Inverse of encode_id. PBT-02: decode(encode(x)) == x."""
    match = _ENTITY_ID.match(value)
    if not match:
        raise DomainError(f"Invalid entity identifier: {value!r}")
    prefix, slug, sequence = match.groups()
    return EntityKind(prefix), slug.lower(), int(sequence)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def to_dict(entity: Any) -> dict[str, Any]:
    """Serialise any domain entity to a plain dictionary.

    Enums become their values, nested dataclasses recurse. The output contains only
    JSON-native types so it can round-trip through YAML, JSON or a database column.
    """
    if not is_dataclass(entity):
        raise DomainError(f"{type(entity).__name__} is not a domain entity")
    return _plain(asdict(entity))


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def from_dict(cls: type, payload: dict[str, Any]) -> Any:
    """Reconstruct an entity. Unknown keys are rejected rather than ignored.

    Silently dropping an unknown key would let a schema change pass unnoticed and
    reappear as missing data much later.
    """
    if not is_dataclass(cls):
        raise DomainError(f"{cls.__name__} is not a domain entity")
    known = {f.name: f for f in fields(cls)}
    unknown = set(payload) - set(known)
    if unknown:
        raise DomainError(f"Unknown fields for {cls.__name__}: {sorted(unknown)}")
    kwargs: dict[str, Any] = {}
    for name, spec in known.items():
        if name not in payload:
            continue
        kwargs[name] = _revive(spec.type, payload[name])
    return cls(**kwargs)


_ENUMS: dict[str, type[Enum]] = {
    "LinkType": LinkType,
    "TestType": TestType,
    "AutomatabilityClass": AutomatabilityClass,
    "RiskBand": RiskBand,
    "UnitState": UnitState,
    "StageName": StageName,
    "ChangeClassification": ChangeClassification,
    "ResourceType": ResourceType,
    "CoverageTechnique": CoverageTechnique,
    "EntityKind": EntityKind,
}


def _revive(annotation: Any, value: Any) -> Any:
    """Rebuild enums and nested entities from their plain form.

    Annotations arrive as strings under `from __future__ import annotations`, so the
    enum name is matched textually rather than by identity.
    """
    if value is None:
        return None
    text = annotation if isinstance(annotation, str) else getattr(annotation, "__name__", "")
    for name, enum_cls in _ENUMS.items():
        if text.startswith(name) or f"[{name}" in text or f" {name}" in text:
            if isinstance(value, list):
                return [enum_cls(v) for v in value]
            return enum_cls(value)
    if text.startswith("list[TestStep]"):
        return [from_dict(TestStep, v) for v in value]
    if text.startswith("list[TestData]"):
        return [from_dict(TestData, v) for v in value]
    if text.startswith("list[TraceLink]"):
        return [from_dict(TraceLink, v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Resource:
    """1. A declared input from resources.md or the design-asset folder."""

    raw_ref: str
    type: ResourceType
    inferred_from: str = ""
    status: str = "pending"
    failure_reason: str | None = None
    first_seen_at: str = field(default_factory=utc_now)
    last_ingested_at: str | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        if not self.raw_ref.strip():
            raise DomainError("Resource requires a non-empty raw_ref")


@dataclass(frozen=True, slots=True)
class Artefact:
    """2. An ingested item with provenance."""

    resource_id: int
    kind: str
    source_identifier: str
    content: str
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)
    detail_level: str = "full"
    ingested_at: str = field(default_factory=utc_now)
    run_id: int | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        validate_content_hash(self.content_hash)
        if self.detail_level not in ("full", "low"):
            raise DomainError(f"detail_level must be 'full' or 'low', got {self.detail_level!r}")

    @classmethod
    def of(cls, *, resource_id: int, kind: str, source_identifier: str, content: str, **kw) -> Self:
        return cls(
            resource_id=resource_id,
            kind=kind,
            source_identifier=source_identifier,
            content=content,
            content_hash=content_hash(content),
            **kw,
        )


@dataclass(frozen=True, slots=True)
class Feature:
    """3. A node in the feature hierarchy."""

    slug: str
    name: str
    parent_id: int | None = None
    description: str = ""
    risk_band: RiskBand | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        feature_slug(self.slug)
        if not self.name.strip():
            raise DomainError("Feature requires a non-empty name")


@dataclass(frozen=True, slots=True)
class Journey:
    """4. A multi-step user flow crossing features."""

    name: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    id: int | None = None


@dataclass(frozen=True, slots=True)
class BusinessRule:
    """5. A discrete extracted rule.

    `contradicts_id` implements FR-ANA-08: when Jira and code disagree, both rules
    persist and point at each other. The system records the conflict; it does not
    resolve it.
    """

    feature_id: int
    rule_kind: str
    condition: str
    effect: str
    is_documented: bool = True
    contradicts_id: int | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        if self.rule_kind not in ("validation", "state-transition", "calculation", "permission"):
            raise DomainError(f"Unknown rule_kind: {self.rule_kind!r}")


@dataclass(frozen=True, slots=True)
class ApiEndpoint:
    """6. An HTTP endpoint discovered in source or an OpenAPI spec."""

    method: str
    route: str
    file_path: str
    line: int
    symbol: str = ""
    feature_id: int | None = None
    request_shape: dict[str, Any] | None = None
    response_shapes: dict[str, Any] | None = None
    status_codes: list[int] = field(default_factory=list)
    auth_requirement: str = "unknown"
    shape_source: str = "inferred"
    id: int | None = None

    def __post_init__(self) -> None:
        # "unknown" is a distinct state from "none": defaulting an undetermined
        # auth requirement to public would hide a security-relevant gap.
        if self.auth_requirement not in ("none", "required", "unknown"):
            raise DomainError(f"auth_requirement must be none|required|unknown")
        if self.shape_source not in ("specified", "inferred"):
            raise DomainError("shape_source must be specified|inferred")


@dataclass(frozen=True, slots=True)
class Screen:
    """7. A UI screen in a particular state."""

    name: str
    state: str = "default"
    feature_id: int | None = None
    route: str | None = None
    source: str = "figma"
    discrepancy_id: int | None = None
    id: int | None = None


@dataclass(frozen=True, slots=True)
class UiElement:
    """8. An element on a screen, with its locator preference chain."""

    screen_id: int
    role: str | None = None
    accessible_name: str | None = None
    test_id: str | None = None
    locator_chain: list[str] = field(default_factory=list)
    is_fragile: bool = False
    is_verified: bool = False
    id: int | None = None


@dataclass(frozen=True, slots=True)
class TestableRequirement:
    """9. An atomic, independently verifiable statement."""

    id: str
    feature_id: int
    statement: str
    classification: str = "functional"
    category: str = "business-rule"
    risk_score: int | None = None
    risk_band: RiskBand | None = None
    risk_factors: dict[str, Any] = field(default_factory=dict)
    risk_is_partial: bool = False
    source_artefact_ids: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        kind, _, _ = decode_id(self.id)
        if kind is not EntityKind.REQUIREMENT:
            raise DomainError(f"Requirement id must use the TR prefix, got {self.id!r}")
        if not self.statement.strip():
            raise DomainError("TestableRequirement requires a non-empty statement")


@dataclass(frozen=True, slots=True)
class CoverageItem:
    """10. A required (requirement, test type) pairing with depth and rationale.

    `is_required=False` rows are kept, not omitted: an absent row and a deliberate
    exclusion look identical unless the exclusion is recorded (BR-2.6).
    """

    id: str
    requirement_id: str
    test_type: TestType
    technique: CoverageTechnique = CoverageTechnique.DIRECT
    planned_count: int = 1
    rationale: str = ""
    is_required: bool = True
    reduction_applied: str | None = None
    model_version: str = "1"

    def __post_init__(self) -> None:
        if decode_id(self.id)[0] is not EntityKind.COVERAGE_ITEM:
            raise DomainError(f"Coverage item id must use the CI prefix, got {self.id!r}")
        if self.planned_count < 0:
            raise DomainError("planned_count cannot be negative")
        if not self.is_required and self.planned_count != 0:
            raise DomainError("A not-required coverage item must plan zero cases")


@dataclass(frozen=True, slots=True)
class TestStep:
    """12. One ordered step. A step without an expected result is not a step."""

    ordinal: int
    action: str
    expected: str

    def __post_init__(self) -> None:
        if self.ordinal < 1:
            raise DomainError(f"Step ordinal must be >= 1, got {self.ordinal}")
        if not self.action.strip():
            raise DomainError(f"Step {self.ordinal} requires a non-empty action")
        if not self.expected.strip():
            raise DomainError(f"Step {self.ordinal} requires a non-empty expected result")


@dataclass(frozen=True, slots=True)
class TestData:
    """13. A data value bound to a case or step, with the class it represents.

    `equivalence_class` is mandatory: it is what makes two superficially similar
    cases materially different in de-duplication (BR-1.4), and what lets a reviewer
    see why a value was chosen.
    """

    field_name: str
    value: str
    equivalence_class: str
    step_ordinal: int | None = None
    boundary_relation: str | None = None

    def __post_init__(self) -> None:
        if not self.equivalence_class.strip():
            raise DomainError(
                f"Test data for {self.field_name!r} requires an equivalence class"
            )
        if self.boundary_relation is not None and self.boundary_relation not in (
            "at",
            "just-inside",
            "just-outside",
        ):
            raise DomainError(
                f"boundary_relation must be at|just-inside|just-outside, "
                f"got {self.boundary_relation!r}"
            )


@dataclass(frozen=True, slots=True)
class TraceLink:
    """14. A typed edge between an entity and a source.

    `alternatives` retains the candidates not chosen during commit derivation, so a
    reviewer can see what else was on the table (BR-3.3).
    """

    source_kind: str
    source_id: str
    target_ref: str
    link_type: LinkType
    evidence: str = ""
    selection_basis: str | None = None
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    resolved_jira_key: str | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        if not self.target_ref.strip():
            raise DomainError("TraceLink requires a target_ref")
        if self.link_type.resolves_jira_key:
            if not self.resolved_jira_key:
                raise DomainError(
                    f"{self.link_type.value} link must carry a resolved_jira_key"
                )
            jira_key(self.resolved_jira_key)
        if self.link_type is LinkType.DERIVED_FROM_COMMIT and not self.selection_basis:
            raise DomainError(
                "derived-from-commit link must record its selection_basis (BR-3.3)"
            )


@dataclass(frozen=True, slots=True)
class TestCase:
    """11. The case itself.

    Two invariants hold at construction: at least one step, and every step carrying
    an expected result. A TestCase that violates either was never created, so no
    later layer has to check for it.
    """

    id: str
    feature_id: int
    coverage_item_id: str
    title: str
    test_type: TestType
    steps: list[TestStep]
    expected_result: str
    priority: str = "medium"
    preconditions: str = ""
    test_data: list[TestData] = field(default_factory=list)
    trace_links: list[TraceLink] = field(default_factory=list)
    automatability: AutomatabilityClass = AutomatabilityClass.NEEDS_REVIEW
    automatability_reason: str = ""
    automatability_overridden_by: str | None = None
    tags: list[str] = field(default_factory=list)
    normalised_hash: str | None = None
    bucket_key: str | None = None
    is_obsolete: bool = False
    obsolete_reason: str | None = None
    obsoleted_by_change_id: int | None = None
    created_run_id: int | None = None
    last_modified_run_id: int | None = None

    def __post_init__(self) -> None:
        if decode_id(self.id)[0] is not EntityKind.TEST_CASE:
            raise DomainError(f"Test case id must use the TC prefix, got {self.id!r}")
        if not self.title.strip():
            raise DomainError("TestCase requires a non-empty title")
        if not self.steps:
            raise DomainError(
                f"TestCase {self.id} requires at least one step (FR-TCG-02)"
            )
        ordinals = [s.ordinal for s in self.steps]
        if ordinals != list(range(1, len(ordinals) + 1)):
            raise DomainError(
                f"TestCase {self.id} step ordinals must run 1..{len(ordinals)} "
                f"with no gaps or duplicates, got {ordinals}"
            )
        if not self.expected_result.strip():
            raise DomainError(f"TestCase {self.id} requires an overall expected result")
        if self.is_obsolete and not self.obsolete_reason:
            raise DomainError(f"Obsolete case {self.id} requires a reason")

    @property
    def jira_keys(self) -> list[str]:
        return [
            link.resolved_jira_key
            for link in self.trace_links
            if link.resolved_jira_key is not None
        ]

    @property
    def equivalence_classes(self) -> frozenset[str]:
        return frozenset(d.equivalence_class for d in self.test_data)


@dataclass(frozen=True, slots=True)
class AutomatedTest:
    """15. A generated spec, linked back to the case it came from."""

    id: str
    case_id: str
    spec_path: str
    test_name: str
    page_object_refs: list[str] = field(default_factory=list)
    input_hash: str | None = None
    output_hash: str | None = None
    is_at_risk: bool = False
    at_risk_reason: str | None = None

    def __post_init__(self) -> None:
        if decode_id(self.id)[0] is not EntityKind.AUTOMATED_TEST:
            raise DomainError(f"Automated test id must use the AT prefix, got {self.id!r}")
        if self.is_at_risk and not self.at_risk_reason:
            raise DomainError(f"At-risk test {self.id} requires a reason")


@dataclass(frozen=True, slots=True)
class Run:
    """16. One execution of the pipeline, baseline or delta."""

    correlation_id: str
    kind: str = "baseline"
    operator: str = ""
    started_at: str = field(default_factory=utc_now)
    ended_at: str | None = None
    business_rules: dict[str, Any] = field(default_factory=dict)
    id: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("baseline", "delta"):
            raise DomainError(f"Run kind must be baseline|delta, got {self.kind!r}")


@dataclass(frozen=True, slots=True)
class UnitStateRecord:
    """17. Per-unit, per-stage progress.

    `approved_content_hash` is what makes a gate real: approval binds to what was
    approved, so modifying the content invalidates it (US-COV-04 AC3).
    """

    unit_ref: str
    stage: StageName
    state: UnitState = UnitState.NOT_STARTED
    lease_id: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    approved_content_hash: str | None = None
    failure_reason: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    id: int | None = None

    def __post_init__(self) -> None:
        if self.state is UnitState.IN_PROGRESS and not self.lease_id:
            raise DomainError(f"{self.unit_ref}/{self.stage.value} in-progress requires a lease")
        if self.state is UnitState.FAILED and not self.failure_reason:
            raise DomainError(f"{self.unit_ref}/{self.stage.value} failed requires a reason")


@dataclass(frozen=True, slots=True)
class ChangeEvent:
    """18. A detected delta and its impact."""

    run_id: int
    source: str
    ref_from: str
    ref_to: str
    changed_refs: list[str] = field(default_factory=list)
    jira_keys: list[str] = field(default_factory=list)
    is_unmapped: bool = False
    impact_scale: float = 0.0
    id: int | None = None

    def __post_init__(self) -> None:
        if self.source not in ("bitbucket", "jira"):
            raise DomainError(f"Change source must be bitbucket|jira, got {self.source!r}")
        if not 0.0 <= self.impact_scale <= 1.0:
            raise DomainError(f"impact_scale must be in [0,1], got {self.impact_scale}")


#: Every entity, for schema generation and round-trip testing.
ENTITIES: tuple[type, ...] = (
    Resource,
    Artefact,
    Feature,
    Journey,
    BusinessRule,
    ApiEndpoint,
    Screen,
    UiElement,
    TestableRequirement,
    CoverageItem,
    TestCase,
    TestStep,
    TestData,
    TraceLink,
    AutomatedTest,
    Run,
    UnitStateRecord,
    ChangeEvent,
)


def strongest_link(links: Iterable[TraceLink]) -> TraceLink | None:
    """BR-8.1. The primary link among several; all are retained regardless."""
    ranked = sorted(
        links, key=lambda l: LINK_TYPE_PRECEDENCE.index(l.link_type)
    )
    return ranked[0] if ranked else None
