"""D5 IdentifierAllocator - stable identifiers the model never supplies.

BR-6. Allocation belongs to the toolchain: an identifier supplied by the caller is
rejected, because an identifier the model chose is one it can reuse, collide or
reformat, and 6,000 cases cannot be reconciled after that.

PBT targets: PBT-02 round-trip (decode(encode(id)) == id),
PBT-03 invariants (uniqueness, strict monotonicity).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from tto_testgen.domain.model import (
    DomainError,
    EntityKind,
    decode_id,
    encode_id,
)

MAX_SEQUENCE = 99999


@dataclass(frozen=True, slots=True)
class SequenceState:
    """The high-water mark per (kind, feature).

    Immutable: `advance` returns a new state. That makes allocation a pure function
    of its input, which is what lets the property tests drive it without a database.
    """

    counters: dict[tuple[EntityKind, str], int] = field(default_factory=dict)

    def peek(self, kind: EntityKind, slug: str) -> int:
        return self.counters.get((kind, slug), 0)

    def advance(self, kind: EntityKind, slug: str) -> "SequenceState":
        key = (kind, slug)
        return SequenceState({**self.counters, key: self.counters.get(key, 0) + 1})

    @classmethod
    def from_existing(cls, identifiers: list[str]) -> "SequenceState":
        """Rebuild the high-water marks from identifiers already issued.

        Used on startup so a restarted process never reissues a number. Takes the
        maximum rather than the count, because obsolete cases are retained and a
        count would collide with them.
        """
        counters: dict[tuple[EntityKind, str], int] = {}
        for identifier in identifiers:
            kind, slug, sequence = decode_id(identifier)
            key = (kind, slug)
            counters[key] = max(counters.get(key, 0), sequence)
        return cls(counters)


class SequenceExhausted(DomainError):
    """99,999 identifiers issued for one kind in one feature.

    Raised rather than wrapped: wrapping would reissue a live identifier, which is
    silent corruption. Failing loudly is the only safe response.
    """


def allocate(
    kind: EntityKind, slug: str, state: SequenceState
) -> tuple[str, SequenceState]:
    """Issue the next identifier for (kind, slug). Pure: returns the new state."""
    nxt = state.peek(kind, slug) + 1
    if nxt > MAX_SEQUENCE:
        raise SequenceExhausted(
            f"Sequence exhausted for {kind.value} in feature {slug!r} "
            f"(limit {MAX_SEQUENCE})"
        )
    return encode_id(kind, slug, nxt), state.advance(kind, slug)


def allocate_many(
    kind: EntityKind, slug: str, count: int, state: SequenceState
) -> tuple[list[str], SequenceState]:
    """Issue `count` consecutive identifiers in one pass.

    A batch of test cases commits atomically, so its identifiers are allocated
    together. Allocating one at a time would leave gaps if the batch rolled back.
    """
    if count < 0:
        raise DomainError(f"Cannot allocate a negative count: {count}")
    issued: list[str] = []
    current = state
    for _ in range(count):
        identifier, current = allocate(kind, slug, current)
        issued.append(identifier)
    return issued, current


def stable_id_for(
    candidate_coverage_item_id: str,
    candidate_title: str,
    existing: list[tuple[str, str, str, bool]],
) -> str | None:
    """BR-6.2 stability. Return the identifier a regenerated case should keep.

    `existing` is (case_id, coverage_item_id, title, is_obsolete). A case matching
    on coverage item and title keeps its identifier across regeneration; obsolete
    cases are skipped so a retired case cannot reclaim its number.
    """
    for case_id, coverage_item_id, title, is_obsolete in existing:
        if is_obsolete:
            continue
        if coverage_item_id == candidate_coverage_item_id and title == candidate_title:
            return case_id
    return None
