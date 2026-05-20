"""Tests for V1.routes.kpi + V1.reports.writer_kpi (Module 12)."""
from __future__ import annotations

from pathlib import Path

import pytest

from V1.config.settings import Settings
from V1.models.kpi import KpiResult
from V1.reports import writer_kpi
from V1.routes import (
    audit,
    backward_feasibility,
    demand_explosion,
    diagnostics,
    forward_scheduler,
    kpi as kpi_route,
    lot_sizing,
    time_calculation,
)
from V1.utilities.bom_walker import build_graph
from V1.utilities.unit_conversion import normalise


@pytest.fixture(scope="module")
def kpi(input_dir: Path, settings: Settings) -> KpiResult:
    au = audit.run(input_dir, settings)
    norm = normalise(au, settings)
    bom = build_graph(norm.audit.bom_df, norm.aging_df,
                      norm.audit.itemtype_df, settings)
    demand = demand_explosion.run(norm, bom, settings)
    lots = lot_sizing.run(norm, demand, settings)
    feas = backward_feasibility.run(lots, demand, bom, norm)
    durs = time_calculation.run(lots, norm, settings)
    sched = forward_scheduler.run(lots, demand, feas, durs, bom, norm, settings)
    diag = diagnostics.run(sched, demand, norm, settings)
    return kpi_route.run(sched, diag, lots)


class TestKpiShape:
    def test_counts_positive(self, kpi: KpiResult) -> None:
        assert kpi.total_lots_scheduled > 0
        assert kpi.total_processing_min > 0
        assert kpi.schedule_span_min > 0

    def test_changeover_zero_v1(self, kpi: KpiResult) -> None:
        """L8 — V1 changeover is 0 always."""
        assert kpi.changeover_min == 0

    def test_otif_in_0_100_range(self, kpi: KpiResult) -> None:
        assert 0.0 <= kpi.otif_pct <= 100.0

    def test_machines_records_for_busy_machines(self, kpi: KpiResult) -> None:
        machine_ids = {m.machine_id for m in kpi.machines}
        assert len(machine_ids) == len(kpi.machines)  # no dup
        for m in kpi.machines:
            assert 0.0 <= m.utilisation_pct <= 100.0
            assert m.busy_min >= 0
            assert m.span_min >= 0


class TestWriter:
    def test_writes_kpi_csv(self, kpi: KpiResult, tmp_path: Path) -> None:
        path = writer_kpi.write(kpi, tmp_path)
        assert path.exists()
        text = path.read_text()
        assert "metric,value" in text
        assert "otif_pct" in text
        assert "changeover_min_v1" in text

    def test_byte_identical_rerun(self, kpi: KpiResult, tmp_path: Path) -> None:
        a = tmp_path / "a"; b = tmp_path / "b"
        a.mkdir(); b.mkdir()
        writer_kpi.write(kpi, a)
        writer_kpi.write(kpi, b)
        assert (a / "kpi.csv").read_bytes() == (b / "kpi.csv").read_bytes()
