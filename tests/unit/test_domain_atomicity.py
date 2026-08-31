"""Atomicity heuristic. BR-U3-2.1, US-TRQ-01."""

import pytest

from tto_testgen.domain.atomicity import check


class TestAtomicStatements:
    @pytest.mark.parametrize(
        "statement",
        [
            "The order total is recalculated when an item is removed",
            "The cart displays the running total",
            "Quantity must be between 1 and 99",
            "The request returns 422 for a negative quantity",
            "An unauthenticated request is rejected",
            # A compound subject is one behaviour, not two.
            "The order total and tax are recalculated when an item is removed",
            "The name and address fields are validated on submit",
        ],
    )
    def test_single_behaviour_passes(self, statement):
        assert check(statement).is_atomic, statement


class TestBundledStatements:
    @pytest.mark.parametrize(
        "statement",
        [
            "The request returns 200 and the order is stored",
            "The system validates the quantity or rejects the request",
            "The order is created and a confirmation email is sent",
        ],
    )
    def test_two_verb_phrases_are_rejected(self, statement):
        verdict = check(statement)
        assert not verdict.is_atomic, statement
        assert verdict.suspected_split
        assert "force_atomic" in verdict.detail

    def test_the_suspected_split_is_shown(self):
        verdict = check("The request returns 200 and the order is stored")
        assert "|" in verdict.suspected_split
        left, right = verdict.suspected_split.split("|")
        assert "returns 200" in left and "order is stored" in right


class TestConservatism:
    """A false rejection costs one resubmission; a false acceptance costs a
    permanently untraceable case. The heuristic errs toward acceptance."""

    @pytest.mark.parametrize(
        "statement",
        [
            "Values between 1 and 99 are accepted",
            "The postcode and country determine the shipping band",
            "Orders placed on Saturday or Sunday ship on Monday",
        ],
    )
    def test_non_verb_conjunctions_pass(self, statement):
        assert check(statement).is_atomic, statement

    def test_a_statement_with_no_conjunction_is_never_rejected(self):
        assert check("The system stores the order").is_atomic


class TestEscape:
    def test_force_atomic_overrides_the_verdict(self):
        # A heuristic with no escape becomes a wall the agent works around by
        # mangling wording.
        bundled = "The request returns 200 and the order is stored"
        assert not check(bundled).is_atomic
        assert check(bundled, force_atomic=True).is_atomic

    def test_an_override_records_that_it_was_used(self):
        verdict = check("a returns 1 and b returns 2", force_atomic=True)
        assert "overridden" in verdict.detail


class TestEdgeCases:
    def test_empty_statement_is_not_atomic(self):
        verdict = check("   ")
        assert not verdict.is_atomic
        assert "empty" in verdict.detail

    def test_whitespace_is_normalised(self):
        assert check("The   cart\n displays  the total").is_atomic

    def test_verdict_is_serialisable(self):
        import json

        json.dumps(check("The cart displays the total").to_dict())

    def test_determinism(self):
        statement = "The request returns 200 and the order is stored"
        assert check(statement) == check(statement)
