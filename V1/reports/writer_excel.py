"""Writes the bundled `btp_schedule.xlsx` — a single workbook with one sheet
per tabular artefact.

Sheets (in tab order):
  - summary           — run-level metadata + headline KPIs
  - kpi               — full KPI table (metric / value)
  - schedule          — lot-level schedule
  - machine_view      — schedule sorted by (machine_id, start_min)
  - building_to_curing
  - aging_violations
  - infeasibilities
  - reservation_log
  - routing_cleaned
  - audit_halt        — HALT findings only
  - audit_warn        — WARN findings only

CSV, JSON, SVG and HTML outputs continue to be written alongside this
workbook (Excel can't carry the dag graph or the Gantt HTML). The workbook
is the headline artefact the planner opens; the individual files remain for
downstream tooling and byte-identical re-run verification.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from V1.config.enums import FindingSeverity
from V1.config.settings import Settings
from V1.models.kpi import KpiResult
from V1.models.lot import LotsResult
from V1.models.schedule import ScheduleResult
from V1.models.diagnostics import DiagnosticsResult
from V1.routes.audit import AuditResult
from V1.utilities.time_math import from_minute


WORKBOOK_NAME = "btp_schedule.xlsx"


# Excel sheet names are capped at 31 chars; pick short, stable names.
SHEET_NAMES = (
    "summary",
    "kpi",
    "schedule",
    "machine_view",
    "building_to_curing",
    "aging_violations",
    "infeasibilities",
    "reservation_log",
    "routing_cleaned",
    "audit_halt",
    "audit_warn",
)


# --- builders for each sheet ----------------------------------------------

def _summary_df(
    audit: AuditResult, lots: LotsResult, schedule: ScheduleResult,
    diag: DiagnosticsResult, kpi: KpiResult, settings: Settings,
    t0: datetime, run_id: str,
) -> pd.DataFrame:
    rows: list[tuple[str, object]] = [
        ("run_id", run_id),
        ("t0", t0.isoformat(sep=" ")),
        ("sku_code", settings.sku_code),
        ("sku_description", settings.sku_description),
        ("green_tyre_code", settings.green_tyre_code),
        ("curing_press", settings.curing_press),
        ("horizon_start", settings.horizon_start.isoformat(sep=" ")),
        ("horizon_end", settings.horizon_end.isoformat(sep=" ")),
        ("total_demand_tyres", settings.total_demand_tyres),
        ("audit_halt_findings", len(audit.halt_findings)),
        ("audit_warn_findings", len(audit.warn_findings)),
        ("lots_sized", len(lots.lots)),
        ("lot_sizing_warnings", len(lots.warnings)),
        ("lots_scheduled", len(schedule.scheduled)),
        ("lots_infeasible", len(schedule.infeasibilities)),
        ("aging_violations", len(diag.aging_violations)),
        ("building_to_curing_ok", kpi.building_lots_ok),
        ("building_to_curing_late", kpi.building_lots_late),
        ("building_to_curing_early", kpi.building_lots_early),
        ("otif_pct", round(kpi.otif_pct, 3)),
        ("total_processing_min", kpi.total_processing_min),
        ("schedule_span_min", kpi.schedule_span_min),
        ("changeover_min_v1", kpi.changeover_min),
    ]
    return pd.DataFrame(rows, columns=["metric", "value"])


def _kpi_df(kpi: KpiResult) -> pd.DataFrame:
    rows: list[tuple[str, object]] = [
        ("total_lots_scheduled", kpi.total_lots_scheduled),
        ("total_lots_infeasible", kpi.total_lots_infeasible),
        ("total_lot_sizing_warnings", kpi.total_warnings),
        ("building_lots_ok", kpi.building_lots_ok),
        ("building_lots_late", kpi.building_lots_late),
        ("building_lots_early", kpi.building_lots_early),
        ("otif_pct", round(kpi.otif_pct, 3)),
        ("aging_violations_total", kpi.aging_violations_total),
        ("aging_violations_min_breaches", kpi.aging_violations_min),
        ("aging_violations_max_breaches", kpi.aging_violations_max),
        ("total_processing_min", kpi.total_processing_min),
        ("changeover_min_v1", kpi.changeover_min),
        ("schedule_span_min", kpi.schedule_span_min),
    ]
    for m in kpi.machines:
        rows.append((f"machine_{m.machine_id}_busy_min", m.busy_min))
        rows.append((f"machine_{m.machine_id}_span_min", m.span_min))
        rows.append((f"machine_{m.machine_id}_util_pct", round(m.utilisation_pct, 3)))
    return pd.DataFrame(rows, columns=["metric", "value"])


def _schedule_df(schedule: ScheduleResult, t0: datetime) -> pd.DataFrame:
    rows = []
    for s in schedule.scheduled:
        rows.append({
            "lot_id": s.lot_id,
            "item_code": s.item_code,
            "item_type": s.item_type,
            "op_seq": s.op_seq,
            "machine_id": s.machine_id,
            "start_min": s.start_min,
            "end_min": s.end_min,
            "duration_min": s.duration_min,
            "qty": s.qty,
            "uom": s.uom,
            "serves_blocks": "|".join(s.serves_blocks),
            "on_time_flag": s.on_time_flag,
            "start_dt": from_minute(s.start_min, t0),
            "end_dt": from_minute(s.end_min, t0),
        })
    cols = ["lot_id", "item_code", "item_type", "op_seq", "machine_id",
            "start_min", "end_min", "duration_min", "qty", "uom",
            "serves_blocks", "on_time_flag", "start_dt", "end_dt"]
    return pd.DataFrame(rows, columns=cols)


def _machine_view_df(schedule_df: pd.DataFrame) -> pd.DataFrame:
    if schedule_df.empty:
        return schedule_df.copy()
    return schedule_df.sort_values(
        ["machine_id", "start_min", "lot_id"], kind="stable"
    ).reset_index(drop=True)


def _btc_df(diag: DiagnosticsResult) -> pd.DataFrame:
    rows = [
        {
            "lot_id": r.lot_id, "machine_id": r.machine_id,
            "block_id": r.block_id,
            "gt_end_min": r.gt_end_min,
            "curing_start_min": r.curing_start_min,
            "gap_min": r.gap_min,
            "min_aging_min": r.min_aging_min,
            "max_aging_min": r.max_aging_min,
            "classification": r.classification,
        }
        for r in diag.building_to_curing
    ]
    cols = ["lot_id", "machine_id", "block_id", "gt_end_min",
            "curing_start_min", "gap_min", "min_aging_min", "max_aging_min",
            "classification"]
    return pd.DataFrame(rows, columns=cols)


def _aging_violations_df(diag: DiagnosticsResult) -> pd.DataFrame:
    rows = [
        {
            "consumer_lot": v.consumer_lot_id,
            "predecessor_lot": v.producer_lot_id,
            "item_code": v.item_code,
            "edge_min": v.edge_min,
            "edge_max": v.edge_max,
            "actual_gap": v.actual_gap_min,
            "violation_type": v.violation_type,
        }
        for v in diag.aging_violations
    ]
    cols = ["consumer_lot", "predecessor_lot", "item_code", "edge_min",
            "edge_max", "actual_gap", "violation_type"]
    return pd.DataFrame(rows, columns=cols)


def _infeasibilities_df(schedule: ScheduleResult) -> pd.DataFrame:
    rows = [
        {
            "lot_id": i.lot_id, "item_code": i.item_code,
            "op_seq": i.op_seq,
            "binding_constraint": i.binding_constraint,
            "message": i.message,
        }
        for i in schedule.infeasibilities
    ]
    cols = ["lot_id", "item_code", "op_seq", "binding_constraint", "message"]
    return pd.DataFrame(rows, columns=cols)


def _reservation_log_df(schedule: ScheduleResult) -> pd.DataFrame:
    rows = [
        {
            "event_minute": e.event_minute,
            "event_type": e.event_type,
            "consumer_lot_id": e.consumer_lot_id,
            "producer_lot_id": e.producer_lot_id,
            "item_code": e.item_code,
            "qty": e.qty,
            "producer_end_min": e.producer_end_min,
            "latest_acceptable_start_min": e.latest_acceptable_start_min,
        }
        for e in schedule.reservation_log
    ]
    cols = ["event_minute", "event_type", "consumer_lot_id",
            "producer_lot_id", "item_code", "qty", "producer_end_min",
            "latest_acceptable_start_min"]
    return pd.DataFrame(rows, columns=cols)


def _routing_cleaned_df(audit: AuditResult) -> pd.DataFrame:
    # Drop the in-memory list column for CSV/Excel friendliness.
    return audit.routing_cleaned_df.drop(columns=["machines_list"], errors="ignore")


def _findings_df(audit: AuditResult, severity: FindingSeverity) -> pd.DataFrame:
    findings = [f for f in audit.findings if f.severity == severity]
    rows = []
    for f in findings:
        rows.append({
            "severity": f.severity.value,
            "code": f.code,
            "sheet": f.sheet or "",
            "source_row_pandas": f.source_row if f.source_row is not None else "",
            "source_row_excel": f.excel_row() if f.excel_row() is not None else "",
            "item_code": f.item_code or "",
            "message": f.message,
        })
    cols = ["severity", "code", "sheet", "source_row_pandas",
            "source_row_excel", "item_code", "message"]
    return pd.DataFrame(rows, columns=cols)


# --- public entry ---------------------------------------------------------

def write_full(
    audit: AuditResult,
    lots: LotsResult,
    schedule: ScheduleResult,
    diag: DiagnosticsResult,
    kpi: KpiResult,
    settings: Settings,
    t0: datetime,
    run_id: str,
    output_dir: Path,
) -> Path:
    """Build and write the full bundled workbook. Returns its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sched_df = _schedule_df(schedule, t0)
    sheets: dict[str, pd.DataFrame] = {
        "summary": _summary_df(audit, lots, schedule, diag, kpi,
                               settings, t0, run_id),
        "kpi": _kpi_df(kpi),
        "schedule": sched_df,
        "machine_view": _machine_view_df(sched_df),
        "building_to_curing": _btc_df(diag),
        "aging_violations": _aging_violations_df(diag),
        "infeasibilities": _infeasibilities_df(schedule),
        "reservation_log": _reservation_log_df(schedule),
        "routing_cleaned": _routing_cleaned_df(audit),
        "audit_halt": _findings_df(audit, FindingSeverity.HALT),
        "audit_warn": _findings_df(audit, FindingSeverity.WARN),
    }
    return _write_workbook(sheets, output_dir)


def write_halt(
    audit: AuditResult,
    settings: Settings,
    t0: datetime,
    run_id: str,
    output_dir: Path,
) -> Path:
    """Write a HALT-only workbook (audit ran, downstream did not).

    Contains just the summary, routing_cleaned, and the two audit-findings
    sheets so the planner can diagnose without leaving Excel.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_rows = [
        ("run_id", run_id),
        ("t0", t0.isoformat(sep=" ")),
        ("sku_code", settings.sku_code),
        ("status", "HALT"),
        ("audit_halt_findings", len(audit.halt_findings)),
        ("audit_warn_findings", len(audit.warn_findings)),
        ("schedule_emitted", "NO — audit HALT blocked downstream"),
    ]
    sheets: dict[str, pd.DataFrame] = {
        "summary": pd.DataFrame(summary_rows, columns=["metric", "value"]),
        "audit_halt": _findings_df(audit, FindingSeverity.HALT),
        "audit_warn": _findings_df(audit, FindingSeverity.WARN),
        "routing_cleaned": _routing_cleaned_df(audit),
    }
    return _write_workbook(sheets, output_dir)


def _write_workbook(sheets: dict[str, pd.DataFrame], output_dir: Path) -> Path:
    path = output_dir / WORKBOOK_NAME
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
            ws = writer.sheets[name]
            ws.freeze_panes = "A2"
            # Width heuristic: header length + 2, capped at 60.
            for col_idx, col in enumerate(df.columns, start=1):
                width = min(60, max(12, len(str(col)) + 2))
                ws.column_dimensions[
                    ws.cell(row=1, column=col_idx).column_letter
                ].width = width
    return path
