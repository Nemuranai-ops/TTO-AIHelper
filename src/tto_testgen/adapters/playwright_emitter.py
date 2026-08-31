"""A7 PlaywrightEmitter - renders the corpus into a runnable Playwright project.

The templates are the generated coding standard; this module decides what goes into
them and where the result is written. It holds no policy of its own: the locator
ladder is L12's, the secret rules are L13's, and automatability was decided by D6 in
U4.

Two properties carry the unit:

  - **Determinism** (P-U5-03). No timestamps, no run ids, no absolute paths, and
    every collection explicitly sorted. Set iteration order is stable within a
    process and not across them, so an unsorted set of imports would produce
    identical output all day and different output tomorrow - which looks like a
    hand-edit on a file nobody touched.
  - **Three-outcome emission** (P-U4-04), reached through U4's table with
    `kind='automation'`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from tto_testgen.adapters.templates import TemplateEnvironment, ts_literal
from tto_testgen.domain.locators import property_name, resolve

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")

#: Scaffold files are recorded under this reserved slug. BR-U5-1.4's slug validation
#: rejects angle brackets, so no real feature can collide with it.
PROJECT_SLUG = "<project>"

SCAFFOLD = (
    ("package.json", "package.json.j2"),
    ("playwright.config.ts", "playwright.config.ts.j2"),
    ("tsconfig.json", "tsconfig.json.j2"),
    (".env.example", "env.example.j2"),
    ("README.md", "README.md.j2"),
    ("fixtures/auth.ts", "auth.fixture.ts.j2"),
)


@dataclass(slots=True)
class AutomationManifest:
    written: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    hand_edited: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "written": sorted(self.written),
            "unchanged": sorted(self.unchanged),
            "hand_edited": sorted(self.hand_edited),
        }


def digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _val(row: Any, key: str, default: Any = "") -> Any:
    if isinstance(row, dict):
        value = row.get(key, default)
    else:
        try:
            value = row[key]
        except (KeyError, IndexError, TypeError):
            value = getattr(row, key, default)
    return default if value is None else value


def _class_name(slug: str) -> str:
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", slug) if p]
    return "".join(p[:1].upper() + p[1:] for p in parts) + "Page"


def _slug_of(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return slug or "screen"


def _tags(raw: Any) -> list[str]:
    if isinstance(raw, str):
        import json

        try:
            raw = json.loads(raw)
        except ValueError:
            raw = [raw]
    return sorted(str(t) for t in (raw or []))


def _jira_key(case: Any) -> str:
    links = _val(case, "trace_links", []) or []
    keys = sorted(
        str(_val(l, "resolved_jira_key") or _val(l, "target_ref")) for l in links
    )
    return keys[0] if keys else ""


def _step_lines(step: Any, page_var: str, is_api: bool) -> list[str]:
    """Render a step as an action and an expectation.

    **The expectation is the wait** (FR-AUT-09). No template fragment emits a delay,
    so a fixed wait cannot appear without someone adding it to a reviewed artefact.

    The action is a comment plus a `TODO` rather than a guess at the Playwright call:
    inferring `click` versus `fill` versus `goto` from prose would produce code that
    looks authoritative and is frequently wrong, which is worse for the engineer than
    an explicit placeholder beside the text they need.
    """
    action = str(_val(step, "action"))
    expected = str(_val(step, "expected"))
    if is_api:
        return [
            f"// TODO: perform — {action}",
            f"// expect(response.ok()).toBeTruthy();  // {expected}",
        ]
    return [
        f"// TODO: perform — {action}",
        f"await expect({page_var}).toHaveTitle(/.*/);  "
        f"// replace with the assertion for: {expected}",
    ]


class PlaywrightEmitter:
    """Renders and emits. Deterministic by construction."""

    def __init__(
        self,
        destination: Path,
        env: TemplateEnvironment,
        *,
        playwright_version: str = "1.49.1",
        typescript_version: str = "5.7.2",
        node_types_version: str = "22.10.2",
        project_name: str = "tto-automation",
    ) -> None:
        self._root = Path(destination)
        self._env = env
        self._versions = {
            "playwright_version": playwright_version,
            "typescript_version": typescript_version,
            "node_types_version": node_types_version,
            "project_name": project_name,
        }

    # --- paths -------------------------------------------------------------

    def path_for(self, relative: str) -> Path:
        return self._root / relative

    def spec_path(self, feature_slug: str, *, api: bool = False) -> Path:
        self._require_slug(feature_slug)
        suffix = ".api.spec.ts" if api else ".spec.ts"
        return self._root / "tests" / f"{feature_slug}{suffix}"

    def page_path(self, screen_slug: str) -> Path:
        self._require_slug(screen_slug)
        return self._root / "pages" / f"{screen_slug}.page.ts"

    @staticmethod
    def _require_slug(slug: str) -> None:
        """Refused, not sanitised.

        Rewriting `../etc` to `etc` writes a file the caller did not ask for, which
        is a different wrong answer rather than a right one. Same rule as U4's
        ViewRenderer.
        """
        if not _SLUG.match(slug or ""):
            raise ValueError(
                f"slug {slug!r} is not a safe path segment "
                "(lowercase letters, digits and hyphens only)"
            )

    # --- rendering ----------------------------------------------------------

    def render_page_object(self, screen: Any, elements: Sequence[Any]) -> str:
        resolved = []
        for element in elements:
            locator = resolve(element)
            if locator is None:
                # No semantic locator and no CSS: the element is omitted rather
                # than given an XPath. The case that needed it is marked at risk.
                continue
            resolved.append({
                "property": property_name(element),
                "expression": locator.expression,
                "annotations": list(locator.annotations),
            })
        # Sorted by property name: query order is not a contract, and two runs
        # returning the same rows in a different order must render the same bytes.
        resolved.sort(key=lambda e: e["property"])
        return self._env.render(
            "page-object.ts.j2",
            class_name=_class_name(_slug_of(_val(screen, "screen_name") or _val(screen, "name"))),
            elements=resolved,
            route=_val(screen, "screen_route") or _val(screen, "route") or "",
        )

    def render_spec(
        self, feature_slug: str, feature_name: str, cases: Sequence[Any],
        *, api: bool = False, page_imports: Iterable[str] = (),
    ) -> str:
        groups: dict[str, list[dict[str, Any]]] = {}
        # Identifier order, never insertion order.
        for case in sorted(cases, key=lambda c: str(_val(c, "id"))):
            item = str(_val(case, "coverage_item_id"))
            rendered = {
                "id": str(_val(case, "id")),
                "test_name": f"{_val(case, 'id')} {_val(case, 'title')}",
                "tags": _tags(_val(case, "tags", [])),
                "jira_key": _jira_key(case),
                "coverage_item_id": item,
                "preconditions": str(_val(case, "preconditions")),
                "at_risk_reason": str(_val(case, "at_risk_reason") or ""),
                "steps": [
                    {
                        "ordinal": _val(step, "ordinal"),
                        "action": str(_val(step, "action")),
                        "expected": str(_val(step, "expected")),
                        "lines": _step_lines(step, "page", api),
                    }
                    for step in sorted(
                        _val(case, "steps", []) or [],
                        key=lambda s: _val(s, "ordinal", 0),
                    )
                ],
            }
            groups.setdefault(item, []).append(rendered)

        template = "api-spec.ts.j2" if api else "spec.ts.j2"
        return self._env.render(
            template,
            feature_name=feature_name,
            feature_slug=feature_slug,
            cases=list(cases),
            page_imports=sorted(set(page_imports)),  # sorted: set order is not stable
            groups=[
                {"title": item, "cases": groups[item]} for item in sorted(groups)
            ],
        )

    def render_scaffold(self, *, extra_variables: Iterable[str] = (),
                        at_risk_count: int = 0) -> list[tuple[str, str]]:
        context = {
            **self._versions,
            "extra_variables": sorted(set(extra_variables)),
            "at_risk_count": at_risk_count,
        }
        return [
            (relative, self._env.render(template, **context))
            for relative, template in SCAFFOLD
        ]

    # --- emission ------------------------------------------------------------

    def emit_file(self, path: Path, content: str, feature_slug: str, views,
                  case_count: int = 0) -> str:
        """P-U4-04, reached through U4's table with kind='automation'.

        Hand-edit is evaluated first: a file the engineer edited and that the corpus
        also changed is still a hand-edit. Tuning `playwright.config.ts` is the first
        thing an engineer does to a new project, and a regeneration that reverted it
        would surface as a mysterious CI failure rather than as a lost edit.
        """
        key = str(path)
        fresh = digest(content)
        recorded = views.get(key)
        recorded_hash = None if recorded is None else str(dict(recorded)["content_hash"])

        if path.exists() and recorded_hash is not None:
            if digest(path.read_text(encoding="utf-8")) != recorded_hash:
                return "hand_edited"
        if recorded_hash == fresh and path.exists():
            return "unchanged"

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        views.upsert(key, feature_slug, fresh, case_count, kind="automation")
        return "written"
