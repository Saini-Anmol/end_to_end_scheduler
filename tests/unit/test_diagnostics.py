"""Tests for V1.routes.diagnostics + V1.reports.writer_diagnostics (Module 11)."""
from __future__ import annotations

from pathlib import Path

import pytest

from V1.config.settings import Settings
from V1.models.diagnostics import DiagnosticsResult
from V1.reports import writer_diagnostics
from V1.routes import (
    audit,
    backward_feasibility,
    demand_explosion,
    diagnostics,
    forward_scheduler,
    lot_sizing,
    time_calculation,
)
from V1.utilities.bom_walker import build_graph
from V1.utilities.unit_conversion import normalise


@pytest.fixture(scope="module")
def norm(input_dir: Path, settings: Settings):
    return normalise(audit.run(input_dir, settings), settings)


@pytest.fixture(scope="module")
def bom(norm, settings):
    return build_graph(norm.audit.bom_df, norm.aging_df,
                       norm.audit.itemtype_df, settings)


@pytest.fixture(scope="module")
def demand(norm, bom, settings):
    return demand_explosion.run(norm, bom, settings)


@pytest.fixture(scope="module")
def lots(norm, demand, settings):
    return lot_sizing.run(norm, demand, settings)


@pytest.fixture(scope="module")
def schedule(lots, demand, bom, norm, settings):
    feas = backward_feasibility.run(lots, demand, bom, norm)
    durations = time_calculation.run(lots, norm, settings)
    return forward_scheduler.run(lots, demand, feas, durations, bom, norm, settings)


@pytest.fixture(scope="module")
def diag(schedule, demand, norm, settings) -> DiagnosticsResult:
    return diagnostics.run(schedule, demand, norm, settings)


class TestAgingViolations:
    def test_in_graph_min_aging_violations_only_on_curing_edge(self, diag) -> None:
        """The forward scheduler enforces MIN aging on every in-graph pick.
        The only MIN violations diagnostics may surface are on the synthetic
        Building→Curing edge (where the curing block start is fixed input
        and Building couldn't finish in time)."""
        for v in diag.aging_violations:
            if v.violation_type != "MIN":
                continue
            assert v.consumer_lot_id.startswith("CURING__"), (
                f"unexpected in-graph MIN violation: {v}"
            )

    def test_violation_records_are_consistent(self, diag) -> None:
        for v in diag.aging_violations:
            if v.violation_type == "MIN":
                assert v.actual_gap_min < v.edge_min
            else:
                assert v.actual_gap_min > v.edge_max


class TestBuildingToCuring:
    def test_records_only_for_gt_lots(self, diag, schedule, settings) -> None:
        gt_lots_committed = [s for s in schedule.scheduled
                              if s.item_code == settings.green_tyre_code]
        # The pilot's BD HALT cascade means GT lots may not be committed in V1.
        # Just assert structural consistency: every BTC record corresponds to a
        # committed GT lot.
        lot_ids = {s.lot_id for s in gt_lots_committed}
        for r in diag.building_to_curing:
            assert r.lot_id in lot_ids


class TestWriter:
    def test_writes_three_csvs(self, diag, schedule, tmp_path: Path) -> None:
        paths = writer_diagnostics.write(diag, schedule, tmp_path)
        for name, p in paths.items():
            assert p.exists()

    def test_byte_identical_rerun(self, diag, schedule, tmp_path: Path) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir(); b.mkdir()
        writer_diagnostics.write(diag, schedule, a)
        writer_diagnostics.write(diag, schedule, b)
        for fname in ("aging_violations.csv", "building_to_curing.csv",
                       "infeasibilities.csv"):
            assert (a / fname).read_bytes() == (b / fname).read_bytes()


class TestDeterminism:
    def test_two_runs_identical(self, schedule, demand, norm, settings) -> None:
        a = diagnostics.run(schedule, demand, norm, settings)
        b = diagnostics.run(schedule, demand, norm, settings)
        assert [(v.consumer_lot_id, v.producer_lot_id, v.violation_type)
                for v in a.aging_violations] \
            == [(v.consumer_lot_id, v.producer_lot_id, v.violation_type)
                for v in b.aging_violations]
