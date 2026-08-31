"""API model merge. BR-U2-5, FR-ANA-04, US-ANA-03."""

import itertools

import pytest

from tto_testgen.domain.apimodel import (
    AuthRequirement,
    CodeEndpoint,
    ShapeSource,
    SpecEndpoint,
    merge,
)


def code(method="GET", route="/orders", **kw):
    return CodeEndpoint(method=method, route=route, file_path="src/api.py", line=1, **kw)


def spec(method="GET", route="/orders", **kw):
    return SpecEndpoint(method=method, route=route, **kw)


class TestExistence:
    def test_code_only_endpoint_exists_with_inferred_shapes(self):
        result = merge([code()], [])
        assert len(result.endpoints) == 1
        assert result.endpoints[0].shape_source is ShapeSource.INFERRED

    def test_spec_only_endpoint_does_not_exist(self):
        """The load-bearing rule.

        An endpoint in the spec with no handler would generate tests for something
        that returns 404 - failures unrelated to any defect.
        """
        result = merge([], [spec(route="/ghost")])
        assert result.endpoints == []
        assert result.discrepancies[0].kind == "endpoint-not-implemented"

    def test_endpoint_in_both_exists_with_specified_shapes(self):
        result = merge([code()], [spec(request_shape={"q": "str"})])
        assert result.endpoints[0].shape_source is ShapeSource.SPECIFIED
        assert result.endpoints[0].request_shape == {"q": "str"}

    def test_every_returned_endpoint_came_from_code(self):
        result = merge([code(), code(method="POST")], [spec(route="/ghost")])
        assert {(e.method, e.route) for e in result.endpoints} == {
            ("GET", "/orders"), ("POST", "/orders")
        }

    def test_method_is_normalised_to_upper_case(self):
        assert merge([code(method="get")], []).endpoints[0].method == "GET"


class TestShapes:
    def test_shape_mismatch_is_recorded_and_the_spec_wins(self):
        result = merge(
            [code(inferred_request={"q": "int"})], [spec(request_shape={"q": "str"})]
        )
        assert result.endpoints[0].request_shape == {"q": "str"}
        assert any(d.kind == "shape-mismatch" for d in result.discrepancies)

    def test_no_mismatch_when_the_code_shape_is_unknown(self):
        result = merge([code()], [spec(request_shape={"q": "str"})])
        assert not any(d.kind == "shape-mismatch" for d in result.discrepancies)


class TestStatusCodes:
    def test_undocumented_codes_are_kept_on_the_endpoint(self):
        # These are exactly the error paths negative test cases derive from.
        result = merge([code(status_codes=(200, 422))], [spec(status_codes=(200,))])
        assert 422 in result.endpoints[0].status_codes

    def test_undocumented_codes_are_also_recorded_as_a_discrepancy(self):
        result = merge([code(status_codes=(200, 422))], [spec(status_codes=(200,))])
        assert any(d.kind == "status-code-undocumented" for d in result.discrepancies)

    def test_agreement_produces_no_discrepancy(self):
        result = merge([code(status_codes=(200,))], [spec(status_codes=(200,))])
        assert result.discrepancies == []


class TestAuthRequirement:
    def test_unknown_in_code_takes_the_spec_value(self):
        result = merge([code()], [spec(auth_requirement=AuthRequirement.REQUIRED)])
        assert result.endpoints[0].auth_requirement is AuthRequirement.REQUIRED

    def test_unknown_is_never_defaulted_to_none(self):
        # Defaulting an undetermined auth requirement to public hides a
        # security-relevant gap (US-ANA-03 AC3).
        result = merge([code()], [])
        assert result.endpoints[0].auth_requirement is AuthRequirement.UNKNOWN

    def test_disagreement_is_recorded_and_the_code_wins(self):
        result = merge(
            [code(auth_requirement=AuthRequirement.REQUIRED)],
            [spec(auth_requirement=AuthRequirement.NONE)],
        )
        assert result.endpoints[0].auth_requirement is AuthRequirement.REQUIRED
        assert any(d.kind == "auth-requirement-mismatch" for d in result.discrepancies)

    def test_no_mismatch_when_either_side_is_unknown(self):
        result = merge([code()], [spec(auth_requirement=AuthRequirement.NONE)])
        assert not any(d.kind == "auth-requirement-mismatch" for d in result.discrepancies)


class TestExhaustiveMergeCases:
    @pytest.mark.parametrize(
        "in_code,in_spec", list(itertools.product([True, False], repeat=2))
    )
    def test_every_presence_combination(self, in_code, in_spec):
        result = merge([code()] if in_code else [], [spec()] if in_spec else [])
        if in_code:
            assert len(result.endpoints) == 1
            expected = ShapeSource.SPECIFIED if in_spec else ShapeSource.INFERRED
            assert result.endpoints[0].shape_source is expected
        else:
            assert result.endpoints == []
            if in_spec:
                assert any(d.kind == "endpoint-not-implemented" for d in result.discrepancies)

    def test_empty_inputs_produce_nothing(self):
        result = merge([], [])
        assert result.endpoints == [] and result.discrepancies == []
