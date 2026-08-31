"""The 9 U7 properties from business-logic-model.md section 5.

Two of them assert what the system must NEVER do. A constraint on forbidden
behaviour is better guarded by a property over all generated inputs than by the
handful of examples someone thought of - C-12 and U7-NFR-REL-02 are exactly that
kind of constraint.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tto_testgen.domain.gates import (
    ROLE_RESTRICTED,
    STAGE_ORDER,
    GateFailure,
    PriorRecord,
    Role,
    evaluate,
    is_role_permitted,
    next_stage,
    prior_stage,
    stage_index,
)
from tto_testgen.domain.model import StageName, UnitState
from tto_testgen.services.runstate import (
    FORBIDDEN_STATUS_FIELDS,
    LeaseClassification,
    RunStateService,
)

SETTINGS = settings(max_examples=200, deadline=None,
                    suppress_health_check=[HealthCheck.too_slow])

stages = st.sampled_from(list(STAGE_ORDER))
states = st.sampled_from(list(UnitState))
roles = st.sampled_from(list(Role))
hashes = st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)
unit_refs = st.text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=1, max_size=20)

prior_records = st.builds(
    PriorRecord,
    state=states,
    approved_by=st.one_of(st.none(), st.text(min_size=1, max_size=12)),
    approved_at=st.one_of(st.none(), st.just("2026-08-29T12:00:00")),
    approved_content_hash=st.one_of(st.none(), hashes),
)


class TestStageOrderingProperties:
    @SETTINGS
    @given(stage=stages)
    def test_property_1_prior_and_next_round_trip(self, stage):
        """PBT-02. prior_stage(next_stage(s)) == s for every non-terminal stage."""
        following = next_stage(stage)
        if following is not None:
            assert prior_stage(following) is stage

    @SETTINGS
    @given(stage=stages)
    def test_property_2_exactly_one_prior_except_the_first(self, stage):
        if stage is STAGE_ORDER[0]:
            assert prior_stage(stage) is None
        else:
            assert prior_stage(stage) is STAGE_ORDER[stage_index(stage) - 1]


class TestGateProperties:
    @SETTINGS
    @given(unit=unit_refs, stage=stages, prior=prior_records, current=st.one_of(st.none(), hashes))
    def test_property_3_open_only_when_all_conditions_hold(self, unit, stage, prior, current):
        """PBT-03. The gate opens only when every condition is satisfied."""
        result = evaluate(unit, stage, prior, current)
        if prior_stage(stage) is None:
            assert result.is_open
            return
        completed = prior.state is UnitState.COMPLETED
        approved = prior.approved_by is not None
        unchanged = (
            prior.approved_content_hash is None
            or current is None
            or prior.approved_content_hash == current
        )
        assert result.is_open == (completed and approved and unchanged)

    @SETTINGS
    @given(unit=unit_refs, stage=stages, prior=prior_records, current=st.one_of(st.none(), hashes))
    def test_property_4_closed_gate_names_exactly_one_condition(self, unit, stage, prior, current):
        result = evaluate(unit, stage, prior, current)
        if result.is_open:
            assert result.failed_condition is None
        else:
            assert result.failed_condition in set(GateFailure)
            assert result.detail and result.remediation

    @SETTINGS
    @given(stage=stages, role=roles)
    def test_property_5_only_coverage_restricts_a_role(self, stage, role):
        permitted = is_role_permitted(stage, role)
        if stage in ROLE_RESTRICTED:
            assert permitted == (role is ROLE_RESTRICTED[stage])
        else:
            assert permitted

    @SETTINGS
    @given(unit=unit_refs, stage=stages, prior=prior_records, current=st.one_of(st.none(), hashes))
    def test_property_6_evaluation_is_deterministic(self, unit, stage, prior, current):
        assert evaluate(unit, stage, prior, current) == evaluate(unit, stage, prior, current)


class TestLeaseProperties:
    @staticmethod
    def _service(minutes_elapsed: int):
        base = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
        return RunStateService(
            lambda: None, clock=lambda: base + timedelta(minutes=minutes_elapsed)
        )

    @SETTINGS
    @given(elapsed=st.integers(min_value=0, max_value=5000))
    def test_property_7_age_is_monotonic_in_elapsed_time(self, elapsed):
        record = {
            "metrics": '{"leased_at": "2026-08-29T12:00:00+00:00"}',
            "state": "in-progress",
        }

        class Row(dict):
            def keys(self):  # sqlite3.Row interface
                return super().keys()

        status = self._service(elapsed).classify_lease(Row(record))
        assert status.age_minutes == elapsed

    @SETTINGS
    @given(elapsed=st.integers(min_value=0, max_value=5000))
    def test_property_8_classification_never_instructs_clearing(self, elapsed):
        """U7-NFR-REL-02. No generated input yields a clearing instruction.

        Clearing a lock another process still holds is how databases get corrupted,
        and this code cannot tell a dead session from a slow one.
        """
        class Row(dict):
            def keys(self):
                return super().keys()

        status = self._service(elapsed).classify_lease(
            Row({"metrics": '{"leased_at": "2026-08-29T12:00:00+00:00"}', "state": "in-progress"})
        )
        assert status.classification in {
            LeaseClassification.ACTIVE,
            LeaseClassification.STALE,
            LeaseClassification.ORPHANED_LOCK,
        }
        forbidden = ("cleared", "released", "reclaimed", "expired automatically")
        assert not any(word in status.guidance.lower() for word in forbidden)


class TestStatusNeutrality:
    @SETTINGS
    @given(
        rows=st.lists(
            st.tuples(unit_refs, stages, states),
            min_size=0,
            max_size=25,
        )
    )
    def test_property_9_status_is_neutral_and_stably_ordered(self, rows):
        """C-12. No proposal field, and ordering that carries no signal.

        Asserted as a property because C-12 is a constraint on what must never
        appear, and no finite set of examples establishes that.
        """
        composed = [
            {
                "unit_ref": unit,
                "stage": stage.value,
                "state": state.value,
                "gate_open": False,
                "lease_status": None,
                "metrics": {},
            }
            for unit, stage, state in rows
        ]
        composed.sort(key=lambda r: (r["unit_ref"], stage_index(StageName(r["stage"]))))

        for row in composed:
            assert FORBIDDEN_STATUS_FIELDS.isdisjoint(row)

        keys = [(r["unit_ref"], stage_index(StageName(r["stage"]))) for r in composed]
        assert keys == sorted(keys)
