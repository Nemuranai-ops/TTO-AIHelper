"""D4 SimilarityAnalyzer - deterministic duplicate detection.

BR-1. Normalise, shingle, compare by Jaccard. Identical at 1.0, near-duplicate at
0.90 or above, distinct below - except that a differing equivalence class is always
material and short-circuits to DISTINCT before the score is computed.

That override exists because two boundary cases at opposite ends of a range share
almost every word. A pure text threshold would reject one and silently halve the
boundary coverage that boundary analysis exists to provide.

PBT targets: PBT-03 invariants - reflexive, symmetric, bounded, deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from tto_testgen.domain.model import TestCase, content_hash

SHINGLE_SIZE = 3
DEFAULT_THRESHOLD = 0.90

_WHITESPACE = re.compile(r"\s+")
_TERMINAL_PUNCT = re.compile(r"[.,;:!?]+$")


class DuplicateVerdict(str, Enum):
    IDENTICAL = "identical"
    NEAR_DUPLICATE = "near-duplicate"
    DISTINCT = "distinct"

    @property
    def rejects(self) -> bool:
        return self in (DuplicateVerdict.IDENTICAL, DuplicateVerdict.NEAR_DUPLICATE)


@dataclass(frozen=True, slots=True)
class NormalisedCase:
    text: str
    hash: str
    classes: frozenset[str]


def _clean(segment: str) -> str:
    return _TERMINAL_PUNCT.sub("", _WHITESPACE.sub(" ", segment.strip().lower()))


def normalise(case: TestCase) -> NormalisedCase:
    """BR-1.1. Concatenate steps in ordinal order, lowercase, collapse whitespace,
    strip terminal punctuation.

    Step order is preserved, not sorted: two cases performing the same actions in a
    different order are different tests, and one may exist precisely to check that
    order matters.

    Data *values* are excluded and equivalence *class labels* retained. Comparing
    values would make every boundary case unique and defeat the check; comparing
    classes keeps "just below minimum" distinct from "just above maximum" while
    still collapsing two cases that both exercise "valid mid-range".
    """
    segments = [
        f"{_clean(step.action)} || {_clean(step.expected)}"
        for step in sorted(case.steps, key=lambda s: s.ordinal)
    ]
    text = " >> ".join(segments)
    return NormalisedCase(
        text=text, hash=content_hash(text), classes=case.equivalence_classes
    )


def bucket_key(case: TestCase, feature_slug: str) -> str:
    """BR-1.5. Candidate selection key, indexed by idx_case_bucket.

    This is the whole performance story. Pairwise comparison at 10,000 cases is
    50 million operations; bucketing narrows the candidate set to cases that could
    plausibly match - typically tens - which is what makes the 200 ms budget in
    NFR-PRF-01 reachable rather than aspirational.
    """
    return f"{feature_slug}|{case.test_type.value}|{len(case.steps)}"


def shingles(text: str, size: int = SHINGLE_SIZE) -> frozenset[str]:
    """Token shingles of `size` consecutive words.

    Short texts yield a single shingle of the whole text rather than an empty set,
    so a one- or two-word case still compares meaningfully instead of scoring 0.0
    against everything.
    """
    tokens = text.split()
    if not tokens:
        return frozenset()
    if len(tokens) < size:
        return frozenset({" ".join(tokens)})
    return frozenset(
        " ".join(tokens[i : i + size]) for i in range(len(tokens) - size + 1)
    )


def similarity(a: NormalisedCase, b: NormalisedCase) -> float:
    """Jaccard similarity of the shingle sets. Always in [0.0, 1.0]."""
    if a.hash == b.hash:
        return 1.0
    sa, sb = shingles(a.text), shingles(b.text)
    if not sa and not sb:
        return 1.0
    union = sa | sb
    if not union:
        return 1.0
    return len(sa & sb) / len(union)


def is_material_difference(a: NormalisedCase, b: NormalisedCase) -> bool:
    """BR-1.4. A differing equivalence class is always material."""
    return a.classes != b.classes


def classify(
    a: NormalisedCase, b: NormalisedCase, threshold: float = DEFAULT_THRESHOLD
) -> DuplicateVerdict:
    """BR-1.3 plus the BR-1.4 override.

    The class check runs first, so a differing class short-circuits to DISTINCT
    without computing similarity - cheaper, and it makes the override unconditional
    rather than a correction applied afterwards.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be in [0,1], got {threshold}")
    if is_material_difference(a, b):
        return DuplicateVerdict.DISTINCT
    score = similarity(a, b)
    if score >= 1.0:
        return DuplicateVerdict.IDENTICAL
    if score >= threshold:
        return DuplicateVerdict.NEAR_DUPLICATE
    return DuplicateVerdict.DISTINCT


@dataclass(frozen=True, slots=True)
class DuplicateFinding:
    verdict: DuplicateVerdict
    existing_case_id: str
    score: float


def find_duplicate(
    candidate: TestCase,
    candidates: list[tuple[str, NormalisedCase]],
    threshold: float = DEFAULT_THRESHOLD,
) -> DuplicateFinding | None:
    """Compare against pre-selected bucket candidates. Returns the first rejection.

    `candidates` comes from an indexed bucket query, never a full scan. Returning
    the strongest match rather than merely the first makes the rejection message
    name the closest existing case, which is what a reviewer needs.
    """
    normalised = normalise(candidate)
    best: DuplicateFinding | None = None
    for existing_id, existing in candidates:
        verdict = classify(normalised, existing, threshold)
        if not verdict.rejects:
            continue
        score = similarity(normalised, existing)
        if best is None or score > best.score:
            best = DuplicateFinding(verdict, existing_id, score)
    return best
