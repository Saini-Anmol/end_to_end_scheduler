"""Writes reservation_log.csv per Section 16 schema."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from V1.models.schedule import ScheduleResult


_COLUMNS = [
    "event_minute", "event_type", "consumer_lot_id", "producer_lot_id",
    "item_code", "qty", "producer_end_min", "latest_acceptable_start_min",
]


def write(result: ScheduleResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        {col: getattr(e, col) for col in _COLUMNS}
        for e in result.reservation_log
    ]
    df = pd.DataFrame(rows, columns=_COLUMNS)
    path = output_dir / "reservation_log.csv"
    df.to_csv(path, index=False)
    return path
