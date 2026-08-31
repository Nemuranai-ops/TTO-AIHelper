import pytest

from tto_testgen.adapters.sqlite.connection import ConnectionSettings, get_connection
from tto_testgen.adapters.sqlite.schema import ensure_schema
from tto_testgen.domain.model import (
    CoverageItem,
    EntityKind,
    Feature,
    TestType as Kind,
    TestableRequirement,
    encode_id,
)


@pytest.fixture
def settings(tmp_path):
    return ConnectionSettings(db_path=tmp_path / "taas.db")


@pytest.fixture
def conn(settings):
    connection = get_connection(settings)
    result = ensure_schema(connection)
    assert result.ok, getattr(result, "message", "")
    yield connection
    connection.close()


@pytest.fixture
def seeded(conn):
    """A feature, requirement and coverage item, so cases have somewhere to attach."""
    from tto_testgen.adapters.sqlite.repositories import unit_of_work

    with unit_of_work(conn) as uow:
        uow.features.upsert(Feature(slug="checkout", name="Checkout"))
        feature_id = conn.execute(
            "SELECT id FROM feature WHERE slug = 'checkout'"
        ).fetchone()[0]
        uow.requirements.upsert(
            TestableRequirement(
                id=encode_id(EntityKind.REQUIREMENT, "checkout", 1),
                feature_id=feature_id,
                statement="Quantity must be between 1 and 99",
            )
        )
        uow.coverage.upsert_many(
            [
                CoverageItem(
                    id=encode_id(EntityKind.COVERAGE_ITEM, "checkout", 1),
                    requirement_id=encode_id(EntityKind.REQUIREMENT, "checkout", 1),
                    test_type=Kind.BOUNDARY,
                    planned_count=3,
                )
            ]
        )
    return feature_id
