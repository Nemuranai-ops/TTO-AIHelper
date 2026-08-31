"""P3 EmitterPorts - output contracts.

Emitters take domain records and a destination, and return a manifest of what was
written. They never read from a repository, so their output is a function of what
they were given - which is what makes byte-identical regeneration (FR-AUT-11)
checkable rather than hopeful.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from tto_testgen.domain.model import TestCase


@dataclass(frozen=True, slots=True)
class WrittenFile:
    path: Path
    content_hash: str
    bytes_written: int


@dataclass(slots=True)
class EmissionManifest:
    files: list[WrittenFile] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)
    hand_edited: list[Path] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.files)


@runtime_checkable
class ViewEmitter(Protocol):
    def emit_feature(self, feature_slug: str, cases: list[TestCase],
                     destination: Path) -> EmissionManifest: ...
    def detect_hand_edits(self, destination: Path) -> list[Path]: ...


@runtime_checkable
class AutomationEmitter(Protocol):
    def emit(self, feature_slug: str, cases: list[TestCase],
             destination: Path) -> EmissionManifest: ...


@runtime_checkable
class ReportEmitter(Protocol):
    def emit(self, kind: str, rows: list[dict[str, object]], destination: Path,
             fmt: str = "markdown") -> EmissionManifest: ...
