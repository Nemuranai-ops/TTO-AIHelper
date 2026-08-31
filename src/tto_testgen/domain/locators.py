"""L12 LocatorResolver - the ranked ladder from a UI element to a Playwright locator.

Pure: an element record in, a value out. No I/O, no template, no database - which
keeps it inside the `domain-is-pure` contract and makes PBT-U5-10 testable without
either.

**XPath is absent from the ladder, not last on it.** Ranking it sixth would still
generate it whenever nothing else existed. Omitting it means the element is dropped
and the case is marked at risk, which is the honest signal: an element with no role,
no label, no text and no test id is one the application should expose better, and a
generated XPath would hide that behind a selector that breaks on the first refactor
(R-04).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: Rank 5 is CSS and is always fragile. There is no rank 6.
MAX_RANK = 5

UNVERIFIED_NOTE = (
    "UNVERIFIED: derived from the design model, not confirmed against a running "
    "application. Confirm before relying on this test's result."
)
FRAGILE_NOTE = (
    "FRAGILE: structural selector with no semantic alternative recorded. Expect "
    "this to break on UI change."
)


@dataclass(frozen=True, slots=True)
class ResolvedLocator:
    """A Playwright locator expression and what is known about its trustworthiness."""

    expression: str
    rank: int
    is_verified: bool
    is_fragile: bool
    annotations: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_at_risk(self) -> bool:
        """Unconfirmed, or structural with nothing better available.

        Not the same as wrong. The flag exists so the automation report can say how
        much of the suite rests on underived evidence without anyone reading the
        generated code to find out.
        """
        return not self.is_verified or self.is_fragile


def _text(row: Any, key: str) -> str:
    value = row.get(key) if isinstance(row, dict) else getattr(row, key, None)
    try:
        value = row[key] if value is None and not isinstance(row, dict) else value
    except (KeyError, IndexError, TypeError):
        pass
    return "" if value is None else str(value).strip()


def _flag(row: Any, key: str) -> bool:
    value = row.get(key) if isinstance(row, dict) else getattr(row, key, None)
    try:
        value = row[key] if value is None and not isinstance(row, dict) else value
    except (KeyError, IndexError, TypeError):
        pass
    return bool(value)


def _chain(row: Any) -> list[str]:
    raw = _text(row, "locator_chain")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except ValueError:
        return [raw]
    return [str(item) for item in parsed] if isinstance(parsed, list) else [str(parsed)]


def _js(value: str) -> str:
    """A quoted JS string. Escaping lives here too, not only in the template filter:
    an expression assembled in the domain must be safe on its own."""
    return json.dumps(value, ensure_ascii=False)


def rank_of(element: Any) -> int:
    """The rank the ladder would assign, without building the expression."""
    resolved = resolve(element)
    return resolved.rank if resolved is not None else MAX_RANK + 1


def resolve(element: Any) -> ResolvedLocator | None:
    """The highest-ranked locator the element supports, or None.

    First match wins. Ranked rather than scored because there is no situation where
    a CSS selector outranks an accessible role - the role is what the user perceives
    and it survives the structural changes CSS does not. A weighting would only hide
    a fixed order behind arithmetic that always gives the same answer.
    """
    role = _text(element, "role")
    name = _text(element, "accessible_name")
    label = _text(element, "label")
    placeholder = _text(element, "placeholder")
    text = _text(element, "text")
    test_id = _text(element, "test_id")
    verified = _flag(element, "is_verified")
    fragile = _flag(element, "is_fragile")

    expression, rank = "", 0
    if role and name:
        expression, rank = f"getByRole({_js(role)}, {{ name: {_js(name)} }})", 1
    elif role:
        expression, rank = f"getByRole({_js(role)})", 1
    elif label:
        expression, rank = f"getByLabel({_js(label)})", 2
    elif placeholder:
        expression, rank = f"getByPlaceholder({_js(placeholder)})", 3
    elif text:
        expression, rank = f"getByText({_js(text)})", 3
    elif test_id:
        expression, rank = f"getByTestId({_js(test_id)})", 4
    else:
        css = next((step for step in _chain(element) if not step.startswith("/")), "")
        if not css:
            # Only an XPath chain, or nothing at all. Both yield no locator: the
            # element is omitted and the case is marked at risk.
            return None
        expression, rank = f"locator({_js(css)})", 5

    notes: list[str] = []
    if not verified:
        notes.append(UNVERIFIED_NOTE)
    if rank == MAX_RANK or fragile:
        notes.append(FRAGILE_NOTE)

    return ResolvedLocator(
        expression=expression,
        rank=rank,
        is_verified=verified,
        is_fragile=fragile or rank == MAX_RANK,
        annotations=tuple(notes),
    )


def property_name(element: Any) -> str:
    """A stable camelCase identifier for the page-object property.

    Derived from the accessible name, label, text or test id - in that order, so the
    name a reader recognises wins over an internal identifier. Deterministic, because
    the property name is part of the rendered bytes.
    """
    source = (
        _text(element, "accessible_name")
        or _text(element, "label")
        or _text(element, "text")
        or _text(element, "test_id")
        or _text(element, "role")
        or "element"
    )
    # ASCII only, deliberately. `str.isalnum()` is true for characters whose
    # lowercase form is not a valid identifier: Turkish dotted capital I (U+0130)
    # lowercases to `i` plus a combining dot above, which would emit TypeScript that
    # does not compile. Restricting the alphabet is the fix; a Unicode-aware
    # identifier rule would be correct in principle and would still have to handle
    # combining marks case by case.
    ascii_only = "".join(
        c if (c.isascii() and c.isalnum()) else " " for c in source
    )
    parts = [p for p in ascii_only.split() if p]
    if not parts:
        return "element"
    head, *rest = parts
    name = head.lower() + "".join(p.capitalize() for p in rest)
    return name if name[0].isalpha() else f"el{name[0].upper()}{name[1:]}"
