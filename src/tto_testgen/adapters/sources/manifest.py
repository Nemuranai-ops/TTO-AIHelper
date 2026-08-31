"""A6 ResourceManifestAdapter - parsing `resources.md`.

BR-U2-1. Nine ordered rules, first match wins, each recording which fired.

Recording the matching rule is what makes a wrong inference diagnosable. When a
Confluence URL is read as a Bitbucket repository, "rule 6 matched /projects/.../repos/"
turns a puzzling failure into a one-line fix; storing only the verdict leaves the
operator guessing among nine rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tto_testgen.domain.model import ResourceType
from tto_testgen.platform.result import ErrorCode, Result, err, ok


@dataclass(frozen=True, slots=True)
class InferenceRule:
    number: int
    name: str
    pattern: re.Pattern[str]
    type: ResourceType


#: Order is a design decision, not an accident of authorship. Rule 2 matches a bare
#: PROJ-123 token and would swallow a JQL string containing one, so rule 3 cannot
#: precede it.
RULES: tuple[InferenceRule, ...] = (
    InferenceRule(1, "jira browse or REST url",
                  re.compile(r"/(?:browse|rest/api/[^/]+/issue)/([A-Z][A-Z0-9]{1,9}-\d+)"),
                  ResourceType.JIRA_ISSUE),
    InferenceRule(2, "bare jira key",
                  re.compile(r"^([A-Z][A-Z0-9]{1,9}-\d+)$"),
                  ResourceType.JIRA_ISSUE),
    InferenceRule(3, "jql query",
                  re.compile(r"(?:[?&]jql=)|(?:^\s*(?:project|issuetype|labels)\s*=)", re.I),
                  ResourceType.JIRA_QUERY),
    InferenceRule(4, "confluence page",
                  re.compile(r"/wiki/spaces/[^/]+/pages/\d+|[?&]pageId=\d+"),
                  ResourceType.CONFLUENCE_PAGE),
    InferenceRule(5, "confluence space",
                  re.compile(r"/wiki/spaces/[^/]+/?$"),
                  ResourceType.CONFLUENCE_SPACE),
    InferenceRule(6, "bitbucket repository",
                  re.compile(r"/projects/[^/]+/repos/[^/]+|bitbucket[^/]*/[^/]+/[^/]+"),
                  ResourceType.BITBUCKET_REPO),
    InferenceRule(7, "openapi specification",
                  re.compile(r"(?:openapi|swagger)\.(?:ya?ml|json)$", re.I),
                  ResourceType.OPENAPI_SPEC),
)

LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)]+)\)|<([^>]+)>|(\S+)")


@dataclass(frozen=True, slots=True)
class ClassifiedResource:
    raw_ref: str
    type: ResourceType
    rule_number: int
    pattern: str

    @property
    def inferred_from(self) -> str:
        return f"rule {self.rule_number}: {self.pattern}"


def classify(raw_ref: str, workspace_root: Path | None = None) -> ClassifiedResource:
    """Apply the rules in order. First match wins."""
    ref = raw_ref.strip()

    for rule in RULES:
        if rule.pattern.search(ref):
            return ClassifiedResource(ref, rule.type, rule.number, rule.name)

    # Rule 8 needs the filesystem, so it sits outside the pattern table.
    candidate = Path(ref)
    if not candidate.is_absolute() and workspace_root is not None:
        candidate = workspace_root / ref
    if candidate.is_dir():
        return ClassifiedResource(ref, ResourceType.DESIGN_FOLDER, 8, "existing directory")

    return ClassifiedResource(ref, ResourceType.UNCLASSIFIED, 9, "no rule matched")


def extract_links(text: str) -> list[str]:
    """Pull candidate references out of Markdown.

    Handles inline links, angle-bracket autolinks and bare tokens on a line. Prose is
    skipped by taking only list items and lines that are a single token.
    """
    refs: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(("-", "*", "+")):
            stripped = stripped.lstrip("-*+ ").strip()
        elif len(stripped.split()) > 1 and "](" not in stripped and not stripped.startswith("<"):
            continue

        match = re.search(r"\[[^\]]*\]\(([^)]+)\)", stripped)
        if match:
            refs.append(match.group(1).strip())
            continue
        match = re.search(r"^<([^>]+)>$", stripped)
        if match:
            refs.append(match.group(1).strip())
            continue
        if stripped:
            refs.append(stripped)
    return refs


class ResourceManifestAdapter:
    """Satisfies P2 `ResourceManifestSource`. Read-only by construction."""

    def __init__(self, manifest_path: Path, workspace_root: Path | None = None) -> None:
        self._path = manifest_path
        self._root = workspace_root or manifest_path.parent

    def parse(self) -> Result[tuple[list[ClassifiedResource], list[str]]]:
        """Returns (classified, unclassifiable-raw-refs).

        A missing manifest is a configuration error reported without creating partial
        state (US-ING-01 AC4).
        """
        if not self._path.exists():
            return err(
                ErrorCode.FAILED_INTERNAL,
                f"resources.md not found at {self._path.name}",
                remediation=f"Create {self._path.name} listing the inputs to ingest.",
            )

        seen: set[str] = set()
        classified: list[ClassifiedResource] = []
        unclassifiable: list[str] = []

        for ref in extract_links(self._path.read_text(encoding="utf-8")):
            if ref in seen:
                continue                                   # US-ING-01 AC3
            seen.add(ref)
            resource = classify(ref, self._root)
            if resource.type is ResourceType.UNCLASSIFIED:
                unclassifiable.append(ref)                 # reported, never guessed
            else:
                classified.append(resource)

        return ok((classified, unclassifiable))
