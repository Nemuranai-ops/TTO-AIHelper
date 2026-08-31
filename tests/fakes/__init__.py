"""Shared in-memory port implementations.

One fake per port, shared by every unit (Units Generation Q5, contract-first). Not
per-unit stubs: eight independent in-memory repositories would drift, and the
drift would surface only at integration, which is exactly what contract-first
exists to prevent.
"""

from tests.fakes.repositories import (
    FakeArtefactRepository,
    FakeCoverageRepository,
    FakeEmittedViewRepository,
    FakeFeatureRepository,
    FakeGapRepository,
    FakeRequirementRepository,
    FakeRunStateRepository,
    FakeTestCaseRepository,
    FakeTraceRepository,
    FakeUnitOfWork,
    fake_unit_of_work,
)
from tests.fakes.commands import FakeCommandRunner, failing, timing_out
from tests.fakes.sources import (
    FakeBitbucketSource,
    FakeConfluenceSource,
    FakeDesignAssetSource,
    FakeJiraSource,
    FakeResourceManifestSource,
)

__all__ = [
    "FakeCommandRunner",
    "failing",
    "timing_out",
    "FakeArtefactRepository",
    "FakeCoverageRepository",
    "FakeEmittedViewRepository",
    "FakeFeatureRepository",
    "FakeGapRepository",
    "FakeRequirementRepository",
    "FakeRunStateRepository",
    "FakeTestCaseRepository",
    "FakeTraceRepository",
    "FakeUnitOfWork",
    "fake_unit_of_work",
    "FakeBitbucketSource",
    "FakeConfluenceSource",
    "FakeDesignAssetSource",
    "FakeJiraSource",
    "FakeResourceManifestSource",
]
