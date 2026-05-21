"""Tests for V1.routes.forward_scheduler (Module 10)."""
from __future__ import annotations

from pathlib import Path

import pytest

from V1.config.settings import Settings
from V1.models.schedule import ScheduleResult
from V1.routes import (
    audit,
    backward_feasibility,
    demand_explosion,
    forward_scheduler,
    lot_sizing,
    time_calculation,
)
from V1.utilities.bom_walker import build_graph
from V1.utilities.unit_conversion import normalise


@pytest.fixture(scope="module")
def norm(nulled_input_dir: Path, settings: Settings):
    """Use the nulled fixture so the BD-cascade infeasibility tests fire
    deterministically regardless of live input file state."""
    return normalise(audit.run(nulled_input_dir, settings), settings)


@pytest.fixture(scope="module")
def bom(norm, settings: Settings):
    return build_graph(norm.audit.bom_df, norm.aging_df,
                       norm.audit.itemtype_df, settings)


@pytest.fixture(scope="module")
def lots(norm, bom, settings: Settings):
    return lot_sizing.run(norm, demand_explosion.run(norm, bom, settings), settings)


@pytest.fixture(scope="module")
def demand(norm, bom, settings: Settings):
    return demand_explosion.run(norm, bom, settings)


@pytest.fixture(scope="module")
def feasibility(lots, demand, bom, norm):
    return backward_feasibility.run(lots, demand, bom, norm)


@pytest.fixture(scope="module")
def durations(lots, norm, settings):
    return time_calculation.run(lots, norm, settings)


@pytest.fixture(scope="module")
def schedule(lots, demand, feasibility, durations, bom, norm, settings):
    return forward_scheduler.run(lots, demand, feasibility, durations,
                                  bom, norm, settings)


class TestShape:
    def test_produces_scheduled_lots(self, schedule: ScheduleResult) -> None:
        assert len(schedule.scheduled) > 0

    def test_machine_id_is_string(self, schedule: ScheduleResult) -> None:
        for s in schedule.scheduled:
            assert isinstance(s.machine_id, str)

    def test_end_consistent_with_duration(
        self, schedule: ScheduleResult
    ) -> None:
        """end = start + duration. Zero-qty placeholders are allowed
        start == end (duration 0)."""
        for s in schedule.scheduled:
            assert s.end_min == s.start_min + s.duration_min
            if s.qty > 0:
                assert s.end_min > s.start_min


class TestMachineCapacity:
    def test_no_machine_double_booked(self, schedule: ScheduleResult) -> None:
        from collections import defaultdict
        per_machine = defaultdict(list)
        for s in schedule.scheduled:
            per_machine[s.machine_id].append((s.start_min, s.end_min, s.lot_id))
        for m, runs in per_machine.items():
            runs.sort()
            for i in range(1, len(runs)):
                prev_start, prev_end, prev_id = runs[i - 1]
                cur_start, cur_end, cur_id = runs[i]
                assert cur_start >= prev_end, (
                    f"machine {m}: {prev_id} ends {prev_end} but {cur_id} "
                    f"starts {cur_start}"
                )


class TestAgingObserved:
    def test_consumer_starts_after_producer_min_aging(
        self, schedule: ScheduleResult, norm
    ) -> None:
        """For every committed consumer-producer pair, observe MIN aging."""
        sched_by_id = schedule.by_lot_id()
        # min_aging lookup
        aging_min = {}
        for _, r in norm.aging_df.iterrows():
            if r["min_aging_min"] is not None:
                aging_min[str(r["ItemCode"])] = int(r["min_aging_min"]) \
                    if r["min_aging_min"] == r["min_aging_min"] else 0
        for s in schedule.scheduled:
            for ing, prod_id in s.producer_lot_ids.items():
                prod = sched_by_id[prod_id]
                gap = s.start_min - prod.end_min
                assert gap >= aging_min.get(ing, 0), (
                    f"{s.lot_id} consumer starts too early relative to {prod_id}"
                )


class TestBuildingPinningCascade:
    """In the pilot, BD-12843443-4 has null proc_time (the locked audit HALT).
    That cascades to: BD lots → DURATION infeasible → GT lots → AND_JOIN
    infeasible. The test verifies the cascade is named correctly, NOT that
    GT lots are scheduled (they can't be until the planner supplies the
    Fillering proc_time)."""

    def test_bd_fillering_durations_missing(
        self, schedule: ScheduleResult, settings: Settings
    ) -> None:
        bd_infeas = [i for i in schedule.infeasibilities
                     if i.item_code == "BD-12843443-4"]
        assert len(bd_infeas) > 0
        for i in bd_infeas:
            assert i.binding_constraint == "DURATION"

    def test_gt_and_join_infeasible_due_to_bd(
        self, schedule: ScheduleResult, settings: Settings
    ) -> None:
        gt_infeas = [i for i in schedule.infeasibilities
                     if i.item_code == settings.green_tyre_code]
        assert len(gt_infeas) > 0
        for i in gt_infeas:
            assert i.binding_constraint == "AND_JOIN"
            assert "BD-12843443-4" in i.message


class TestReservationLog:
    def test_created_consumed_pairs(self, schedule: ScheduleResult) -> None:
        """Every 'created' has a matching 'consumed' (V1: at the same minute)."""
        created = {(r.consumer_lot_id, r.producer_lot_id)
                   for r in schedule.reservation_log if r.event_type == "created"}
        consumed = {(r.consumer_lot_id, r.producer_lot_id)
                    for r in schedule.reservation_log if r.event_type == "consumed"}
        assert created == consumed


class TestDeterminism:
    def test_two_runs_byte_identical(
        self, lots, demand, feasibility, durations, bom, norm, settings
    ) -> None:
        a = forward_scheduler.run(lots, demand, feasibility, durations,
                                   bom, norm, settings)
        b = forward_scheduler.run(lots, demand, feasibility, durations,
                                   bom, norm, settings)
        assert [(s.lot_id, s.machine_id, s.start_min, s.end_min) for s in a.scheduled] \
            == [(s.lot_id, s.machine_id, s.start_min, s.end_min) for s in b.scheduled]
