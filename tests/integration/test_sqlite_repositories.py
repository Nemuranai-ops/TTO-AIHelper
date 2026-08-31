"""A1, A2, L1, L2, L3. Requirements: US-ENB-01, US-TRC-01, NFR-REL-01, NFR-SEC-04."""

import sqlite3

import pytest

from tto_testgen.adapters.sqlite import queries as q
from tto_testgen.adapters.sqlite.backup import (
    backup_before,
    export_corpus,
    list_backups,
    prune,
    restore,
)
from tto_testgen.adapters.sqlite.connection import (
    ConfigurationNotApplied,
    ConnectionSettings,
    assert_configuration,
    get_connection,
)
from tto_testgen.adapters.sqlite.repositories import MAX_PAGE_SIZE, unit_of_work
from tto_testgen.adapters.sqlite.schema import (
    current_version,
    migrate_down,
    migrate_up,
    split_statements,
    verify_reversibility,
)
from tto_testgen.adapters.sqlite.migrations import LATEST_VERSION, m001_initial
from tto_testgen.domain.model import (
    EntityKind,
    LinkType,
    TestCase as Case,
    TestData as Data,
    TestStep as Step,
    TestType as Kind,
    TraceLink,
    encode_id,
)


def build_case(feature_id, seq=1, *, steps=None, links=True, key="PAY-12", tags=None):
    trace = (
        [TraceLink("test_case", encode_id(EntityKind.TEST_CASE, "checkout", seq), key,
                   LinkType.DIRECT_STORY, resolved_jira_key=key)]
        if links
        else []
    )
    return Case(
        id=encode_id(EntityKind.TEST_CASE, "checkout", seq),
        feature_id=feature_id,
        coverage_item_id=encode_id(EntityKind.COVERAGE_ITEM, "checkout", 1),
        title=f"case {seq}",
        test_type=Kind.BOUNDARY,
        steps=steps if steps is not None else [Step(1, f"action {seq}", "Accepted")],
        expected_result="ok",
        test_data=[Data("qty", str(seq), f"class-{seq}")],
        trace_links=trace,
        tags=tags or ["regression"],
    )


class TestConnectionConfiguration:
    def test_foreign_keys_are_on(self, conn):
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_wal_journal_mode(self, conn):
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

    def test_configuration_is_asserted_not_merely_set(self, settings):
        # PRAGMA foreign_keys is silently ignored inside a transaction, and an
        # unenforced foreign key is invisible until inconsistent data appears.
        connection = get_connection(settings)
        connection.execute("PRAGMA foreign_keys = OFF")
        with pytest.raises(ConfigurationNotApplied):
            assert_configuration(connection, settings)

    def test_foreign_keys_are_actually_enforced(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO business_rule (feature_id, rule_kind, condition, effect) "
                "VALUES (9999, 'validation', 'x', 'y')"
            )


class TestMigrations:
    def test_migrate_up_reaches_the_latest_version(self, conn):
        assert current_version(conn) == LATEST_VERSION

    def test_schema_has_the_designed_shape(self, conn):
        """Assert what U1 requires, not a global total.

        A count of every table in the database breaks whenever a later unit adds
        one - migration 003 did exactly that - and the failure says nothing about
        whether U1's schema is intact. Naming U1's own objects keeps the test
        meaningful as the schema grows.
        """
        names = lambda t: {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = ?", (t,)
            ).fetchall()
        }
        u1_entities = {
            "resource", "artefact", "feature", "journey", "business_rule",
            "api_endpoint", "screen", "ui_element", "testable_requirement",
            "coverage_item", "test_case", "test_step", "test_data", "trace_link",
            "automated_test", "run", "unit_state", "change_event",
        }
        u1_machinery = {"schema_version", "case_integrity_check"}
        u1_indexes = {
            "idx_case_bucket", "idx_case_feature_type", "idx_case_obsolete",
            "idx_trace_source", "idx_trace_target", "idx_trace_jira",
            "idx_artefact_hash", "idx_unit_state", "idx_step_case_ord",
        }
        u1_triggers = {
            "trg_case_requires_steps", "trg_case_requires_jira_key",
            "trg_case_id_is_immutable",
        }
        assert u1_entities | u1_machinery <= names("table")
        assert u1_indexes <= names("index")
        assert u1_triggers <= names("trigger")
        assert len(u1_entities) == 18

    def test_every_migration_is_reversible(self, tmp_path):
        # A reverse migration nobody has run is a hypothesis, and OD-02's rollback
        # story depends on it being a fact.
        connection = get_connection(ConnectionSettings(db_path=tmp_path / "rev.db"))
        assert verify_reversibility(connection).ok

    def test_migrate_down_removes_the_schema(self, conn):
        assert migrate_down(conn, 0).ok
        assert current_version(conn) == 0

    def test_unknown_future_version_is_refused(self, conn):
        conn.execute(
            "INSERT INTO schema_version (version, name, applied_at) "
            "VALUES (999, 'from the future', datetime('now'))"
        )
        result = migrate_up(conn)
        assert not result.ok
        assert "does not recognise" in result.message

    def test_statement_splitter_keeps_trigger_bodies_whole(self):
        # executescript() implicitly commits, so statements run individually inside
        # a transaction. A naive split on ";" would tear trigger bodies apart.
        statements = split_statements(m001_initial.UP)
        triggers = [s for s in statements if s.upper().startswith("CREATE TRIGGER")]
        assert len(triggers) == 3
        assert all(s.strip().upper().endswith("END;") for s in triggers)

    def test_migration_is_transactional(self, tmp_path):
        connection = get_connection(ConnectionSettings(db_path=tmp_path / "t.db"))
        migrate_up(connection)
        assert not connection.in_transaction


class TestIntegrityConstraints:
    """The two rules that matter most, enforced at the storage layer as well as in D7."""

    def test_case_without_steps_is_rejected_by_the_database(self, conn, seeded):
        with unit_of_work(conn) as uow:
            # Insert directly, bypassing the domain, to prove the constraint holds
            # even if a future code path skips the validator.
            conn.execute(
                q.CASE_INSERT,
                dict(id="TC-CHECKOUT-00090", feature_id=seeded,
                     coverage_item_id="CI-CHECKOUT-00001", title="t",
                     test_type="boundary", priority="medium", preconditions="",
                     expected_result="ok", automatability="needs-review",
                     automatability_reason="", automatability_overridden_by=None,
                     tags="[]", normalised_hash=None, bucket_key=None,
                     run_id=None, now="2026-01-01", actor="test"),
            )
            conn.execute(q.TRACE_INSERT, dict(
                source_kind="test_case", source_id="TC-CHECKOUT-00090",
                target_ref="PAY-1", link_type="direct-story", evidence="",
                selection_basis=None, alternatives="[]", resolved_jira_key="PAY-1"))
            with pytest.raises(sqlite3.IntegrityError, match="REJECTED_NO_STEPS"):
                conn.execute(q.INTEGRITY_CHECK, {"case_id": "TC-CHECKOUT-00090"})

    def test_case_without_jira_key_is_rejected_by_the_database(self, conn, seeded):
        with pytest.raises(sqlite3.IntegrityError, match="REJECTED_NO_JIRA_KEY"):
            with unit_of_work(conn) as uow:
                uow.cases.upsert_many([build_case(seeded, 91, links=False)], "checkout")

    def test_step_with_blank_expected_is_rejected(self, conn, seeded):
        with unit_of_work(conn) as uow:
            uow.cases.upsert_many([build_case(seeded, 1)], "checkout")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO test_step (case_id, ordinal, action, expected) "
                "VALUES ('TC-CHECKOUT-00001', 2, 'do', '   ')"
            )

    def test_test_data_requires_an_equivalence_class(self, conn, seeded):
        with unit_of_work(conn) as uow:
            uow.cases.upsert_many([build_case(seeded, 1)], "checkout")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO test_data (case_id, field_name, value, equivalence_class) "
                "VALUES ('TC-CHECKOUT-00001', 'qty', '5', '  ')"
            )

    def test_case_identifier_is_immutable(self, conn, seeded):
        with unit_of_work(conn) as uow:
            uow.cases.upsert_many([build_case(seeded, 1)], "checkout")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE test_case SET id = 'TC-CHECKOUT-00777' WHERE id = 'TC-CHECKOUT-00001'"
            )

    def test_derived_link_without_selection_basis_is_rejected(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(q.TRACE_INSERT, dict(
                source_kind="test_case", source_id="TC-X-00001", target_ref="PAY-1",
                link_type="derived-from-commit", evidence="", selection_basis=None,
                alternatives="[]", resolved_jira_key="PAY-1"))

    def test_not_required_coverage_item_must_plan_zero(self, conn, seeded):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO coverage_item (id, requirement_id, test_type, planned_count, "
                "is_required) VALUES ('CI-CHECKOUT-00099', 'TR-CHECKOUT-00001', 'boundary', 5, 0)"
            )

    def test_obsolete_case_requires_a_reason(self, conn, seeded):
        with unit_of_work(conn) as uow:
            uow.cases.upsert_many([build_case(seeded, 1)], "checkout")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE test_case SET is_obsolete = 1 WHERE id = 'TC-CHECKOUT-00001'")


class TestUnitOfWork:
    def test_commits_on_clean_exit(self, conn, seeded):
        with unit_of_work(conn) as uow:
            uow.cases.upsert_many([build_case(seeded, 1)], "checkout")
        assert conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == 1

    def test_rolls_back_on_exception(self, conn, seeded):
        with pytest.raises(RuntimeError):
            with unit_of_work(conn) as uow:
                uow.cases.upsert_many([build_case(seeded, 1)], "checkout")
                raise RuntimeError("something went wrong mid-batch")
        assert conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == 0

    def test_a_failing_case_rolls_back_the_whole_batch(self, conn, seeded):
        # All-or-nothing: partial acceptance would leave the agent reconciling
        # which of a batch landed, across a context boundary.
        with pytest.raises(sqlite3.IntegrityError):
            with unit_of_work(conn) as uow:
                uow.cases.upsert_many(
                    [build_case(seeded, 1), build_case(seeded, 2, links=False)], "checkout"
                )
        assert conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == 0

    def test_nested_unit_of_work_joins_the_outer_transaction(self, conn, seeded):
        with pytest.raises(RuntimeError):
            with unit_of_work(conn) as outer:
                outer.cases.upsert_many([build_case(seeded, 1)], "checkout")
                with unit_of_work(conn) as inner:
                    inner.cases.upsert_many([build_case(seeded, 2)], "checkout")
                raise RuntimeError("outer fails after inner completed")
        # The inner block must not have committed independently.
        assert conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == 0

    def test_leaves_no_open_transaction(self, conn, seeded):
        with unit_of_work(conn) as uow:
            uow.cases.upsert_many([build_case(seeded, 1)], "checkout")
        assert not conn.in_transaction


class TestRepositories:
    def test_round_trips_a_case_with_steps_data_and_links(self, conn, seeded):
        with unit_of_work(conn) as uow:
            uow.cases.upsert_many([build_case(seeded, 1)], "checkout")
        with unit_of_work(conn) as uow:
            record = uow.cases.get("TC-CHECKOUT-00001")
        assert record["title"] == "case 1"
        assert len(record["steps"]) == 1
        assert record["test_data"][0]["equivalence_class"] == "class-1"
        assert record["trace_links"][0]["resolved_jira_key"] == "PAY-12"

    def test_soft_delete_retains_the_row_and_its_reason(self, conn, seeded):
        with unit_of_work(conn) as uow:
            uow.cases.upsert_many([build_case(seeded, 1)], "checkout")
            uow.changes.add.__self__  # repository is reachable
        with unit_of_work(conn) as uow:
            uow.cases.mark_obsolete("TC-CHECKOUT-00001", "requirement deleted", 1)
        row = conn.execute(
            "SELECT is_obsolete, obsolete_reason FROM test_case WHERE id = 'TC-CHECKOUT-00001'"
        ).fetchone()
        assert row["is_obsolete"] == 1
        assert row["obsolete_reason"] == "requirement deleted"

    def test_obsolete_cases_are_excluded_from_the_active_corpus(self, conn, seeded):
        with unit_of_work(conn) as uow:
            uow.cases.upsert_many([build_case(seeded, 1), build_case(seeded, 2)], "checkout")
            uow.cases.mark_obsolete("TC-CHECKOUT-00001", "superseded", 1)
        with unit_of_work(conn) as uow:
            assert uow.cases.count_active() == 1
            assert len(uow.cases.query().items) == 1
            assert len(uow.cases.query(include_obsolete=True).items) == 2

    def test_bucket_candidates_use_the_index(self, conn, seeded):
        plan = conn.execute(
            "EXPLAIN QUERY PLAN " + q.CASE_BUCKET_CANDIDATES, {"bucket_key": "x"}
        ).fetchall()
        detail = " ".join(row["detail"] for row in plan)
        # A timing test can pass on a small corpus while the planner does a full
        # scan, then fail mysteriously at volume. Assert the plan, not the clock.
        assert "idx_case_bucket" in detail, detail

    def test_known_jira_keys_reflects_ingested_artefacts_only(self, conn, seeded):
        with unit_of_work(conn) as uow:
            assert uow.artefacts.known_jira_keys() == frozenset()

    def test_pagination_caps_and_continues(self, conn, seeded):
        with unit_of_work(conn) as uow:
            uow.cases.upsert_many(
                [build_case(seeded, i) for i in range(1, 6)], "checkout"
            )
        with unit_of_work(conn) as uow:
            first = uow.cases.query(limit=2)
            assert len(first.items) == 2 and first.has_more
            second = uow.cases.query(limit=2, cursor=first.next_cursor)
            assert len(second.items) == 2
            assert {r["id"] for r in first.items} & {r["id"] for r in second.items} == set()

    def test_page_size_is_hard_capped(self, conn, seeded):
        with unit_of_work(conn) as uow:
            page = uow.cases.query(limit=10_000)
        assert len(page.items) <= MAX_PAGE_SIZE

    def test_tag_filter(self, conn, seeded):
        with unit_of_work(conn) as uow:
            uow.cases.upsert_many(
                [build_case(seeded, 1, tags=["smoke"]), build_case(seeded, 2, tags=["regression"])],
                "checkout",
            )
        with unit_of_work(conn) as uow:
            assert len(uow.cases.query(tag="smoke").items) == 1

    def test_existing_identifiers_supports_sequence_rebuild(self, conn, seeded):
        with unit_of_work(conn) as uow:
            uow.cases.upsert_many([build_case(seeded, 7)], "checkout")
        with unit_of_work(conn) as uow:
            assert uow.cases.existing_identifiers() == ["TC-CHECKOUT-00007"]


class TestBackupAndExport:
    def test_backup_uses_the_online_api_and_is_readable(self, conn, tmp_path, seeded):
        # A filesystem copy during an in-flight write produces a corrupt copy, and
        # WAL makes that more likely rather than less.
        result = backup_before(conn, "pre-migration", tmp_path / "backups")
        assert result.ok
        copy = sqlite3.connect(str(result.value.path))
        assert copy.execute("SELECT COUNT(*) FROM feature").fetchone()[0] == 1

    def test_prune_retains_the_newest(self, conn, tmp_path):
        for i in range(13):
            backup_before(conn, f"op{i}", tmp_path / "backups")
        assert prune(tmp_path / "backups", keep=10).value == 3
        assert len(list_backups(tmp_path / "backups")) == 10

    def test_export_is_portable_and_complete(self, conn, tmp_path, seeded):
        with unit_of_work(conn) as uow:
            uow.cases.upsert_many([build_case(seeded, 1)], "checkout")
        manifest = export_corpus(conn, tmp_path / "export").value
        assert manifest.tables["test_case"] == 1
        assert manifest.tables["test_step"] == 1
        assert (tmp_path / "export" / "manifest.json").exists()

    def test_restore_recovers_the_corpus(self, conn, tmp_path, seeded):
        with unit_of_work(conn) as uow:
            uow.cases.upsert_many([build_case(seeded, 1)], "checkout")
        backup = backup_before(conn, "before-loss", tmp_path / "backups").value
        with unit_of_work(conn) as uow:
            uow.cases.mark_obsolete("TC-CHECKOUT-00001", "lost", 1)
        assert restore(backup, tmp_path / "restored.db").ok
        restored = sqlite3.connect(str(tmp_path / "restored.db"))
        assert restored.execute(
            "SELECT is_obsolete FROM test_case WHERE id = 'TC-CHECKOUT-00001'"
        ).fetchone()[0] == 0
