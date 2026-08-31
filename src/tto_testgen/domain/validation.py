"""D7 IntegrityValidator - the last gate before anything enters the corpus.

BR-7. Ten checks in a fixed order: cheap structural checks before expensive lookups,
so a malformed batch fails before touching the database.

This is the second line of defence, not the first. The same two rules that matter
most - a case must have steps, a case must carry a Jira key - also exist as SQLite
constraints. The validator produces an error the agent can act on; the constraint
makes the rule unbreakable even if a future code path bypasses the validator.
Neither alone is sufficient: a constraint gives an unhelpful error, and a validator
can be forgotten.

Requirements: FR-TCG-01, FR-TCG-02, FR-TRC-01, requirements.md 10.3.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tto_testgen.domain.model import TestCase
from tto_testgen.domain.privacy import screen_case
from tto_testgen.domain.similarity import (
    DEFAULT_THRESHOLD,
    DuplicateFinding,
    NormalisedCase,
    find_duplicate,
    normalise,
)
from tto_testgen.domain.traceability import require_jira_key
from tto_testgen.platform.result import ErrorCode


@dataclass(frozen=True, slots=True)
class Rejection:
    case_ref: str
    code: ErrorCode
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"case": self.case_ref, "code": self.code.value, "detail": self.detail}


@dataclass(slots=True)
class BatchValidation:
    """Outcome of validating a whole batch.

    Every failure is collected rather than the first. At batch sizes of forty or
    more, failing on the first problem would force the agent through as many
    correction rounds as there are faults; collecting them lets one pass fix
    everything (US-TCG-01 AC2).
    """

    accepted: list[TestCase] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.rejections

    @property
    def total(self) -> int:
        return len(self.accepted) + len(self.rejections)

    def summary(self) -> dict[str, object]:
        by_code: dict[str, int] = {}
        for rejection in self.rejections:
            by_code[rejection.code.value] = by_code.get(rejection.code.value, 0) + 1
        return {
            "accepted": len(self.accepted),
            "rejected": len(self.rejections),
            "by_code": by_code,
        }


def validate_case(
    case: TestCase,
    known_keys: frozenset[str],
    *,
    supplied_id: bool = False,
    bucket_candidates: list[tuple[str, NormalisedCase]] | None = None,
    threshold: float = DEFAULT_THRESHOLD,
    privacy_options: dict | None = None,
) -> list[Rejection]:
    """BR-7. Run the ten checks in order. Returns every failure found.

    Checks 2-4 (structure) are enforced at construction by D1, so a TestCase object
    reaching here has already passed them. They are re-stated in the ordering
    documentation for completeness, and check 4 is re-verified because ordinal
    integrity is cheap to confirm and expensive to discover missing.
    """
    failures: list[Rejection] = []
    ref = case.id

    # 1. Identifier not supplied by the caller.
    if supplied_id:
        failures.append(
            Rejection(ref, ErrorCode.REJECTED_SELF_SUPPLIED_ID, "Identifier was caller-supplied")
        )

    # 4. Step ordinals unique and gapless from 1 (D1 also enforces this).
    ordinals = [s.ordinal for s in case.steps]
    if ordinals != list(range(1, len(ordinals) + 1)):
        failures.append(
            Rejection(
                ref,
                ErrorCode.REJECTED_INVALID_STEPS,
                f"Step ordinals must run 1..{len(ordinals)}, got {ordinals}",
            )
        )

    # 5. Data-dependent steps carry an equivalence class.
    missing_class = [d.field_name for d in case.test_data if not d.equivalence_class.strip()]
    if missing_class:
        failures.append(
            Rejection(
                ref,
                ErrorCode.REJECTED_MISSING_EQUIVALENCE_CLASS,
                f"Test data without an equivalence class: {sorted(missing_class)}",
            )
        )

    # 5b. No real personal data in the test data (U4-NFR-SEC-01).
    #
    # A structural property of the case, checked here rather than at the MCP
    # boundary: the pattern set will change as the team learns which false
    # positives bite, and each change is a domain rule, not a wire contract.
    for finding in screen_case(case, **(privacy_options or {})):
        failures.append(
            Rejection(ref, ErrorCode.REJECTED_PERSONAL_DATA, finding.message())
        )

    # 6 and 7. At least one link, and one resolving to a Jira key.
    if not case.trace_links:
        failures.append(
            Rejection(ref, ErrorCode.REJECTED_NO_JIRA_KEY, "Case carries no trace links")
        )
    else:
        resolved = require_jira_key(case.trace_links, known_keys)
        if resolved is None:
            # 8. Distinguish "no key at all" from "key not in the ingested set",
            # because the remediation differs: add a link, versus ingest the issue.
            claimed = [k for k in case.jira_keys]
            if claimed:
                failures.append(
                    Rejection(
                        ref,
                        ErrorCode.REJECTED_UNKNOWN_JIRA_KEY,
                        f"Referenced key(s) not in the ingested set: {sorted(set(claimed))}",
                    )
                )
            else:
                failures.append(
                    Rejection(
                        ref,
                        ErrorCode.REJECTED_NO_JIRA_KEY,
                        "No trace link resolves to a Jira key",
                    )
                )

    # 10. Duplicate detection against pre-selected bucket candidates.
    if bucket_candidates:
        finding: DuplicateFinding | None = find_duplicate(case, bucket_candidates, threshold)
        if finding is not None:
            failures.append(
                Rejection(
                    ref,
                    ErrorCode.REJECTED_DUPLICATE,
                    f"{finding.verdict.value} of {finding.existing_case_id} "
                    f"(similarity {finding.score:.2f})",
                )
            )

    return failures


def validate_batch(
    cases: list[TestCase],
    known_keys: frozenset[str],
    *,
    gate_open: bool = True,
    gate_detail: str = "",
    existing_bucket: dict[str, list[tuple[str, NormalisedCase]]] | None = None,
    threshold: float = DEFAULT_THRESHOLD,
    feature_slug: str = "",
) -> BatchValidation:
    """Validate a whole batch.

    Stage A (the gate) stops the batch; stages B, C and D collect. A closed gate
    makes every case in the batch moot, so continuing wastes work. A malformed case
    does not invalidate its neighbours, so all faults are reported together.

    Intra-batch duplicates are checked as well as corpus duplicates: two identical
    cases arriving in the same payload must not both be accepted.
    """
    result = BatchValidation()

    # Stage A: the gate. Stops the batch.
    if not gate_open:
        result.rejections.append(
            Rejection(
                "batch",
                ErrorCode.REJECTED_GATE_CLOSED,
                gate_detail or "Coverage baseline is not approved for this feature",
            )
        )
        return result

    from tto_testgen.domain.similarity import bucket_key

    seen_in_batch: dict[str, list[tuple[str, NormalisedCase]]] = {}

    for case in cases:
        key = bucket_key(case, feature_slug) if feature_slug else ""
        candidates = list((existing_bucket or {}).get(key, []))
        candidates.extend(seen_in_batch.get(key, []))

        failures = validate_case(
            case,
            known_keys,
            bucket_candidates=candidates,
            threshold=threshold,
        )
        if failures:
            result.rejections.extend(failures)
        else:
            result.accepted.append(case)
            seen_in_batch.setdefault(key, []).append((case.id, normalise(case)))

    # All-or-nothing: a batch with any rejection accepts none of it.
    if result.rejections:
        result.accepted.clear()
    return result
