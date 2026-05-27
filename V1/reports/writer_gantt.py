"""Writes one master Gantt + three piece-wise Gantts of the schedule.

Outputs (Section 11):
  • `gantt_all.html`   — master view: every machine × every lot, full horizon.
  • `gantt_part1.html` — first third of the horizon.
  • `gantt_part2.html` — middle third of the horizon.
  • `gantt_part3.html` — final third of the horizon.

Each piece-wise gantt embeds its date range in the chart title. A lot is
assigned to ONE part by its `start_min` (so it appears exactly once
across the three piece-wise files; the master always has it).

Rows = machines (sorted by `machine_id`). Bars are coloured by `item_type`.
Hover surfaces `lot_id`, `item_code`, qty + uom, duration, `serves_blocks`,
and `on_time_flag` so a planner can read the schedule without
cross-referencing the workbook.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px

from V1.models.demand import DemandResult
from V1.models.schedule import ScheduleResult
from V1.utilities.time_math import from_minute


# Column order locked for determinism (used by both master + piece-wise).
_HOVER_COLS = [
    "lot_id", "item_code", "qty_uom", "duration_min",
    "serves_blocks", "on_time_flag",
]


# Process-flow ordering. Lower rank = closer to the top of the chart
# (y-axis is reversed in Plotly, so the last machine in this order ends up
# visually on top). We want Building rows visually prominent, so building
# machines (6001-7004) get the LARGEST rank, putting them at the top.
_PROCESS_RANK_PREFIX: list[tuple[str, int]] = [
    # rank, machine prefix / exact id — first match wins
    (10, "MS"),               # raw / pre-positioned materials
    (20, "0201"),             # mixing (master)
    (21, "0202"),
    (22, "0203"),
    (23, "0204"),
    (24, "0205"),
    (25, "0206"),
    (40, "FRC"),              # calendering
    (50, "Quintuplex"),       # extruders
    (51, "TRC"),
    (52, "Duplex"),
    (60, "WBC"),              # cutters
    (61, "WBCNew"),
    (62, "FWS"),
    (63, "FWSNew"),
    (64, "HTBC"),
    (65, "LTBC"),
    (66, "LTBCNew"),
    (70, "VIPO"),             # bead chain
    (71, "FILLERING"),
    (90, "6001"),             # Tyre Building (top of chart — most important)
    (91, "6002"),
    (92, "6003"),
    (93, "6004"),
    (94, "7001"),
    (95, "7002"),
    (96, "7003"),
    (97, "7004"),
]


def _machine_rank(machine_id: str) -> tuple[int, str]:
    """Return a (rank, name) sort key putting machines in process-flow order.

    Building machines (6001-7004) get the LARGEST rank so they end up
    visually on TOP of the chart (y-axis reversed). Unknown machines get
    rank 999, sorted alphabetically among themselves.
    """
    for rank, prefix in _PROCESS_RANK_PREFIX:
        if machine_id.startswith(prefix):
            return (rank, machine_id)
    return (999, machine_id)


def _rows(schedule: ScheduleResult, t0: datetime) -> list[dict]:
    return [
        {
            "lot_id": s.lot_id,
            "item_code": s.item_code,
            "item_type": s.item_type,
            "machine_id": s.machine_id,
            "start": from_minute(s.start_min, t0),
            "end": from_minute(s.end_min, t0),
            "start_min": s.start_min,
            "end_min": s.end_min,
            "duration_min": s.duration_min,
            "qty_uom": f"{s.qty:.1f} {s.uom}",
            "serves_blocks": ",".join(s.serves_blocks) if s.serves_blocks else "—",
            "on_time_flag": bool(s.on_time_flag),
        }
        # Skip zero-qty placeholder lots (e.g., the b00 GT lot) — they have
        # duration_min=0 and machine_id="—" so they wouldn't render as bars.
        for s in schedule.scheduled if s.duration_min > 0
    ]


def _render(
    df: pd.DataFrame,
    machine_order: list[str],
    title: str,
    out_path: Path,
) -> Path | None:
    """Render one Plotly Gantt to `out_path`. Returns None if df is empty."""
    if df.empty:
        return None
    height = max(600, 28 * len(machine_order) + 200)
    fig = px.timeline(
        df, x_start="start", x_end="end", y="machine_id",
        color="item_type",
        category_orders={"machine_id": machine_order},
        hover_data=_HOVER_COLS,
        title=title,
    )
    # Force the y-axis category order explicitly. px.timeline's
    # `category_orders` parameter is sometimes re-sorted by Plotly's
    # internal logic; setting `categoryarray` directly on the axis is
    # authoritative. `autorange='reversed'` keeps Building (first item in
    # `machine_order`) at the visual TOP of the chart.
    fig.update_yaxes(
        categoryorder="array",
        categoryarray=machine_order,
        autorange="reversed",
        title="Machine",
    )
    fig.update_xaxes(title="Wall-clock time")
    fig.update_layout(height=height, legend_title="Item type")
    fig.write_html(out_path, include_plotlyjs="cdn")
    return out_path


def _partition_ranges(
    start_min: int, end_min: int,
) -> list[tuple[int, int]]:
    """Split [start_min, end_min] into 3 equal integer-minute parts.

    Boundaries are inclusive on the left, exclusive on the right for the
    first two parts; the third part is inclusive on both ends so the last
    minute is always covered.
    """
    span = max(0, end_min - start_min)
    third = span // 3
    p1_start = start_min
    p1_end = start_min + third
    p2_start = p1_end
    p2_end = start_min + 2 * third
    p3_start = p2_end
    p3_end = end_min
    return [(p1_start, p1_end), (p2_start, p2_end), (p3_start, p3_end)]


def _fmt_range(t0: datetime, lo_min: int, hi_min: int) -> str:
    """Render an inclusive date range like '19 May – 22 May 2026' for titles."""
    lo = from_minute(lo_min, t0)
    hi = from_minute(hi_min, t0)
    if lo.year == hi.year and lo.month == hi.month:
        return f"{lo.day:02d}–{hi.day:02d} {lo.strftime('%b %Y')}"
    if lo.year == hi.year:
        return f"{lo.strftime('%d %b')} – {hi.strftime('%d %b %Y')}"
    return f"{lo.strftime('%d %b %Y')} – {hi.strftime('%d %b %Y')}"


def write(
    schedule: ScheduleResult, demand: DemandResult, t0: datetime,
    output_dir: Path,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if not schedule.scheduled:
        return []

    rows = _rows(schedule, t0)
    df = pd.DataFrame(rows).sort_values(["machine_id", "start", "lot_id"])
    # Process-flow ordering: Building machines (6001-7004) at the TOP of
    # the chart, mixers/raws at the bottom. Plotly's y-axis is reversed
    # (`autorange="reversed"`), so the FIRST item in category_orders is
    # rendered at the top. Sort by rank DESCENDING so high-rank (Building)
    # comes first → ends up at the top of the chart. Drop the "—"
    # placeholder machine (zero-qty placeholder lots have no bar).
    machine_order = sorted(
        [m for m in df["machine_id"].unique() if m != "—"],
        key=_machine_rank,
        reverse=True,
    )

    written: list[Path] = []

    # 1. Master gantt — every lot on every machine.
    master = _render(
        df, machine_order,
        title="Gantt — all machines, all lots (master view)",
        out_path=output_dir / "gantt_all.html",
    )
    if master is not None:
        written.append(master)

    # 2. Piece-wise gantts — split horizon into 3 equal time ranges.
    schedule_lo = int(df["start_min"].min())
    schedule_hi = int(df["end_min"].max())
    parts = _partition_ranges(schedule_lo, schedule_hi)
    for i, (lo, hi) in enumerate(parts, start=1):
        # Assign each lot to the FIRST part whose [lo, hi] contains its
        # start_min — except the third part also picks up anything that
        # spans past schedule_hi.
        if i < len(parts):
            mask = (df["start_min"] >= lo) & (df["start_min"] < hi)
        else:
            mask = df["start_min"] >= lo
        part_df = df[mask].copy()
        title = (
            f"Gantt — Part {i} of 3 — {_fmt_range(t0, lo, hi)} "
            f"({len(part_df)} lots)"
        )
        part_path = _render(
            part_df, machine_order, title,
            out_path=output_dir / f"gantt_part{i}.html",
        )
        if part_path is not None:
            written.append(part_path)

    return written
