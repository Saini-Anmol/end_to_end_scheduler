"""Tests for V1.reports.writer_excel — bundled workbook output."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from V1.config.settings import Settings
from V1.reports import writer_excel
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
def pipeline_results(input_dir: Path, settings: Settings):
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
    kpi = kpi_route.run(sched, diag, lots)
    return au, lots, sched, diag, kpi, norm


class TestWriteFull:
    @pytest.fixture(scope="class")
    def workbook_path(self, pipeline_results, settings: Settings,
                       tmp_path_factory) -> Path:
        au, lots, sched, diag, kpi, norm = pipeline_results
        out = tmp_path_factory.mktemp("out_full")
        return writer_excel.write_full(
            audit=au, lots=lots, schedule=sched, diag=diag, kpi=kpi,
            settings=settings, t0=norm.t0, run_id="TEST",
            output_dir=out,
        )

    def test_workbook_exists(self, workbook_path: Path) -> None:
        assert workbook_path.exists()
        assert workbook_path.name == "btp_schedule.xlsx"

    def test_all_expected_sheets_present(self, workbook_path: Path) -> None:
        xl = pd.ExcelFile(workbook_path)
        for name in writer_excel.SHEET_NAMES:
            assert name in xl.sheet_names, f"missing sheet: {name}"

    def test_sheets_in_documented_tab_order(self, workbook_path: Path) -> None:
        xl = pd.ExcelFile(workbook_path)
        assert tuple(xl.sheet_names) == writer_excel.SHEET_NAMES

    def test_schedule_sheet_has_lot_rows(self, workbook_path: Path) -> None:
        df = writer_excel.read_sheet(workbook_path, "schedule")
        assert len(df) > 0
        assert {"lot_id", "machine_id", "start_min", "end_min", "qty", "uom"} \
            <= set(df.columns)

    def test_kpi_sheet_has_otif(self, workbook_path: Path) -> None:
        df = writer_excel.read_sheet(workbook_path, "kpi")
        assert "otif_pct" in df["metric"].values

    def test_summary_sheet_carries_run_id(self, workbook_path: Path) -> None:
        df = writer_excel.read_sheet(workbook_path, "summary")
        row = df[df["metric"] == "run_id"]
        assert len(row) == 1
        assert str(row.iloc[0]["value"]) == "TEST"

    def test_machine_view_sorted_by_machine_then_start(
        self, workbook_path: Path
    ) -> None:
        df = writer_excel.read_sheet(workbook_path, "machine_view")
        if len(df) == 0:
            pytest.skip("no scheduled lots")
        df_sorted = df.sort_values(["machine_id", "start_min", "lot_id"], kind="stable")
        pd.testing.assert_frame_equal(
            df.reset_index(drop=True), df_sorted.reset_index(drop=True)
        )

    def test_audit_halt_sheet_present_with_columns(
        self, workbook_path: Path
    ) -> None:
        """Sheet always exists; rows present iff the live inputs HALT.
        With BD Fillering proc_time now supplied in input/, this sheet is
        normally empty — we only assert structure."""
        df = writer_excel.read_sheet(workbook_path, "audit_halt")
        expected_cols = {"severity", "code", "sheet", "source_row_pandas",
                          "source_row_excel", "item_code", "message"}
        assert expected_cols <= set(df.columns)

    def test_synthetic_halt_finding_appears_in_workbook(
        self, settings: Settings, pipeline_results, tmp_path: Path
    ) -> None:
        """Construct an AuditResult with a synthetic HALT finding and verify
        write_full surfaces it on the audit_halt sheet, independent of the
        live input file state."""
        from dataclasses import replace
        from V1.config.enums import FindingSeverity
        from V1.models.finding import AuditFinding
        au, lots, sched, diag, kpi, norm = pipeline_results
        synthetic = AuditFinding(
            severity=FindingSeverity.HALT,
            code="AUDIT_NULL_PROC_TIME",
            sheet="Routing",
            source_row=59,
            item_code="BD-12843443-4",
            message="synthetic HALT for test",
        )
        au_with_halt = replace(au, findings=[*au.findings, synthetic])
        path = writer_excel.write_full(
            audit=au_with_halt, lots=lots, schedule=sched, diag=diag,
            kpi=kpi, settings=settings, t0=norm.t0, run_id="SYN-HALT",
            output_dir=tmp_path,
        )
        df = writer_excel.read_sheet(path, "audit_halt")
        assert (df["item_code"] == "BD-12843443-4").any()
        bd = df[df["item_code"] == "BD-12843443-4"].iloc[0]
        assert int(bd["source_row_excel"]) == 61

    def test_infeasibilities_columns(self, workbook_path: Path) -> None:
        df = writer_excel.read_sheet(workbook_path, "infeasibilities")
        expected = {"lot_id", "item_code", "op_seq",
                    "binding_constraint", "message"}
        assert expected <= set(df.columns)


class TestWriteHalt:
    def test_halt_workbook_minimal_sheets(
        self, pipeline_results, settings: Settings, tmp_path: Path
    ) -> None:
        au, _, _, _, _, norm = pipeline_results
        path = writer_excel.write_halt(
            audit=au, settings=settings, t0=norm.t0, run_id="HALT-TEST",
            output_dir=tmp_path,
        )
        assert path.exists()
        xl = pd.ExcelFile(path)
        # Required sheets for HALT runs.
        for name in ("summary", "audit_halt", "audit_warn", "routing_cleaned"):
            assert name in xl.sheet_names

    def test_halt_summary_says_halt(
        self, pipeline_results, settings: Settings, tmp_path: Path
    ) -> None:
        au, _, _, _, _, norm = pipeline_results
        path = writer_excel.write_halt(
            audit=au, settings=settings, t0=norm.t0, run_id="HALT-TEST",
            output_dir=tmp_path,
        )
        df = writer_excel.read_sheet(path, "summary")
        status = df[df["metric"] == "status"].iloc[0]["value"]
        assert status == "HALT"
