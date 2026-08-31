"""L11 TemplateEnvironment - the one configured Jinja2 environment.

Every setting here is a decision, and the defaults are wrong for generated code in
each case. P-U5-02.

`StrictUndefined` is the one that matters. Jinja2's default renders a missing
variable as the empty string, so a typo produces

    readonly submitButton = this.page.getByRole('button', { name: '' });

which **compiles**, passes review, and fails weeks later as a locator matching
nothing in a CI run where the cause is invisible. Strict mode turns it into a
render-time error naming the template and the variable - the same reasoning that
made `foreign_keys = ON` non-negotiable in U1.
"""

from __future__ import annotations

import json
from typing import Any

from jinja2 import Environment, PackageLoader, StrictUndefined

TEMPLATE_PACKAGE = "tto_testgen"
TEMPLATE_DIR = "templates/playwright"


def ts_literal(value: Any) -> str:
    """A correctly quoted JS string literal for any value.

    `json.dumps` rather than a hand-written escaper: JSON string syntax is a subset
    of JavaScript string syntax, and it already handles quotes, backslashes,
    newlines, tabs and control characters. A second implementation would only
    contribute the bug class this filter exists to remove - one unescaped character,
    discovered when a case title happens to contain it.

    `ensure_ascii=False` keeps non-ASCII readable in the generated file rather than
    emitting escape sequences. Determinism is unaffected: same input, same bytes.
    """
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    return json.dumps(str(value), ensure_ascii=False)


def ts_tag(value: Any) -> str:
    """A Playwright tag: the case's own tag, prefixed with `@`.

    Not derived, extended or tidied. Jenkins selects suites by tag expression, and a
    tag the generator invented is one the operator cannot predict (FR-AUT-05).
    """
    text = str(value).strip()
    return ts_literal(text if text.startswith("@") else f"@{text}")


def indent_block(text: str, spaces: int = 2) -> str:
    """Indent every line of a comment block. Deterministic, and it keeps multi-line
    annotations from breaking the surrounding structure."""
    pad = " " * spaces
    return "\n".join(f"{pad}{line}" if line else "" for line in str(text).splitlines())


class TemplateEnvironment:
    """Owns the environment and renders named templates. Nothing else."""

    def __init__(self) -> None:
        self._env = Environment(
            loader=PackageLoader(TEMPLATE_PACKAGE, TEMPLATE_DIR),
            # HTML escaping would corrupt TypeScript. Escaping is per value, through
            # `ts`, which is narrower and correct for this target.
            autoescape=False,
            # A missing variable must fail loudly, not render as nothing.
            undefined=StrictUndefined,
            # The three whitespace settings are determinism, not cosmetics: without
            # them an editor reformatting a template changes the rendered bytes
            # without changing the rendered meaning, and every file then reports as
            # hand-edited on the next run.
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
        self._env.filters["ts"] = ts_literal
        self._env.filters["tag"] = ts_tag
        self._env.filters["comment"] = indent_block

    def render(self, template_name: str, **context: Any) -> str:
        return self._env.get_template(template_name).render(**context)

    def template_names(self) -> list[str]:
        return sorted(self._env.list_templates())
