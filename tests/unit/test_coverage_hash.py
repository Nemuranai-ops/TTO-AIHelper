"""Canonical-form hashing. BR-U3-4.2, U3-NFR-PRF-03.

These are the tests the Test Lead's approval rests on: they define exactly what
"modifying an approved model" means.
"""

from dataclasses import dataclass

import pytest

from tto_testgen.domain.coverage_hash import canonical_payload, coverage_hash, next_version


@dataclass
class Item:
    id: str
    requirement_id: str = "TR-CHECKOUT-00001"
    test_type: str = "boundary"
    technique: str = "boundary-value-analysis"
    planned_count: int = 6
    is_required: bool = True
    rationale: str = "some rationale"


def items(*ids, **kw):
    return [Item(id=i, **kw) for i in ids]


class TestDeterminism:
    def test_identical_items_hash_identically(self):
        assert coverage_hash(items("CI-A-00001")) == coverage_hash(items("CI-A-00001"))

    def test_order_does_not_matter(self):
        forward = items("CI-A-00001", "CI-A-00002", "CI-A-00003")
        assert coverage_hash(forward) == coverage_hash(list(reversed(forward)))

    def test_payload_is_sorted_by_id(self):
        payload = canonical_payload(items("CI-A-00003", "CI-A-00001"))
        assert [row[0] for row in payload] == ["CI-A-00001", "CI-A-00003"]

    def test_separators_are_pinned(self):
        """Python's default JSON separators include a space after each comma.

        Stable within a version, not guaranteed across them. The approval binds to
        this digest, so a stdlib formatting change must not be able to invalidate
        every approval in the corpus.
        """
        import inspect

        from tto_testgen.domain import coverage_hash as module

        source = inspect.getsource(module.coverage_hash)
        assert 'separators=(",", ":")' in source

    def test_hash_is_hex_sha256(self):
        digest = coverage_hash(items("CI-A-00001"))
        assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)


class TestSensitivity:
    """What counts as a modification."""

    def test_changing_planned_count_changes_the_hash(self):
        assert coverage_hash(items("CI-A-00001", planned_count=6)) != coverage_hash(
            items("CI-A-00001", planned_count=7)
        )

    def test_changing_is_required_changes_the_hash(self):
        # A test type flipping to not-required changes coverage materially while
        # leaving the planned total unchanged. A counts-only digest would miss it.
        required = [Item("CI-A-00001", planned_count=0, is_required=True)]
        not_required = [Item("CI-A-00001", planned_count=0, is_required=False)]
        assert coverage_hash(required) != coverage_hash(not_required)

    def test_changing_test_type_changes_the_hash(self):
        assert coverage_hash(items("CI-A-00001", test_type="boundary")) != coverage_hash(
            items("CI-A-00001", test_type="validation")
        )

    def test_changing_technique_changes_the_hash(self):
        assert coverage_hash(
            items("CI-A-00001", technique="decision-table")
        ) != coverage_hash(items("CI-A-00001", technique="state-transition"))

    def test_adding_an_item_changes_the_hash(self):
        assert coverage_hash(items("CI-A-00001")) != coverage_hash(
            items("CI-A-00001", "CI-A-00002")
        )


class TestInsensitivity:
    def test_changing_rationale_does_not_change_the_hash(self):
        # Requiring re-approval for a typo fix trains the Test Lead to approve
        # without reading, which defeats the gate more thoroughly than a loose hash.
        a = [Item("CI-A-00001", rationale="original wording")]
        b = [Item("CI-A-00001", rationale="corrected wording")]
        assert coverage_hash(a) == coverage_hash(b)

    def test_rationale_is_absent_from_the_payload(self):
        payload = canonical_payload([Item("CI-A-00001", rationale="secret")])
        assert "secret" not in str(payload)

    def test_enum_values_are_unwrapped(self):
        from enum import Enum

        class Kind(str, Enum):
            BOUNDARY = "boundary"

        wrapped = [Item("CI-A-00001", test_type=Kind.BOUNDARY)]
        plain = [Item("CI-A-00001", test_type="boundary")]
        assert coverage_hash(wrapped) == coverage_hash(plain)


class TestVersioning:
    def test_first_build_is_version_one(self):
        version, changed = next_version(None, "a" * 64)
        assert (version, changed) == (1, True)

    def test_unchanged_rebuild_reuses_the_version(self):
        # An operator re-running coverage to check something must not cost the Test
        # Lead a second approval of the same model.
        version, changed = next_version((3, "a" * 64), "a" * 64)
        assert (version, changed) == (3, False)

    def test_changed_rebuild_increments(self):
        version, changed = next_version((3, "a" * 64), "b" * 64)
        assert (version, changed) == (4, True)

    def test_a_previous_build_with_no_hash_is_treated_as_changed(self):
        version, changed = next_version((3, None), "a" * 64)
        assert (version, changed) == (4, True)
