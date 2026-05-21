"""Writes the bundled `btp_schedule.xlsx` — a single workbook with one sheet
per tabular artefact, formatted for planner consumption.

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

Each sheet carries:
  - Row 1: merged title bar (navy fill, white bold text).
  - Row 2: column headers (banded blue fill, white bold).
  - Row 3+: data, with cell-level conditional fills for utilisation %,
            on_time_flag, classification, violation_type, and severity.
  - Frozen panes below row 2 so title + header stay visible while scrolling.

Use `writer_excel.read_sheet(path, sheet_name)` to read a sheet back as a
DataFrame — it handles the title-row offset (`header=1`) so callers don't
need to know about the layout.

CSV, JSON, SVG and HTML outputs (`dag.json`, `bom_graph.svg`, `gantt_*.html`,
`audit_report.md`) continue to be written alongside this workbook for
downstream tooling. The workbook is the headline artefact the planner opens.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from V1.config.enums import FindingSeverity
from V1.config.settings import Settings
from V1.models.kpi import KpiResult
from V1.models.lot import LotsResult
from V1.models.schedule import ScheduleResult
from V1.models.diagnostics import DiagnosticsResult
from V1.routes.audit import AuditResult
from V1.utilities.time_math import from_minute


WORKBOOK_NAME = "btp_schedule.xlsx"

# Layout: title in Excel row 1, header in row 2, data from row 3.
TITLE_ROW = 1
HEADER_ROW = 2
DATA_START_ROW = 3
# pandas `header=` arg to use when reading these workbooks back.
PD_READ_HEADER = HEADER_ROW - 1  # 0-indexed → 1


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


# Human-readable titles rendered in each sheet's row 1.
_SHEET_TITLES: dict[str, str] = {
    "summary": "Run Summary",
    "kpi": "Key Performance Indicators",
    "schedule": "Production Schedule",
    "machine_view": "Machine-Level Schedule",
    "building_to_curing": "Building → Curing Handoff",
    "aging_violations": "Aging Window Violations",
    "infeasibilities": "Infeasible Lots",
    "reservation_log": "Reservation Log",
    "routing_cleaned": "Cleaned Routing",
    "audit_halt": "Audit — HALT Findings",
    "audit_warn": "Audit — Warnings",
}


# Colour palette (Excel-standard "Good/Neutral/Bad" tones + navy title bar).
_C_TITLE_BG = "1F4E78"
_C_TITLE_FG = "FFFFFF"
_C_HEADER_BG = "305496"
_C_HEADER_FG = "FFFFFF"
_C_GREEN_BG = "C6EFCE"
_C_YELLOW_BG = "FFEB9C"
_C_RED_BG = "FFC7CE"
_C_GRAY_BG = "D9D9D9"


def _fill(hex_rgb: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_rgb)


# Utilisation % conditional bands (planner-supplied thresholds).
#   >= 90       → green   (high utilisation)
#   50  – <90   → yellow  (medium utilisation)
#   <  50       → red     (low utilisation)
def _utilisation_fill(pct: float) -> PatternFill | None:
    if pct >= 90.0:
        return _fill(_C_GREEN_BG)
    if pct >= 50.0:
        return _fill(_C_YELLOW_BG)
    return _fill(_C_RED_BG)


_CLASSIFICATION_FILL: dict[str, str] = {
    "OK": _C_GREEN_BG,
    "LATE": _C_RED_BG,
    "EARLY": _C_YELLOW_BG,
    "ZERO_QTY": _C_GRAY_BG,
}

_SEVERITY_FILL: dict[str, str] = {
    "HALT": _C_RED_BG,
    "WARN": _C_YELLOW_BG,
}


def read_sheet(workbook_path: Path, sheet_name: str) -> pd.DataFrame:
    """Read a sheet back as a DataFrame, accounting for the row-1 title bar.

    All downstream code (tests, planner notebooks, downstream tooling)
    should use this helper rather than `pd.read_excel` directly, so the
    title-row offset is encapsulated.
    """
    return pd.read_excel(workbook_path, sheet_name=sheet_name,
                          header=PD_READ_HEADER)


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
    # `startrow=HEADER_ROW - 1` lays the pandas-emitted header on Excel
    # row 2; row 1 is left empty for the merged title bar.
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False,
                         startrow=HEADER_ROW - 1)
            ws = writer.sheets[name]
            _format_sheet(ws, df, name)
    return path


def _format_sheet(ws, df: pd.DataFrame, sheet_name: str) -> None:
    """Apply title bar, header banding, frozen panes, column widths, and
    per-sheet categorical fills. Pure presentation — no data mutation."""
    n_cols = max(1, len(df.columns))
    n_rows = len(df)

    # --- Row 1: merged title bar ------------------------------------------
    title = _SHEET_TITLES.get(
        sheet_name, sheet_name.replace("_", " ").title()
    )
    ws.cell(row=TITLE_ROW, column=1, value=title)
    if n_cols > 1:
        ws.merge_cells(
            start_row=TITLE_ROW, end_row=TITLE_ROW,
            start_column=1, end_column=n_cols,
        )
    title_cell = ws.cell(row=TITLE_ROW, column=1)
    title_cell.font = Font(size=14, bold=True, color=_C_TITLE_FG)
    title_cell.fill = _fill(_C_TITLE_BG)
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[TITLE_ROW].height = 28

    # --- Row 2: column headers --------------------------------------------
    header_font = Font(bold=True, color=_C_HEADER_FG)
    header_fill = _fill(_C_HEADER_BG)
    header_align = Alignment(horizontal="left", vertical="center")
    for col_idx in range(1, n_cols + 1):
        cell = ws.cell(row=HEADER_ROW, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
    ws.row_dimensions[HEADER_ROW].height = 22

    # Freeze title + header so they stay visible while scrolling data.
    ws.freeze_panes = ws.cell(row=DATA_START_ROW, column=1)

    # --- Per-sheet categorical fills (data rows) --------------------------
    if sheet_name == "kpi" and n_rows > 0:
        _shade_kpi_utilisation(ws, df)
    elif sheet_name in ("schedule", "machine_view") and n_rows > 0:
        _shade_on_time_flag(ws, df)
    elif sheet_name == "building_to_curing" and n_rows > 0:
        _shade_classification(ws, df)
    elif sheet_name == "aging_violations" and n_rows > 0:
        _shade_violation_type(ws, df)
    elif sheet_name in ("audit_halt", "audit_warn") and n_rows > 0:
        _shade_severity(ws, df)

    # --- Column widths (header text length + 2, capped at 60) -------------
    for col_idx, col in enumerate(df.columns, start=1):
        width = min(60, max(12, len(str(col)) + 2))
        ws.column_dimensions[get_column_letter(col_idx)].width = width


def _data_range(n_rows: int) -> range:
    """Excel row indices (1-based) for the data block."""
    return range(DATA_START_ROW, DATA_START_ROW + n_rows)


def _col_index(df: pd.DataFrame, col_name: str) -> int | None:
    """1-based column index of `col_name` in df, or None if absent."""
    if col_name not in df.columns:
        return None
    return list(df.columns).index(col_name) + 1


def _shade_kpi_utilisation(ws, df: pd.DataFrame) -> None:
    """Colour every utilisation-% cell in the kpi sheet.

    The kpi sheet is a (metric, value) long-table; we scan for rows whose
    metric name ends in `_util_pct` and shade the value cell.
    """
    metric_col = _col_index(df, "metric")
    value_col = _col_index(df, "value")
    if metric_col is None or value_col is None:
        return
    for row_idx, df_row_idx in zip(_data_range(len(df)), df.index):
        metric = str(df.at[df_row_idx, "metric"])
        if not metric.endswith("_util_pct"):
            continue
        raw = df.at[df_row_idx, "value"]
        try:
            pct = float(raw)
        except (TypeError, ValueError):
            continue
        fill = _utilisation_fill(pct)
        if fill is not None:
            ws.cell(row=row_idx, column=value_col).fill = fill


def _shade_on_time_flag(ws, df: pd.DataFrame) -> None:
    col = _col_index(df, "on_time_flag")
    if col is None:
        return
    for row_idx, df_row_idx in zip(_data_range(len(df)), df.index):
        val = df.at[df_row_idx, "on_time_flag"]
        if val is True or str(val).strip().lower() == "true":
            ws.cell(row=row_idx, column=col).fill = _fill(_C_GREEN_BG)
        elif val is False or str(val).strip().lower() == "false":
            ws.cell(row=row_idx, column=col).fill = _fill(_C_RED_BG)


def _shade_classification(ws, df: pd.DataFrame) -> None:
    col = _col_index(df, "classification")
    if col is None:
        return
    for row_idx, df_row_idx in zip(_data_range(len(df)), df.index):
        cls = str(df.at[df_row_idx, "classification"])
        rgb = _CLASSIFICATION_FILL.get(cls)
        if rgb is not None:
            ws.cell(row=row_idx, column=col).fill = _fill(rgb)


def _shade_violation_type(ws, df: pd.DataFrame) -> None:
    """Any aging-window violation is bad — colour the type cell red."""
    col = _col_index(df, "violation_type")
    if col is None:
        return
    for row_idx, df_row_idx in zip(_data_range(len(df)), df.index):
        val = df.at[df_row_idx, "violation_type"]
        if isinstance(val, str) and val:
            ws.cell(row=row_idx, column=col).fill = _fill(_C_RED_BG)


def _shade_severity(ws, df: pd.DataFrame) -> None:
    col = _col_index(df, "severity")
    if col is None:
        return
    for row_idx, df_row_idx in zip(_data_range(len(df)), df.index):
        sev = str(df.at[df_row_idx, "severity"])
        rgb = _SEVERITY_FILL.get(sev)
        if rgb is not None:
            ws.cell(row=row_idx, column=col).fill = _fill(rgb)
