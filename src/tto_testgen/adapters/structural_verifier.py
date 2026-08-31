"""L15 StructuralVerifier - the checks that need no toolchain.

These always run, and readiness depends on them. They catch the failure US-HND-02 AC4
names - a spec importing a page object that was never generated - which is the common
one, needs no compiler, and completes in milliseconds.

Imports are found by regular expression rather than by parsing TypeScript. The
question is *whether a referenced file exists*, which needs no parser; adding one
would introduce a second implementation of TypeScript's module resolution that could
disagree with the real one, and a verification step that disagrees with the compiler
is worse than one that checks less (U6-NFR-MNT-03).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tto_testgen.domain.secrets import scan_value

#: FR-HND-01's list. Checked for presence rather than assumed: U5 might not have run,
#: or might have run for one feature and not the rest, and "the directory looks like a
#: project" is not the same as "the project is complete".
REQUIRED_FILES = (
    "package.json",
    "playwright.config.ts",
    "tsconfig.json",
    ".env.example",
    ".gitignore",
    "README.md",
    "fixtures/auth.ts",
)

_IMPORT = re.compile(r"""from\s+['"](\.\.?/[^'"]+)['"]""")
_ABSOLUTE_POSIX = re.compile(r"(?<![\w.])/(?:Users|home|var|opt|private)/[\w.\-/]+")
_ABSOLUTE_WINDOWS = re.compile(r"[A-Za-z]:\\(?:[\w.\-]+\\)+[\w.\-]+")
_TEXT_SUFFIXES = {".ts", ".json", ".md", ".example", ".gitignore"}


@dataclass(frozen=True, slots=True)
class Check:
    """One structural assertion. A finding always names a file (U6-NFR-MNT-04)."""

    name: str
    passed: bool
    location: str = ""
    detail: str = ""


class StructuralVerifier:
    """Runs the check set. Reports; never repairs."""

    def __init__(self, *, extra_credential_fields: frozenset[str] = frozenset()) -> None:
        self._extra_credential_fields = extra_credential_fields

    def verify(self, project_root: Path) -> list[Check]:
        checks: list[Check] = []
        checks += self._required_files(project_root)
        checks += self._imports_resolve(project_root)
        checks += self._no_absolute_paths(project_root)
        checks += self._no_credentials(project_root)
        return checks

    # --- the checks ------------------------------------------------------------

    def _required_files(self, root: Path) -> list[Check]:
        return [
            Check(
                name=f"required file present: {relative}",
                passed=(root / relative).exists(),
                location=relative,
                detail="" if (root / relative).exists() else "file is missing",
            )
            for relative in REQUIRED_FILES
        ]

    def _imports_resolve(self, root: Path) -> list[Check]:
        """US-HND-02 AC4: a spec referencing a page object that was never generated."""
        checks: list[Check] = []
        for source in self._sources(root, "*.ts"):
            try:
                text = source.read_text(encoding="utf-8")
            except OSError as exc:
                checks.append(Check(f"readable: {source.name}", False,
                                    str(source.relative_to(root)), str(exc)))
                continue
            for target in sorted(set(_IMPORT.findall(text))):
                resolved = (source.parent / target).resolve()
                # Appended, never `with_suffix`: a module named `checkout.page`
                # already has a suffix, and `with_suffix(".ts")` would replace `.page`
                # and look for `checkout.ts` - a file that never exists, so every
                # correct import would report as broken.
                exists = resolved.exists() or any(
                    resolved.with_name(resolved.name + suffix).exists()
                    for suffix in (".ts", ".tsx")
                )
                checks.append(
                    Check(
                        name=f"import resolves: {source.name} -> {target}",
                        passed=exists,
                        location=str(source.relative_to(root)),
                        detail="" if exists else f"{target} does not exist",
                    )
                )
        return checks

    def _no_absolute_paths(self, root: Path) -> list[Check]:
        """An absolute path names the generating workstation.

        Useless to a reader on another machine, and a small disclosure about the
        operator's environment in a file that is about to be pushed.
        """
        checks: list[Check] = []
        for source in self._text_files(root):
            text = self._read(source)
            if text is None:
                continue
            hit = _ABSOLUTE_POSIX.search(text) or _ABSOLUTE_WINDOWS.search(text)
            checks.append(
                Check(
                    name=f"no absolute path: {source.name}",
                    passed=hit is None,
                    location=str(source.relative_to(root)),
                    detail="" if hit is None else "an absolute path is embedded",
                )
            )
        return checks

    def _no_credentials(self, root: Path) -> list[Check]:
        """U5 refuses a credential before rendering; the only remaining path into the
        assembled project is a hand-edit, and this is the last point before a push."""
        checks: list[Check] = []
        for source in self._text_files(root):
            if source.name == ".env.example":
                # It documents variable names with no values, so its keys read as
                # credential fields by design. Checked separately below.
                continue
            text = self._read(source)
            if text is None:
                continue
            finding = None
            for number, line in enumerate(text.splitlines(), start=1):
                found = scan_value(
                    "generated line", line,
                    extra_credential_fields=self._extra_credential_fields,
                )
                # Only value shapes apply to generated code: a TypeScript property
                # named `password` reading from process.env is correct, not a leak.
                if found is not None and found.kind != "credential-field":
                    finding = (number, found)
                    break
            checks.append(
                Check(
                    name=f"no credential literal: {source.name}",
                    passed=finding is None,
                    location=(
                        str(source.relative_to(root))
                        if finding is None
                        else f"{source.relative_to(root)}:{finding[0]}"
                    ),
                    detail="" if finding is None else finding[1].message(),
                )
            )

        example = root / ".env.example"
        if example.exists():
            text = self._read(example) or ""
            offenders = [
                number
                for number, line in enumerate(text.splitlines(), start=1)
                if "=" in line and not line.lstrip().startswith("#")
                and line.split("=", 1)[1].strip()
            ]
            checks.append(
                Check(
                    name="no values in .env.example",
                    passed=not offenders,
                    location=".env.example"
                    + ("" if not offenders else f":{offenders[0]}"),
                    detail="" if not offenders else "a variable carries a value",
                )
            )
        return checks

    # --- helpers ------------------------------------------------------------------

    @staticmethod
    def _sources(root: Path, pattern: str):
        for directory in ("tests", "pages", "fixtures"):
            yield from sorted((root / directory).glob(pattern))

    @staticmethod
    def _text_files(root: Path):
        """Streamed, one at a time. At ~300 files the project would fit in memory;
        reading one at a time costs nothing and keeps U6-NFR-SCL-03 true rather than
        incidentally satisfied."""
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if "node_modules" in path.parts or path.name == "package-lock.json":
                continue
            if path.suffix in _TEXT_SUFFIXES or path.name in {".gitignore", ".env.example"}:
                yield path

    @staticmethod
    def _read(path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
