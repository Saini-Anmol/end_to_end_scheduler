"""Route 8 — diagnostics (Section 10 #8, approach-flow step 25).

Walks the committed schedule, recomputes every consumer-producer gap, flags
breaches of `[MIN_aging, MAX_aging]` (inclusive both ends per L22). Two
classes of aging-edge checks:

  1. **In-graph** edges: for each ScheduledLot, for each ingredient picked
     from `producer_lot_ids`, compare gap = consumer.start − producer.end
     against the producer item's aging window.

  2. **Building → Curing** edge: for each Building (GT) lot, for each
     served curing block, compare gap = curing.start − GT.end against the
     Green Tyre's aging window. This is the most consequential edge in V1
     because it determines OTIF.

`building_to_curing` records one row per (GT lot, served block) with the
classification OK / LATE / EARLY / ZERO_QTY.
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


# Synthetic "consumer" lot_id used for Building→Curing aging-violation rows.
# Curing isn't a scheduled lot in V1 (fixed input), but we still want the
# violation to appear in aging_violations.csv with a clear identifier.
def _curing_consumer_id(block_id: str) -> str:
    return f"CURING__{block_id}"


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

    # block_id → curing_start — covers all 42 rows including zero-qty b00.
    block_curing_start: dict[str, int] = {
        d.block_id: d.curing_start_min for d in demand.block_demands
    }
    for idx, row in norm.curing_df.reset_index(drop=True).iterrows():
        bid = f"b{int(idx):02d}"
        block_curing_start.setdefault(bid, int(row["start_min"]))

    violations: list[AgingViolation] = []

    # 1. In-graph consumer-producer pairs. A consumer may draw from multiple
    #    producer lots per ingredient (MPQ-split); each pair is checked
    #    independently against the ingredient's aging window.
    for s in schedule.scheduled:
        if s.qty == 0:
            continue  # zero-qty placeholder — no real consumption
        for ing_item, producer_ids in s.producer_lot_ids.items():
            for producer_id in producer_ids:
                producer = sched_by_id.get(producer_id)
                if producer is None or producer.qty == 0:
                    continue
                mn, mx = aging.get(ing_item, (0, 10 ** 9))
                gap = s.start_min - producer.end_min
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

    # 2. Building → Curing edge.
    gt_min, gt_max = aging.get(settings.green_tyre_code, (0, 10 ** 9))
    building_records: list[BuildingToCuringRecord] = []
    for s in schedule.scheduled:
        if s.item_code != settings.green_tyre_code:
            continue
        # L1 — per-block grain: one Building lot per curing row.
        for block_id in s.serves_blocks:
            cur_start = block_curing_start.get(block_id)
            if cur_start is None:
                continue
            gap = cur_start - s.end_min
            if s.qty == 0:
                cls = "ZERO_QTY"
            elif gap < gt_min:
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
            # Mirror LATE / EARLY into aging_violations.csv so every breach
            # of an aging window shows up in one place.
            if cls in ("LATE", "EARLY"):
                violations.append(AgingViolation(
                    consumer_lot_id=_curing_consumer_id(block_id),
                    producer_lot_id=s.lot_id,
                    item_code=settings.green_tyre_code,
                    edge_min=gt_min, edge_max=gt_max,
                    actual_gap_min=gap,
                    violation_type=("MIN" if cls == "LATE" else "MAX"),
                ))

    violations.sort(key=lambda v: (v.consumer_lot_id, v.producer_lot_id))
    building_records.sort(key=lambda r: (r.block_id, r.lot_id))

    return DiagnosticsResult(
        aging_violations=violations,
        building_to_curing=building_records,
    )
