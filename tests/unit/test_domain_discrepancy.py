"""Discrepancy detection. BR-U2-6, FR-ANA-08."""

import pytest

from tto_testgen.domain.apimodel import CodeEndpoint, SpecEndpoint, merge
from tto_testgen.domain.discrepancy import (
    NOT_DISCREPANCIES,
    Discrepancy,
    DiscrepancyKind,
    from_merge,
    rule_contradiction,
    screen_differs_from_design,
    screen_not_in_live,
)


class TestSymmetry:
    def test_both_claims_are_stored_with_their_sources(self):
        # A record holding one claim plus a note about "the other source" reads in
        # one direction only, and the reader often arrives from the other side.
        d = rule_contradiction("qty > 0", "reject with 400", "clamp to 1")
        assert d.source_a == "jira" and d.claim_a == "reject with 400"
        assert d.source_b == "code" and d.claim_b == "clamp to 1"

    def test_neither_claim_is_marked_correct(self):
        d = screen_differs_from_design("checkout", "two columns", "one column")
        assert not hasattr(d, "correct")
        assert not hasattr(d, "winner")

    def test_two_different_sources_are_required(self):
        with pytest.raises(ValueError, match="two different sources"):
            Discrepancy.of(DiscrepancyKind.RULE_CONTRADICTION, "x", "code", "a", "code", "b")

    def test_a_subject_is_required(self):
        with pytest.raises(ValueError, match="subject"):
            Discrepancy.of(DiscrepancyKind.RULE_CONTRADICTION, "  ", "jira", "a", "code", "b")


class TestDetectors:
    def test_screen_not_in_live(self):
        d = screen_not_in_live("checkout")
        assert d.kind is DiscrepancyKind.SCREEN_NOT_IN_LIVE
        assert d.subject == "checkout"

    def test_screen_differs_from_design(self):
        d = screen_differs_from_design("checkout", "two columns", "one column")
        assert d.kind is DiscrepancyKind.SCREEN_DIFFERS_FROM_DESIGN

    def test_rule_contradiction(self):
        d = rule_contradiction("qty > 0", "reject", "clamp")
        assert d.kind is DiscrepancyKind.RULE_CONTRADICTION

    def test_every_kind_has_a_detector_or_arises_from_the_merge(self):
        merge_kinds = {
            DiscrepancyKind.ENDPOINT_NOT_IMPLEMENTED,
            DiscrepancyKind.SHAPE_MISMATCH,
            DiscrepancyKind.STATUS_CODE_UNDOCUMENTED,
            DiscrepancyKind.AUTH_REQUIREMENT_MISMATCH,
        }
        direct_kinds = {
            DiscrepancyKind.SCREEN_NOT_IN_LIVE,
            DiscrepancyKind.SCREEN_DIFFERS_FROM_DESIGN,
            DiscrepancyKind.RULE_CONTRADICTION,
        }
        assert merge_kinds | direct_kinds == set(DiscrepancyKind)


class TestMergeLifting:
    def test_a_merge_discrepancy_lifts_into_the_common_record(self):
        result = merge([], [SpecEndpoint("GET", "/ghost")])
        lifted = from_merge(result.discrepancies[0])
        assert lifted.kind is DiscrepancyKind.ENDPOINT_NOT_IMPLEMENTED
        assert lifted.detected_at

    def test_every_merge_discrepancy_kind_is_liftable(self):
        result = merge(
            [CodeEndpoint("GET", "/o", "f.py", 1, status_codes=(200, 500),
                          inferred_request={"a": 1})],
            [SpecEndpoint("GET", "/o", request_shape={"a": "str"}, status_codes=(200,)),
             SpecEndpoint("PUT", "/o")],
        )
        for discrepancy in result.discrepancies:
            assert from_merge(discrepancy).kind in set(DiscrepancyKind)


class TestBoundary:
    def test_the_non_discrepancy_list_is_documented(self):
        # The tempting mistake is to detect these and drown the real signal.
        assert len(NOT_DISCREPANCIES) >= 4
        assert any("wording" in item for item in NOT_DISCREPANCIES)

    def test_serialisation_round_trips_the_claims(self):
        payload = rule_contradiction("qty > 0", "reject", "clamp").to_dict()
        assert payload["claim_a"] == "reject" and payload["claim_b"] == "clamp"
