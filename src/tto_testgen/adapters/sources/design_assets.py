"""A5 DesignAssetAdapter - the Figma screenshot folder.

BR-U2-4. Filename convention with a sidecar manifest overriding field by field.

Field-by-field override lets the manifest correct one attribute without restating the
others - and a restatement is a chance to introduce an error.

Requirements: FR-ING-07, FR-ING-08, FR-ING-10, NFR-SEC-05.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from tto_testgen.platform.result import ErrorCode, Result, err, ok

MANIFEST_NAME = "screens.manifest.yaml"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
SEPARATOR = "__"
OVERRIDABLE = ("feature", "screen", "state", "route", "jira_key")

_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    return _SLUG.sub("-", value.strip().lower()).strip("-")


@dataclass(frozen=True, slots=True)
class ParsedAsset:
    filename: str
    feature: str
    screen: str
    state: str
    route: str | None = None
    jira_key: str | None = None
    content_hash: str = ""
    #: Which field came from the filename and which from the manifest. Field-by-field
    #: override is only auditable if the origin of each value is visible.
    origin: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class DesignAssetParse:
    associated: list[ParsedAsset] = field(default_factory=list)
    unassociated: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.associated) + len(self.unassociated)


def parse_filename(stem: str) -> dict[str, str] | None:
    """Two segments means feature and screen with state defaulting; three means all.

    Requiring exactly three would reject the common `feature__screen.png` for no
    benefit; accepting one or four-plus would be guessing.
    """
    segments = stem.split(SEPARATOR)
    if len(segments) == 2:
        return {"feature": slugify(segments[0]), "screen": slugify(segments[1]),
                "state": "default"}
    if len(segments) == 3:
        return {"feature": slugify(segments[0]), "screen": slugify(segments[1]),
                "state": slugify(segments[2])}
    return None


class DesignAssetAdapter:
    """Satisfies P2 `DesignAssetSource`."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def load_manifest(self) -> Result[dict[str, dict]]:
        path = self._folder / MANIFEST_NAME
        if not path.exists():
            return ok({})
        try:
            # safe_load, not load: this is a file from a shared folder, and a shared
            # folder is an untrusted input (NFR-SEC-05).
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            return err(
                ErrorCode.FAILED_INTERNAL,
                f"{MANIFEST_NAME} is not valid YAML: {exc}",
                remediation=f"Correct the syntax in {MANIFEST_NAME}, or remove it.",
            )
        if not isinstance(loaded, dict):
            return err(ErrorCode.FAILED_INTERNAL,
                       f"{MANIFEST_NAME} must be a mapping of filename to fields")
        return ok(loaded)

    def screenshots(self) -> Result[DesignAssetParse]:
        if not self._folder.exists():
            return err(
                ErrorCode.FAILED_INTERNAL,
                f"design asset folder not found: {self._folder.name}",
                remediation="Create the folder, or remove it from resources.md.",
            )

        manifest_result = self.load_manifest()
        if not manifest_result.ok:
            return manifest_result
        manifest = manifest_result.value

        parse = DesignAssetParse()
        for path in sorted(self._folder.iterdir()):
            if path.suffix.lower() not in IMAGE_SUFFIXES:
                continue

            parsed = parse_filename(path.stem)
            entry = manifest.get(path.name, {})

            if parsed is None and not entry:
                parse.unassociated.append(path.name)       # reported, never guessed
                continue

            values = parsed or {"feature": "", "screen": "", "state": "default"}
            origin = {k: "filename" for k in values}

            for name in OVERRIDABLE:
                if name in entry:
                    values[name] = entry[name]
                    origin[name] = "manifest"

            if not values.get("feature") or not values.get("screen"):
                parse.unassociated.append(path.name)
                continue

            parse.associated.append(ParsedAsset(
                filename=path.name,
                feature=values["feature"], screen=values["screen"],
                state=values.get("state", "default"),
                route=values.get("route"), jira_key=values.get("jira_key"),
                content_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
                origin=origin,
            ))

        return ok(parse)

    def unassociated(self) -> list[str]:
        result = self.screenshots()
        return result.value.unassociated if result.ok else []
