"""Canonical-form hashing of a coverage model.

BR-U3-4.2. The Test Lead's approval binds to this digest, so its determinism is
load-bearing: a hash that varied across runs would invalidate every approval in the
corpus for no reason, and one that ignored a material change would keep an approval
the Test Lead never gave to the content it now covers.

Pure: takes items as arguments, returns a string.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Protocol


class HashableItem(Protocol):
    """The six fields BR-U3-4.2 puts in the digest."""

    id: str
    requirement_id: str
    planned_count: int
    is_required: bool


def canonical_payload(items: Iterable[Any]) -> list[list[Any]]:
    """Order-independent, prose-free.

    Rationale text is excluded: rewording it does not change what will be tested, and
    forcing re-approval for a typo fix trains the Test Lead to approve without
    reading - which defeats the gate more thoroughly than a loose hash ever could.

    `is_required` is included: a test type flipping to not-required changes coverage
    materially while leaving the planned total unchanged, so a counts-only digest
    would miss it.
    """
    rows = []
    for item in sorted(items, key=lambda i: i.id):
        test_type = getattr(item.test_type, "value", item.test_type)
        technique = getattr(item.technique, "value", item.technique)
        rows.append([
            item.id,
            item.requirement_id,
            test_type,
            technique,
            int(item.planned_count),
            bool(item.is_required),
        ])
    return rows


def coverage_hash(items: Iterable[Any]) -> str:
    """SHA-256 over the canonical form.

    `separators=(",", ":")` is pinned deliberately. Python's default JSON separators
    include a space after each comma - stable within a version, not guaranteed across
    them. A formatting change in the standard library must not be able to invalidate
    every approval in the corpus.
    """
    payload = json.dumps(
        canonical_payload(items), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def next_version(previous: tuple[int, str | None] | None, digest: str) -> tuple[int, bool]:
    """BR-U3-4.1. Returns (version, changed).

    An unchanged rebuild reuses the version, so the operator re-running coverage to
    check something does not cost the Test Lead a second approval of the same model.
    """
    if previous is None:
        return 1, True
    version, previous_hash = previous
    if previous_hash == digest:
        return version, False
    return version + 1, True
