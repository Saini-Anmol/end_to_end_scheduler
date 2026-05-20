"""Writes gantt_<block_id>.html for sample curing blocks (Section 11).

For each chosen sample block, builds a Plotly Gantt timeline showing every
scheduled lot whose `serves_blocks` includes that block. Bars are stacked by
machine_id; colour-coded by item_type. Hover text shows lot_id + qty + uom.

V1 selects three samples deterministically: the EARLIEST, MIDDLE, and LATEST
demand blocks in chronological order.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px

from V1.models.demand import DemandResult
from V1.models.schedule import ScheduleResult
from V1.utilities.time_math import from_minute


def _sample_blocks(demand: DemandResult) -> list[str]:
    block_ids = sorted(
        {d.block_id for d in demand.block_demands},
        key=lambda b: int(b[1:]),
    )
    if not block_ids:
        return []
    if len(block_ids) <= 3:
        return block_ids
    return [block_ids[0], block_ids[len(block_ids) // 2], block_ids[-1]]


def write(
    schedule: ScheduleResult, demand: DemandResult, t0: datetime,
    output_dir: Path,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for block_id in _sample_blocks(demand):
        rows = []
        for s in schedule.scheduled:
            if block_id not in s.serves_blocks:
                continue
            rows.append({
                "lot_id": s.lot_id,
                "item_code": s.item_code,
                "item_type": s.item_type,
                "machine_id": s.machine_id,
                "start": from_minute(s.start_min, t0),
                "end": from_minute(s.end_min, t0),
                "qty_uom": f"{s.qty:.1f} {s.uom}",
            })
        if not rows:
            continue
        df = pd.DataFrame(rows).sort_values(["machine_id", "start"])
        fig = px.timeline(
            df, x_start="start", x_end="end", y="machine_id",
            color="item_type",
            hover_data=["lot_id", "item_code", "qty_uom"],
            title=f"Gantt — block {block_id}",
        )
        fig.update_yaxes(autorange="reversed")
        path = output_dir / f"gantt_{block_id}.html"
        fig.write_html(path, include_plotlyjs="cdn")
        written.append(path)
    return written
