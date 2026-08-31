"""API model derivation - merging what the code has with what the spec claims.

BR-U2-5. The spec decides shapes; the code decides existence.

That asymmetry is the whole rule. A spec entry with no implementation would generate
tests for an endpoint that returns 404 - failures unrelated to any defect, which erode
trust in a suite faster than missing coverage does. The reverse is safe: an endpoint
in code but absent from the spec genuinely exists, and its shape being inferred is
recorded so a later failure can be judged against the weaker source.

Pure: takes claims as arguments, returns records. No network, no database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ShapeSource(str, Enum):
    SPECIFIED = "specified"
    INFERRED = "inferred"


class AuthRequirement(str, Enum):
    NONE = "none"
    REQUIRED = "required"
    #: Never defaulted to NONE. Defaulting an undetermined auth requirement to
    #: public would hide a security-relevant gap (US-ANA-03 AC3).
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CodeEndpoint:
    """What `bitbucket_endpoints` found."""

    method: str
    route: str
    file_path: str
    line: int
    symbol: str = ""
    status_codes: tuple[int, ...] = ()
    auth_requirement: AuthRequirement = AuthRequirement.UNKNOWN
    inferred_request: dict | None = None
    inferred_responses: dict | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.method.upper(), self.route)


@dataclass(frozen=True, slots=True)
class SpecEndpoint:
    """What an OpenAPI document claims."""

    method: str
    route: str
    request_shape: dict | None = None
    response_shapes: dict | None = None
    status_codes: tuple[int, ...] = ()
    auth_requirement: AuthRequirement = AuthRequirement.UNKNOWN

    @property
    def key(self) -> tuple[str, str]:
        return (self.method.upper(), self.route)


@dataclass(frozen=True, slots=True)
class MergedEndpoint:
    method: str
    route: str
    file_path: str
    line: int
    symbol: str
    request_shape: dict | None
    response_shapes: dict | None
    status_codes: tuple[int, ...]
    auth_requirement: AuthRequirement
    shape_source: ShapeSource


@dataclass(frozen=True, slots=True)
class MergeDiscrepancy:
    kind: str
    subject: str
    source_a: str
    claim_a: str
    source_b: str
    claim_b: str


@dataclass(slots=True)
class ApiMergeResult:
    endpoints: list[MergedEndpoint] = field(default_factory=list)
    discrepancies: list[MergeDiscrepancy] = field(default_factory=list)

    @property
    def inferred_count(self) -> int:
        return sum(1 for e in self.endpoints if e.shape_source is ShapeSource.INFERRED)

    @property
    def specified_count(self) -> int:
        return sum(1 for e in self.endpoints if e.shape_source is ShapeSource.SPECIFIED)


def _shapes_differ(code: CodeEndpoint, spec: SpecEndpoint) -> bool:
    if code.inferred_request is None or spec.request_shape is None:
        return False
    return code.inferred_request != spec.request_shape


def merge(
    code_endpoints: list[CodeEndpoint], spec_endpoints: list[SpecEndpoint]
) -> ApiMergeResult:
    """BR-U2-5.1. Merge, preferring the spec for shapes and the code for existence."""
    result = ApiMergeResult()
    by_key = {spec.key: spec for spec in spec_endpoints}
    code_keys = {endpoint.key for endpoint in code_endpoints}

    for endpoint in code_endpoints:
        spec = by_key.get(endpoint.key)
        subject = f"{endpoint.method.upper()} {endpoint.route}"

        if spec is None:
            result.endpoints.append(
                MergedEndpoint(
                    method=endpoint.method.upper(), route=endpoint.route,
                    file_path=endpoint.file_path, line=endpoint.line, symbol=endpoint.symbol,
                    request_shape=endpoint.inferred_request,
                    response_shapes=endpoint.inferred_responses,
                    status_codes=endpoint.status_codes,
                    auth_requirement=endpoint.auth_requirement,
                    shape_source=ShapeSource.INFERRED,
                )
            )
            continue

        result.endpoints.append(
            MergedEndpoint(
                method=endpoint.method.upper(), route=endpoint.route,
                file_path=endpoint.file_path, line=endpoint.line, symbol=endpoint.symbol,
                request_shape=spec.request_shape,
                response_shapes=spec.response_shapes,
                # Codes found in the handler are kept even when the spec omits them:
                # those are exactly the error paths negative cases derive from.
                status_codes=tuple(sorted(set(endpoint.status_codes) | set(spec.status_codes))),
                auth_requirement=(
                    spec.auth_requirement
                    if endpoint.auth_requirement is AuthRequirement.UNKNOWN
                    else endpoint.auth_requirement
                ),
                shape_source=ShapeSource.SPECIFIED,
            )
        )

        if _shapes_differ(endpoint, spec):
            result.discrepancies.append(
                MergeDiscrepancy(
                    "shape-mismatch", subject,
                    "code", str(endpoint.inferred_request),
                    "openapi", str(spec.request_shape),
                )
            )

        undocumented = set(endpoint.status_codes) - set(spec.status_codes)
        if undocumented:
            result.discrepancies.append(
                MergeDiscrepancy(
                    "status-code-undocumented", subject,
                    "code", f"returns {sorted(undocumented)}",
                    "openapi", f"documents {sorted(spec.status_codes)}",
                )
            )

        if (
            endpoint.auth_requirement is not AuthRequirement.UNKNOWN
            and spec.auth_requirement is not AuthRequirement.UNKNOWN
            and endpoint.auth_requirement is not spec.auth_requirement
        ):
            result.discrepancies.append(
                MergeDiscrepancy(
                    "auth-requirement-mismatch", subject,
                    "code", endpoint.auth_requirement.value,
                    "openapi", spec.auth_requirement.value,
                )
            )

    for key, spec in by_key.items():
        if key in code_keys:
            continue
        # In the spec, not in the code. NOT an endpoint - a discrepancy.
        result.discrepancies.append(
            MergeDiscrepancy(
                "endpoint-not-implemented", f"{key[0]} {key[1]}",
                "openapi", "declared",
                "code", "no handler found",
            )
        )

    return result
