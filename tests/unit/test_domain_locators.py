"""L12 LocatorResolver."""

from __future__ import annotations

import json

import pytest

from tto_testgen.domain.locators import (
    FRAGILE_NOTE,
    UNVERIFIED_NOTE,
    property_name,
    rank_of,
    resolve,
)


def element(**overrides):
    base = {
        "role": None, "accessible_name": None, "label": None, "placeholder": None,
        "text": None, "test_id": None, "locator_chain": "[]",
        "is_verified": 1, "is_fragile": 0,
    }
    return {**base, **overrides}


# --- the ladder ----------------------------------------------------------------

def test_role_and_name_rank_first():
    got = resolve(element(role="button", accessible_name="Place order"))
    assert got.rank == 1
    assert got.expression == 'getByRole("button", { name: "Place order" })'


def test_label_ranks_second_when_no_role():
    assert resolve(element(label="Quantity")).expression == 'getByLabel("Quantity")'


def test_placeholder_and_text_rank_third():
    assert resolve(element(placeholder="Search")).rank == 3
    assert resolve(element(text="Continue")).rank == 3


def test_test_id_ranks_fourth():
    assert resolve(element(test_id="submit-btn")).expression == 'getByTestId("submit-btn")'


def test_css_ranks_last_and_is_always_fragile():
    got = resolve(element(locator_chain=json.dumps([".checkout .submit"])))
    assert got.rank == 5
    assert got.is_fragile
    assert FRAGILE_NOTE in got.annotations


def test_the_highest_available_rank_always_wins():
    """PBT-U5-10 as an example. A role outranks a test id even when both exist."""
    got = resolve(element(role="button", accessible_name="Pay", test_id="pay-btn"))
    assert got.rank == 1
    assert "getByTestId" not in got.expression


# --- XPath -----------------------------------------------------------------------

def test_an_xpath_only_chain_yields_no_locator():
    """XPath is absent from the ladder, not last on it.

    Ranking it sixth would still generate it whenever nothing else existed. Returning
    None drops the element and marks the case at risk, which is the honest signal:
    the application should expose the element better.
    """
    assert resolve(element(locator_chain=json.dumps(["//div[3]/button[1]"]))) is None
    assert rank_of(element(locator_chain=json.dumps(["//div[3]"]))) == 6


def test_a_chain_mixing_xpath_and_css_uses_the_css():
    got = resolve(element(locator_chain=json.dumps(["//div[3]", ".submit"])))
    assert got.expression == 'locator(".submit")'


def test_no_locator_at_all_yields_none():
    assert resolve(element()) is None


# --- annotations ------------------------------------------------------------------

def test_an_unverified_element_is_annotated():
    got = resolve(element(role="button", accessible_name="Pay", is_verified=0))
    assert UNVERIFIED_NOTE in got.annotations
    assert got.is_at_risk


def test_a_verified_semantic_locator_is_not_at_risk():
    got = resolve(element(role="button", accessible_name="Pay", is_verified=1))
    assert got.annotations == ()
    assert not got.is_at_risk


def test_a_fragile_flag_is_honoured_even_at_a_good_rank():
    got = resolve(element(role="button", accessible_name="Pay", is_fragile=1))
    assert got.rank == 1
    assert FRAGILE_NOTE in got.annotations


# --- escaping ----------------------------------------------------------------------

def test_a_quote_in_an_accessible_name_is_escaped():
    """The expression must be safe on its own, not only via the template filter."""
    got = resolve(element(role="button", accessible_name='Say "hello"'))
    assert '\\"hello\\"' in got.expression


def test_a_newline_in_a_name_does_not_break_the_expression():
    got = resolve(element(role="link", accessible_name="line one\nline two"))
    assert "\\n" in got.expression
    assert "\n" not in got.expression


# --- property names -------------------------------------------------------------------

@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"accessible_name": "Place order"}, "placeOrder"),
        ({"label": "Card number"}, "cardNumber"),
        ({"test_id": "submit-btn"}, "submitBtn"),
        ({"text": "Continue to payment"}, "continueToPayment"),
        ({"accessible_name": "  Place   order  "}, "placeOrder"),
        ({"accessible_name": "2FA code"}, "el2faCode"),  # digit-leading names get an `el` prefix
        ({"role": "button"}, "button"),
        ({}, "element"),
    ],
)
def test_property_names_are_stable_camel_case(kwargs, expected):
    assert property_name(element(**kwargs)) == expected


def test_property_names_are_deterministic():
    el = element(accessible_name="Place order")
    assert len({property_name(el) for _ in range(20)}) == 1
