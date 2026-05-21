"""Writes schedule.csv + machine_view.csv (Section 11).

Datetime ↔ minute boundary lives here (L23). Other writers MUST NOT touch
pd.Timestamp arithmetic — they read minute values and call back through
the time_math helpers.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from V1.models.schedule import ScheduleResult
from V1.utilities.time_math import from_minute


def _to_records(result: ScheduleResult, t0: datetime) -> list[dict]:
    rows: list[dict] = []
    for s in result.scheduled:
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
            "start_dt": from_minute(s.start_min, t0).isoformat(sep=" "),
            "end_dt": from_minute(s.end_min, t0).isoformat(sep=" "),
        })
    return rows


def write(result: ScheduleResult, t0: datetime, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = _to_records(result, t0)
    df = pd.DataFrame(rows)
    sched_path = output_dir / "schedule.csv"
    df.to_csv(sched_path, index=False)
    # machine_view.csv: same rows sorted by (machine_id, start_min).
    if len(df) > 0:
        view = df.sort_values(["machine_id", "start_min", "lot_id"], kind="stable")
    else:
        view = df
    view_path = output_dir / "machine_view.csv"
    view.to_csv(view_path, index=False)
    return sched_path, view_path
