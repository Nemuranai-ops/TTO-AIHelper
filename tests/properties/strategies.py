"""Domain-specific Hypothesis strategies (PBT-07).

Unconstrained primitives produce meaningless counterexamples: a random byte string
as a Jira key tests the regex, not the rule. These strategies generate values that
look like the ones the system actually handles, so a failure points at a real defect.
"""

from __future__ import annotations

from hypothesis import strategies as st

from tto_testgen.domain.model import (
    AutomatabilityClass,
    CoverageTechnique,
    EntityKind,
    LinkType,
    TestCase as Case,
    TestData as Data,
    TestStep as Step,
    TestType as Kind,
    TraceLink,
    encode_id,
)

# --- value objects -----------------------------------------------------------

jira_keys = st.builds(
    lambda project, number: f"{project}-{number}",
    st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=2, max_size=10),
    st.integers(min_value=1, max_value=99999),
)

feature_slugs = st.builds(
    lambda parts: "-".join(parts),
    st.lists(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=8),
        min_size=1,
        max_size=3,
    ),
).filter(lambda s: 1 <= len(s) <= 60)

sequences = st.integers(min_value=1, max_value=99999)
entity_kinds = st.sampled_from(list(EntityKind))
type_values = st.sampled_from(list(Kind))
coverage_techniques = st.sampled_from(list(CoverageTechnique))
automatability = st.sampled_from(list(AutomatabilityClass))

#: Realistic step prose rather than arbitrary text: normalisation strips case and
#: punctuation, so the generator must produce values where that actually matters.
_ACTIONS = [
    "Open the checkout page",
    "Enter a valid quantity",
    "Submit the order",
    "Select express delivery",
    "Apply the discount code",
    "Confirm the payment",
]
_EXPECTATIONS = [
    "The order summary is shown",
    "The value is accepted",
    "A validation message appears",
    "The request returns 200",
    "The request returns 422",
]
_CLASSES = [
    "valid-mid-range",
    "just-below-minimum",
    "just-above-maximum",
    "empty",
    "non-numeric",
]

steps = st.builds(
    lambda ordinal, action, expected: Step(ordinal, action, expected),
    st.just(1),
    st.sampled_from(_ACTIONS),
    st.sampled_from(_EXPECTATIONS),
)


@st.composite
def step_lists(draw, min_size: int = 1, max_size: int = 6):
    """Ordinals must run 1..n with no gaps, so they are assigned rather than drawn."""
    count = draw(st.integers(min_value=min_size, max_value=max_size))
    actions = draw(st.lists(st.sampled_from(_ACTIONS), min_size=count, max_size=count))
    expectations = draw(st.lists(st.sampled_from(_EXPECTATIONS), min_size=count, max_size=count))
    return [
        Step(index + 1, action, expected)
        for index, (action, expected) in enumerate(zip(actions, expectations))
    ]


data_values = st.builds(
    lambda name, value, cls: Data(name, value, cls),
    st.sampled_from(["quantity", "email", "postcode", "amount"]),
    st.text(min_size=1, max_size=12).filter(lambda s: s.strip()),
    st.sampled_from(_CLASSES),
)


@st.composite
def trace_links(draw, resolving: bool = True):
    key = draw(jira_keys)
    link_type = (
        draw(st.sampled_from([LinkType.DIRECT_STORY, LinkType.DERIVED_FROM_COMMIT]))
        if resolving
        else draw(st.sampled_from([LinkType.CONFLUENCE, LinkType.CODE_SYMBOL, LinkType.SCREENSHOT]))
    )
    return TraceLink(
        source_kind="test_case",
        source_id="x",
        target_ref=key if resolving else "page/123",
        link_type=link_type,
        evidence=draw(st.text(max_size=20)),
        selection_basis="generated" if link_type is LinkType.DERIVED_FROM_COMMIT else None,
        resolved_jira_key=key if resolving else None,
    )


@st.composite
def cases(draw, slug: str | None = None, with_links: bool = True):
    feature = slug or draw(feature_slugs)
    sequence = draw(sequences)
    return Case(
        id=encode_id(EntityKind.TEST_CASE, feature, sequence),
        feature_id=draw(st.integers(min_value=1, max_value=50)),
        coverage_item_id=encode_id(EntityKind.COVERAGE_ITEM, feature, draw(sequences)),
        title=draw(st.text(min_size=1, max_size=40).filter(lambda s: s.strip())),
        test_type=draw(type_values),
        steps=draw(step_lists()),
        expected_result=draw(st.sampled_from(_EXPECTATIONS)),
        test_data=draw(st.lists(data_values, max_size=3)),
        trace_links=draw(st.lists(trace_links(), min_size=1, max_size=2)) if with_links else [],
        automatability=draw(automatability),
        tags=draw(st.lists(st.sampled_from(["smoke", "regression", "ui", "api"]), max_size=3)),
    )
