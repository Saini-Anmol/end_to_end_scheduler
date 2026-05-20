"""Writes aging_violations.csv, building_to_curing.csv, infeasibilities.csv."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from V1.models.diagnostics import DiagnosticsResult
from V1.models.schedule import ScheduleResult


def write(
    diag: DiagnosticsResult, schedule: ScheduleResult, output_dir: Path
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    av_rows = [
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
    av_path = output_dir / "aging_violations.csv"
    pd.DataFrame(av_rows, columns=[
        "consumer_lot", "predecessor_lot", "item_code",
        "edge_min", "edge_max", "actual_gap", "violation_type",
    ]).to_csv(av_path, index=False)

    btc_rows = [
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
    btc_path = output_dir / "building_to_curing.csv"
    pd.DataFrame(btc_rows, columns=[
        "lot_id", "machine_id", "block_id", "gt_end_min", "curing_start_min",
        "gap_min", "min_aging_min", "max_aging_min", "classification",
    ]).to_csv(btc_path, index=False)

    inf_rows = [
        {
            "lot_id": i.lot_id, "item_code": i.item_code,
            "op_seq": i.op_seq,
            "binding_constraint": i.binding_constraint,
            "message": i.message,
        }
        for i in schedule.infeasibilities
    ]
    inf_path = output_dir / "infeasibilities.csv"
    pd.DataFrame(inf_rows, columns=[
        "lot_id", "item_code", "op_seq", "binding_constraint", "message",
    ]).to_csv(inf_path, index=False)

    return {
        "aging_violations": av_path,
        "building_to_curing": btc_path,
        "infeasibilities": inf_path,
    }
