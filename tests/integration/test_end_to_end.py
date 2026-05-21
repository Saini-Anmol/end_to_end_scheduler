"""End-to-end integration tests: full pipeline + byte-identical re-run.

Two scenarios — both work off COPIES of `input/` in tmp dirs, so the live
pilot data is never modified by tests:

  1. **HALT path** — copy of inputs with BD-12843443-4 Fillering `proc_time`
     forced to NaN. Audit HALTs at code 10; downstream routes don't run;
     `btp_schedule.xlsx` is still written but with the HALT-only layout
     (summary + audit findings + routing_cleaned sheet).

  2. **Full-pipeline path** — copy of inputs with `proc_time` ensured set
     (60 SEC/BATCH if absent). All 13 pipeline steps run; the planner-facing
     artefacts (`btp_schedule.xlsx`, `audit_report.md`, `dag.json`,
     `bom_graph.svg`, `gantt_*.html`) land in the run folder.

     Determinism (L11 / Section 12.2) is asserted on:
       - `dag.json` — byte-identical (JSON is fully stable).
       - `btp_schedule.xlsx` — sheet-by-sheet dataframe equality (the
         workbook bytes include an openpyxl-embedded build timestamp, but
         every cell value is reproducible).
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from V1.config.halt_codes import HaltCode
from V1.config.settings import Settings, load_settings
from V1.setups import bootstrap


HALT_RUN_TS = datetime(2099, 1, 1, 12, 30)
FULL_RUN_TS_A = datetime(2099, 1, 1, 12, 31)
FULL_RUN_TS_B = datetime(2099, 1, 1, 12, 32)


def _copy_inputs(src_dir: Path, dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    for f in src_dir.iterdir():
        shutil.copy2(f, dst_dir / f.name)


def _patch_bd_proc_time(dst_dir: Path, proc_time_sec: float | None) -> None:
    """Set BD-12843443-4 Fillering `proc_time` (or null it) in a *copy* of
    the routing xlsx. `proc_time_sec=None` → force NaN to trigger HALT.
    """
    xlsx_path = next(dst_dir.glob("BTP_Routing_*.xlsx"))
    sheet_name = "Routing - 1325220516095HTMX0"
    df_all = pd.read_excel(xlsx_path, sheet_name=None)
    df = df_all[sheet_name]
    mask = (df["routed_product"] == "BD-12843443-4") & (df["operation_seq"] == 60)
    assert mask.any(), "BD Fillering row not found"
    if proc_time_sec is None:
        df.loc[mask, "proc_time"] = float("nan")
        df.loc[mask, "proc_time_UOM"] = float("nan")
        df.loc[mask, "batch_size"] = float("nan")
        df.loc[mask, "batch_UNIT"] = float("nan")
    else:
        df.loc[mask, "proc_time"] = float(proc_time_sec)
        df.loc[mask, "proc_time_UOM"] = "SEC/BATCH"
        df.loc[mask, "batch_size"] = 100.0
        df.loc[mask, "batch_UNIT"] = "NOS"
    df_all[sheet_name] = df
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as w:
        for sheet, sub in df_all.items():
            sub.to_excel(w, sheet_name=sheet, index=False)


class TestHaltPath:
    def test_audit_halts_when_bd_proc_time_nulled(
        self, project_root: Path, tmp_path: Path, tmp_path_factory
    ) -> None:
        nulled_inputs = tmp_path_factory.mktemp("nulled_inputs")
        _copy_inputs(project_root / "input", nulled_inputs)
        _patch_bd_proc_time(nulled_inputs, proc_time_sec=None)
        out = tmp_path / "output"
        settings = load_settings()
        code = bootstrap.run(
            settings=settings,
            input_dir=nulled_inputs,
            output_root=out,
            now=HALT_RUN_TS,
        )
        assert code == int(HaltCode.AUDIT_NULL_PROC_TIME) == 10
        runs = list(out.iterdir())
        assert len(runs) == 1
        run_dir = runs[0]
        # Audit artefacts + the HALT-only workbook are present.
        assert (run_dir / "audit_report.md").exists()
        assert (run_dir / "btp_schedule.xlsx").exists()
        # No standalone CSVs (or downstream artefacts) on HALT.
        for downstream in ("routing_cleaned.csv", "schedule.csv",
                            "machine_view.csv", "kpi.csv", "dag.json",
                            "aging_violations.csv", "reservation_log.csv",
                            "building_to_curing.csv", "infeasibilities.csv",
                            "bom_graph.svg"):
            assert not (run_dir / downstream).exists()


class TestFullPath:
    @pytest.fixture(scope="class")
    def patched_inputs(self, project_root: Path, tmp_path_factory) -> Path:
        src = project_root / "input"
        dst = tmp_path_factory.mktemp("patched_inputs")
        _copy_inputs(src, dst)
        _patch_bd_proc_time(dst, proc_time_sec=60.0)
        return dst

    @pytest.fixture(scope="class")
    def two_runs(self, patched_inputs: Path, tmp_path_factory) -> tuple[Path, Path]:
        out_a = tmp_path_factory.mktemp("out_a")
        out_b = tmp_path_factory.mktemp("out_b")
        settings = load_settings()
        code_a = bootstrap.run(
            settings=settings, input_dir=patched_inputs,
            output_root=out_a, now=FULL_RUN_TS_A,
        )
        code_b = bootstrap.run(
            settings=settings, input_dir=patched_inputs,
            output_root=out_b, now=FULL_RUN_TS_B,
        )
        assert code_a == int(HaltCode.OK), f"run A halted with code {code_a}"
        assert code_b == int(HaltCode.OK), f"run B halted with code {code_b}"
        a_dir = next(out_a.iterdir())
        b_dir = next(out_b.iterdir())
        return a_dir, b_dir

    def test_every_planner_artefact_emitted(self, two_runs) -> None:
        a_dir, _ = two_runs
        expected = {
            "audit_report.md",
            "dag.json",
            "bom_graph.svg",
            "btp_schedule.xlsx",
        }
        for name in expected:
            assert (a_dir / name).exists(), f"missing artefact: {name}"
        # At least one gantt_*.html
        assert any(a_dir.glob("gantt_*.html"))
        # Redundant CSVs that used to be emitted alongside the workbook must
        # NOT reappear — they're all sheets inside btp_schedule.xlsx.
        for legacy in ("routing_cleaned.csv", "schedule.csv",
                        "machine_view.csv", "kpi.csv", "aging_violations.csv",
                        "reservation_log.csv", "building_to_curing.csv",
                        "infeasibilities.csv"):
            assert not (a_dir / legacy).exists(), f"legacy CSV re-appeared: {legacy}"

    def test_bundled_excel_carries_every_sheet(self, two_runs) -> None:
        from V1.reports import writer_excel
        a_dir, _ = two_runs
        wb = pd.ExcelFile(a_dir / "btp_schedule.xlsx")
        assert set(writer_excel.SHEET_NAMES) <= set(wb.sheet_names)

    def test_dag_json_byte_identical(self, two_runs) -> None:
        """L11 / Section 12.2 — JSON is byte-stable, so dag.json must match."""
        a_dir, b_dir = two_runs
        assert (a_dir / "dag.json").read_bytes() == (b_dir / "dag.json").read_bytes()

    def test_excel_sheet_values_identical(self, two_runs) -> None:
        """L11 / Section 12.2 — every data sheet's dataframe must be equal
        across re-runs. The workbook *bytes* aren't stable (openpyxl embeds
        a build timestamp), but every cell value is reproducible.

        The `summary` sheet is excluded because it includes the per-run
        `run_id` (the wall-clock minute when the run started) — which
        legitimately differs across runs by design.
        """
        from V1.reports import writer_excel
        a_dir, b_dir = two_runs
        a_path = a_dir / "btp_schedule.xlsx"
        b_path = b_dir / "btp_schedule.xlsx"
        for sheet in writer_excel.SHEET_NAMES:
            if sheet == "summary":
                continue  # carries run_id metadata; legitimately varies
            a_df = writer_excel.read_sheet(a_path, sheet)
            b_df = writer_excel.read_sheet(b_path, sheet)
            assert a_df.equals(b_df), f"sheet {sheet!r} differs across runs"

    def test_gt_lots_scheduled_in_full_path(self, two_runs) -> None:
        """With BD Fillering proc_time provided, GT lots schedule normally."""
        from V1.reports import writer_excel
        a_dir, _ = two_runs
        sched = writer_excel.read_sheet(a_dir / "btp_schedule.xlsx", "schedule")
        gt_rows = sched[sched["item_code"] == "GT2056516TAXIMXTL"]
        assert len(gt_rows) > 0

    def test_no_machine_double_booking(self, two_runs) -> None:
        from V1.reports import writer_excel
        a_dir, _ = two_runs
        sched = writer_excel.read_sheet(a_dir / "btp_schedule.xlsx", "schedule")
        for m, grp in sched.groupby("machine_id"):
            grp = grp.sort_values("start_min")
            ends = grp["end_min"].values
            starts = grp["start_min"].values[1:]
            assert all(s >= e for s, e in zip(starts, ends[:-1])), (
                f"double-booking on machine {m}"
            )

    def test_kpi_otif_reported(self, two_runs) -> None:
        from V1.reports import writer_excel
        a_dir, _ = two_runs
        kpi = writer_excel.read_sheet(a_dir / "btp_schedule.xlsx", "kpi")
        otif_row = kpi[kpi["metric"] == "otif_pct"]
        assert len(otif_row) == 1
        otif_val = float(otif_row.iloc[0]["value"])
        assert 0.0 <= otif_val <= 100.0
