"""Writes kpi.csv: headline totals + per-machine utilisation."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from V1.models.kpi import KpiResult


def write(kpi: KpiResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_rows = [
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

    # Per-machine rows: prefix with `machine_util_<id>_*`.
    machine_rows: list[tuple[str, float | int]] = []
    for m in kpi.machines:
        machine_rows.append((f"machine_{m.machine_id}_busy_min", m.busy_min))
        machine_rows.append((f"machine_{m.machine_id}_span_min", m.span_min))
        machine_rows.append((f"machine_{m.machine_id}_util_pct", round(m.utilisation_pct, 3)))

    df = pd.DataFrame(summary_rows + machine_rows, columns=["metric", "value"])
    path = output_dir / "kpi.csv"
    df.to_csv(path, index=False)
    return path
