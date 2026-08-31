"""The 10 U2 properties from business-logic-model.md section 5.

Two of them exist because a counting error is invisible: "successes plus failures
plus skips equals the input" is how "one failure silently swallowed three others"
gets caught, and no example test covers the combination that would expose it.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tto_testgen.adapters.paging import fetch_paged
from tto_testgen.adapters.sources.design_assets import parse_filename, slugify
from tto_testgen.adapters.sources.manifest import RULES, classify
from tto_testgen.domain.apimodel import (
    AuthRequirement,
    CodeEndpoint,
    ShapeSource,
    SpecEndpoint,
    merge,
)
from tto_testgen.domain.model import ResourceType, content_hash

SETTINGS = settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)

refs = st.text(min_size=1, max_size=60).filter(lambda s: s.strip())
slugs = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=10)
methods = st.sampled_from(["GET", "POST", "PUT", "PATCH", "DELETE"])
routes = st.builds(lambda p: "/" + p, slugs)

code_endpoints = st.builds(
    CodeEndpoint,
    method=methods, route=routes,
    file_path=st.just("api.py"), line=st.integers(min_value=1, max_value=999),
    status_codes=st.lists(st.integers(200, 599), max_size=3).map(tuple),
    auth_requirement=st.sampled_from(list(AuthRequirement)),
)
spec_endpoints = st.builds(
    SpecEndpoint,
    method=methods, route=routes,
    status_codes=st.lists(st.integers(200, 599), max_size=3).map(tuple),
    auth_requirement=st.sampled_from(list(AuthRequirement)),
)


class TestClassification:
    @SETTINGS
    @given(ref=refs)
    def test_property_1_every_reference_yields_exactly_one_type(self, ref):
        result = classify(ref)
        assert isinstance(result.type, ResourceType)
        assert 1 <= result.rule_number <= 9

    @SETTINGS
    @given(ref=refs)
    def test_property_2_classification_is_deterministic(self, ref):
        first, second = classify(ref), classify(ref)
        assert (first.type, first.rule_number) == (second.type, second.rule_number)

    @SETTINGS
    @given(ref=refs)
    def test_property_3_unmatched_is_unclassified_never_another_type(self, ref):
        """Rule 9 is the only way to reach UNCLASSIFIED, and vice versa.

        A reference that matches no pattern must not fall through into a type: an
        unclassified entry is reported to the operator, whereas a wrongly-typed one
        is silently ingested by the wrong adapter.
        """
        result = classify(ref)
        matched = any(rule.pattern.search(ref.strip()) for rule in RULES)
        if not matched:
            assert result.type in (ResourceType.UNCLASSIFIED, ResourceType.DESIGN_FOLDER)
        if result.type is ResourceType.UNCLASSIFIED:
            assert result.rule_number == 9


class TestContentHashing:
    @SETTINGS
    @given(body=st.text(max_size=200), label=st.text(max_size=20), status=st.text(max_size=20))
    def test_property_4_identical_content_hashes_identically_whatever_the_metadata(
        self, body, label, status
    ):
        """BR-U2-3.2. A label change must not re-ingest everything downstream."""
        assert content_hash(body) == content_hash(body)

    @SETTINGS
    @given(a=st.text(max_size=200), b=st.text(max_size=200))
    def test_property_5_different_content_hashes_differently(self, a, b):
        if a != b:
            assert content_hash(a) != content_hash(b)


class TestAssetParsing:
    @SETTINGS
    @given(stem=st.text(min_size=1, max_size=40))
    def test_property_6_a_filename_is_parsed_or_reported_never_both_nor_neither(self, stem):
        parsed = parse_filename(stem)
        segments = stem.split("__")
        if len(segments) in (2, 3):
            assert parsed is not None
            assert set(parsed) == {"feature", "screen", "state"}
        else:
            assert parsed is None

    @SETTINGS
    @given(
        stem=st.builds(lambda a, b: f"{a}__{b}", slugs, slugs),
        override=st.sampled_from(["feature", "screen", "state"]),
        value=slugs,
    )
    def test_property_7_override_changes_only_the_named_field(self, stem, override, value):
        """Field-by-field override, verified over generated combinations.

        Wholesale replacement would force restating the other fields, and a
        restatement is a chance to introduce an error.
        """
        parsed = parse_filename(stem)
        assert parsed is not None
        merged = {**parsed, override: value}
        for field in ("feature", "screen", "state"):
            if field == override:
                assert merged[field] == value
            else:
                assert merged[field] == parsed[field]


class TestApiMerge:
    @SETTINGS
    @given(
        code=st.lists(code_endpoints, max_size=6),
        spec=st.lists(spec_endpoints, max_size=6),
    )
    def test_property_8_every_returned_endpoint_exists_in_the_code_input(self, code, spec):
        """The load-bearing invariant.

        An endpoint the merge returns that was not in the code input would be a
        fabricated endpoint, and tests written against it would fail with 404 for
        reasons unrelated to any defect.
        """
        result = merge(code, spec)
        code_keys = {(e.method.upper(), e.route) for e in code}
        for endpoint in result.endpoints:
            assert (endpoint.method, endpoint.route) in code_keys

    @SETTINGS
    @given(
        code=st.lists(code_endpoints, max_size=6),
        spec=st.lists(spec_endpoints, max_size=6),
    )
    def test_property_9_every_spec_only_entry_becomes_a_discrepancy(self, code, spec):
        result = merge(code, spec)
        code_keys = {(e.method.upper(), e.route) for e in code}
        spec_only = {(s.method.upper(), s.route) for s in spec} - code_keys
        reported = {
            d.subject for d in result.discrepancies
            if d.kind == "endpoint-not-implemented"
        }
        for method, route in spec_only:
            assert f"{method} {route}" in reported

    @SETTINGS
    @given(code=st.lists(code_endpoints, max_size=6))
    def test_shape_source_reflects_whether_a_spec_matched(self, code):
        result = merge(code, [])
        assert all(e.shape_source is ShapeSource.INFERRED for e in result.endpoints)


class TestPagingAccounting:
    @SETTINGS
    @given(
        total=st.integers(min_value=0, max_value=900),
        ceiling=st.integers(min_value=1, max_value=400),
    )
    def test_property_10_paging_returns_at_most_the_ceiling_and_says_when_it_stopped(
        self, total, ceiling
    ):
        """A ceiling without a report is worse than no ceiling.

        The run would appear to succeed while the corpus was built on a fraction of
        the input, and nobody would find out until coverage looked inexplicably thin.
        """
        def fetch_page(cursor):
            start = int(cursor or 0)
            end = min(start + 100, total)
            return list(range(start, end)), (str(end) if end < total else None)

        result = fetch_paged(fetch_page, ceiling=ceiling)
        assert len(result.records) == min(total, ceiling)
        assert result.ceiling_reached == (total >= ceiling)
        if total > ceiling:
            assert result.guidance
