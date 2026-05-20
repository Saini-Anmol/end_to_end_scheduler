"""Route 8 — diagnostics (Section 10 #8, approach-flow step 25).

Walks the committed schedule, recomputes every consumer-producer gap, flags
breaches of `[MIN_aging, MAX_aging]` (inclusive both ends per L22) into the
aging-violations table. Classifies every Building (GT) lot's hand-off into
its served curing block as OK / LATE / EARLY.
"""
from __future__ import annotations

import pandas as pd

from V1.config.settings import Settings
from V1.models.demand import DemandResult
from V1.models.diagnostics import (
    AgingViolation,
    BuildingToCuringRecord,
    DiagnosticsResult,
)
from V1.models.schedule import ScheduleResult
from V1.utilities.unit_conversion import NormalisedResult


def _aging_lookup(aging_df: pd.DataFrame) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for _, row in aging_df.iterrows():
        if pd.notna(row.get("min_aging_min")) and pd.notna(row.get("max_aging_min")):
            out[str(row["ItemCode"])] = (
                int(row["min_aging_min"]), int(row["max_aging_min"])
            )
    return out


def run(
    schedule: ScheduleResult,
    demand: DemandResult,
    norm: NormalisedResult,
    settings: Settings,
) -> DiagnosticsResult:
    sched_by_id = schedule.by_lot_id()
    aging = _aging_lookup(norm.aging_df)
    block_curing_start = {
        d.block_id: d.curing_start_min for d in demand.block_demands
    }

    violations: list[AgingViolation] = []
    for s in schedule.scheduled:
        for ing_item, producer_id in s.producer_lot_ids.items():
            producer = sched_by_id.get(producer_id)
            if producer is None:
                continue
            mn, mx = aging.get(ing_item, (0, 10 ** 9))
            gap = s.start_min - producer.end_min
            # Inclusive bounds (L22).
            if gap < mn:
                violations.append(AgingViolation(
                    consumer_lot_id=s.lot_id, producer_lot_id=producer_id,
                    item_code=ing_item, edge_min=mn, edge_max=mx,
                    actual_gap_min=gap, violation_type="MIN",
                ))
            elif gap > mx:
                violations.append(AgingViolation(
                    consumer_lot_id=s.lot_id, producer_lot_id=producer_id,
                    item_code=ing_item, edge_min=mn, edge_max=mx,
                    actual_gap_min=gap, violation_type="MAX",
                ))
    violations.sort(key=lambda v: (v.consumer_lot_id, v.producer_lot_id))

    # Building → Curing classification
    building_records: list[BuildingToCuringRecord] = []
    gt_min, gt_max = aging.get(settings.green_tyre_code, (0, 10 ** 9))
    for s in schedule.scheduled:
        if s.item_code != settings.green_tyre_code:
            continue
        # L1 — per-block grain: one Building lot per curing row.
        for block_id in s.serves_blocks:
            cur_start = block_curing_start.get(block_id)
            if cur_start is None:
                continue
            gap = cur_start - s.end_min
            if gap < gt_min:
                cls = "LATE"
            elif gap > gt_max:
                cls = "EARLY"
            else:
                cls = "OK"
            building_records.append(BuildingToCuringRecord(
                lot_id=s.lot_id, machine_id=s.machine_id, block_id=block_id,
                gt_end_min=s.end_min, curing_start_min=cur_start,
                gap_min=gap, min_aging_min=gt_min, max_aging_min=gt_max,
                classification=cls,
            ))
    building_records.sort(key=lambda r: (r.block_id, r.lot_id))

    return DiagnosticsResult(
        aging_violations=violations,
        building_to_curing=building_records,
    )
