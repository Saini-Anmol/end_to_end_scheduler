"""Route 7 — forward_scheduler (Section 10 #7, approach-flow steps 17-24).

V1 V1 V1 V1 simplification: topological greedy forward sweep. Lots are
processed in BOM topological order (raws → masters → components → GT), and
within each item in chronological + lot_id order. For each lot:

  1. For each BOM-child ingredient, find a FEFO-eligible committed producer
     lot that shares at least one served block with the consumer.
  2. `earliest_lot_start = max(producer.end + max(transfer, MIN_aging))`
     across picked producers.
  3. Pick a machine: among eligible, smallest (machine_free_from, machine_id).
  4. `actual_start = max(earliest_lot_start, machine_free_from)`.
  5. `actual_end = actual_start + duration`.
  6. Feasibility: actual_end ≤ feasibility.latest_acceptable_end_min.
  7. If feasible: commit, append reservation 'created'+'consumed' log entries.
     Else: append InfeasibilityRecord (L11 — flag and continue).

Building (GT) lots enforce atomic AND-join (Section 4.2): if any one of the
8 in-scope components has no eligible producer, the lot is infeasible and
no reservations are committed for it.

Determinism: every iteration order is explicitly sorted. Tiebreaks per L19
(FEFO `expiry, lot_id`) and per machine selection (`free_from, machine_id`).

Not yet implemented (deferred from V1):
  - Strict event-heap dispatch (L21) — we use topo+greedy instead.
  - Full LSF tiebreak chain (L15) — sequential dispatch avoids the tie.
  - Soft-reservation expiry (L16) — sequential dispatch avoids contention.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import bisect

import networkx as nx
import pandas as pd

from V1.config.settings import Settings
from V1.models.demand import DemandResult
from V1.models.feasibility import FeasibilityResult
from V1.models.lot import LotsResult
from V1.models.schedule import (
    InfeasibilityRecord,
    ReservationLogEntry,
    ScheduledLot,
    ScheduleResult,
)
from V1.routes.time_calculation import DurationResult
from V1.utilities.bom_walker import BomGraph
from V1.utilities.fefo import FefoCandidate, fefo_pick
from V1.utilities.machine_parser import build_eligibility_index
from V1.utilities.unit_conversion import NormalisedResult


def _block_chrono_index(bid: str) -> int:
    return int(bid[1:])


def _aging_min_for(item: str, aging_df: pd.DataFrame) -> int:
    rows = aging_df[aging_df["ItemCode"].astype(str) == item]
    if len(rows) == 0:
        return 0
    v = rows.iloc[0]["min_aging_min"]
    return int(v) if pd.notna(v) else 0


def _aging_max_for(item: str, aging_df: pd.DataFrame) -> int:
    rows = aging_df[aging_df["ItemCode"].astype(str) == item]
    if len(rows) == 0:
        # Effectively no upper bound (raws / work-away).
        return 10 ** 9
    v = rows.iloc[0]["max_aging_min"]
    return int(v) if pd.notna(v) else 10 ** 9


def _transfer_min_for(item: str, routing_df: pd.DataFrame, default: int) -> int:
    rows = routing_df[routing_df["routed_product"] == item]
    if len(rows) == 0:
        return default
    v = rows.iloc[0].get("transfer_time_min")
    return int(v) if pd.notna(v) else default


def _is_building_lot(lot, settings: Settings) -> bool:
    return lot.item_code == settings.green_tyre_code


def _find_earliest_slot(
    intervals: list[tuple[int, int]], duration: int, lower_bound: int,
) -> int:
    """Find the earliest start time ≥ `lower_bound` where a lot of `duration`
    minutes fits between existing intervals on the machine.

    `intervals` is sorted by start ascending and is non-overlapping. Walks
    gaps left-to-right; returns the first start that satisfies the bound
    and avoids overlap. If no gap fits, returns the time after the last
    committed lot.
    """
    cursor = lower_bound
    for s, e in intervals:
        if e <= cursor:
            continue  # interval entirely in the past
        if s >= cursor + duration:
            return cursor
        cursor = max(cursor, e)
    return cursor


def _insert_interval(
    intervals: list[tuple[int, int]], start: int, end: int,
) -> None:
    """Insert (start, end) into sorted intervals list."""
    bisect.insort(intervals, (start, end))


def _aging_min_lookup(aging_df: pd.DataFrame) -> dict[str, int]:
    out: dict[str, int] = {}
    for _, row in aging_df.iterrows():
        if pd.notna(row.get("min_aging_min")):
            out[str(row["ItemCode"])] = int(row["min_aging_min"])
    return out


def _aging_max_lookup(aging_df: pd.DataFrame) -> dict[str, int]:
    out: dict[str, int] = {}
    for _, row in aging_df.iterrows():
        if pd.notna(row.get("max_aging_min")):
            out[str(row["ItemCode"])] = int(row["max_aging_min"])
    return out


def _compute_target_ends(
    lots_by_item: dict[str, list],
    durations,
    bom: BomGraph,
    norm: NormalisedResult,
    settings: Settings,
    block_curing_start: dict[str, int],
) -> tuple[dict[str, int], dict[str, int]]:
    """Compute per-lot target_end_ceiling and target_end_floor.

    For each producer lot feeding consumer lot(s):
      - ceiling: end ≤ MIN(consumer.target_start − own_item.min_aging)
                 (aging-MIN must hold for every consumer)
      - floor:   end ≥ MAX(consumer.target_start − own_item.max_aging)
                 (aging-MAX — producer must NOT have expired by then)

    GT lots are tied to a specific curing block:
      ceiling = curing_start − GT.min_aging
      floor   = curing_start − GT.max_aging

    Walks items PARENTS-FIRST (consumers first in our edge convention) so
    each producer's consumers already have target_ends set when it's visited.

    Returns (ceilings, floors). Forward dispatch uses `floor − duration` as
    the target_start (earliest viable start that satisfies aging-MAX), and
    checks the final `actual_end ≤ ceiling` for on_time_flag.
    """
    ceilings: dict[str, int] = {}
    floors: dict[str, int] = {}
    aging_min_by_item = _aging_min_lookup(norm.aging_df)
    aging_max_by_item = _aging_max_lookup(norm.aging_df)
    gt_min_aging = aging_min_by_item.get(settings.green_tyre_code, 0)
    gt_max_aging = aging_max_by_item.get(settings.green_tyre_code, 10 ** 9)
    gt = settings.green_tyre_code

    item_order = list(reversed(bom.topological_order(exclude_capstrip=True)))
    if gt in lots_by_item and gt not in item_order:
        item_order.insert(0, gt)

    def _lot_duration(lot_id: str) -> int:
        d = durations.for_lot(lot_id)
        if not d:
            return 0
        return next(iter(d.values()))

    for item in item_order:
        if item == settings.sku_code or item not in lots_by_item:
            continue
        for lot in lots_by_item[item]:
            if item == gt:
                block_id = lot.serves_blocks[0] if lot.serves_blocks else None
                if block_id is None:
                    continue
                cur_start = block_curing_start.get(block_id)
                if cur_start is None:
                    continue
                ceilings[lot.lot_id] = int(cur_start - gt_min_aging)
                floors[lot.lot_id] = int(cur_start - gt_max_aging)
                continue

            this_min_aging = aging_min_by_item.get(item, 0)
            this_max_aging = aging_max_by_item.get(item, 10 ** 9)
            ceiling_candidates: list[int] = []
            floor_candidates: list[int] = []
            for parent_item in bom.parents(item, exclude_capstrip=True):
                for parent_lot in lots_by_item.get(parent_item, []):
                    p_te = ceilings.get(parent_lot.lot_id)
                    if p_te is None:
                        continue
                    if set(parent_lot.serves_blocks).isdisjoint(lot.serves_blocks):
                        continue
                    p_dur = _lot_duration(parent_lot.lot_id)
                    p_ts = p_te - p_dur
                    ceiling_candidates.append(p_ts - this_min_aging)
                    floor_candidates.append(p_ts - this_max_aging)
            if ceiling_candidates:
                ceilings[lot.lot_id] = min(ceiling_candidates)
                floors[lot.lot_id] = max(floor_candidates)
    return ceilings, floors


def run(
    lots: LotsResult,
    demand: DemandResult,
    feasibility: FeasibilityResult,
    durations: DurationResult,
    bom: BomGraph,
    norm: NormalisedResult,
    settings: Settings,
) -> ScheduleResult:
    """Greedy topological forward sweep."""
    # Lookups
    feasibility_by_lot = feasibility.by_lot_id()
    eligibility_idx = build_eligibility_index(norm.routing_df)

    # Index lots by item, sorted chronologically + lot_id
    lots_by_item: dict[str, list] = {}
    for lot in lots.lots:
        lots_by_item.setdefault(lot.item_code, []).append(lot)
    for item in lots_by_item:
        lots_by_item[item].sort(
            key=lambda l: (_block_chrono_index(l.earliest_block_id), l.lot_id)
        )

    # Item processing order: topological children-first.
    item_order = bom.topological_order(exclude_capstrip=True)
    # Filter to items that have lots in this run.
    item_order = [it for it in item_order if it in lots_by_item]
    # GT may not appear in demand if it was added externally by lot_sizing.
    # Append GT explicitly at the end so it's processed after all components.
    if settings.green_tyre_code in lots_by_item and settings.green_tyre_code not in item_order:
        item_order.append(settings.green_tyre_code)

    # block_id → curing_start_min — built from BOTH demand and curing_df so
    # zero-qty placeholder blocks (b00) are also addressable.
    block_curing_start: dict[str, int] = {
        d.block_id: d.curing_start_min for d in demand.block_demands
    }
    for idx, row in norm.curing_df.reset_index(drop=True).iterrows():
        bid = f"b{int(idx):02d}"
        block_curing_start.setdefault(bid, int(row["start_min"]))

    # Per-machine committed intervals — gap-aware so later-dispatched lots
    # with earlier target_starts can back-fill gaps left by earlier ones.
    machine_intervals: dict[str, list[tuple[int, int]]] = {}
    for ms in eligibility_idx.values():
        for m in ms:
            machine_intervals.setdefault(m, [])

    # Pre-compute target ceilings + floors per lot via CPM backward pass.
    # Ceiling = latest end honouring aging-MIN of every consumer.
    # Floor   = earliest end honouring aging-MAX of every consumer.
    target_ceilings, target_floors = _compute_target_ends(
        lots_by_item, durations, bom, norm, settings, block_curing_start
    )

    # Committed lot info: lot_id → ScheduledLot
    committed: dict[str, ScheduledLot] = {}

    scheduled: list[ScheduledLot] = []
    infeasibilities: list[InfeasibilityRecord] = []
    reservation_log: list[ReservationLogEntry] = []

    # FEFO candidates per item — appended as lots are committed.
    fefo_candidates: dict[str, list[FefoCandidate]] = {}

    for item in item_order:
        for lot in lots_by_item[item]:
            # Zero-qty placeholder GT lots (b00 — pre-shift slot with 0 tyres)
            # are tracked for traceability per L1 but produce nothing. Place
            # them at curing_start_min with duration 0; no producer matching.
            if lot.qty == 0:
                bid = lot.serves_blocks[0] if lot.serves_blocks else None
                cstart = block_curing_start.get(bid, 0) if bid else 0
                # Placeholder lots consume no machine time → mark with "—" so
                # they don't appear to collide with real lots on the
                # configured Building primary.
                placeholder = ScheduledLot(
                    lot_id=lot.lot_id, item_code=lot.item_code,
                    item_type=lot.item_type, op_seq=lot.op_seq,
                    machine_id="—",
                    start_min=cstart, end_min=cstart, duration_min=0,
                    qty=0.0, uom=lot.uom,
                    serves_blocks=list(lot.serves_blocks),
                    on_time_flag=True,
                )
                scheduled.append(placeholder)
                committed[lot.lot_id] = placeholder
                continue

            # 1. Find producer for each BOM-child ingredient
            ingredients = bom.children(item, exclude_capstrip=True)
            producer_picks: dict[str, ScheduledLot] = {}
            earliest_start = 0
            blocking_reason: str | None = None
            for ing in ingredients:
                # Raws / work-away: no producer needed (available at t0).
                if ing not in fefo_candidates or not fefo_candidates[ing]:
                    if ing not in lots_by_item:
                        continue  # truly a raw / work-away
                    # Has lots in plan but none scheduled yet → no producer.
                    blocking_reason = (
                        f"AND_JOIN: ingredient {ing!r} has no committed producer"
                    )
                    break

                # Filter candidates by block overlap with consumer.
                consumer_blocks = set(lot.serves_blocks)
                overlapping = [
                    c for c in fefo_candidates[ing]
                    if not set(committed[c.lot_id].serves_blocks).isdisjoint(consumer_blocks)
                ]
                if not overlapping:
                    blocking_reason = (
                        f"BLOCK_OVERLAP: ingredient {ing!r} — no committed "
                        f"producer overlaps consumer's serves_blocks"
                    )
                    break

                # FEFO at the consumer's "earliest possible start" so far.
                # Iterate: pick first eligible at current earliest_start; if
                # that pick pushes earliest_start further, re-check eligibility
                # (rare in practice — one iteration suffices for V1).
                candidate_min = max(
                    earliest_start,
                    min(c.end_min + max(c.min_aging_min,
                                        _transfer_min_for(ing, norm.routing_df,
                                                          settings.default_transfer_min))
                        for c in overlapping)
                )
                picked = fefo_pick(overlapping, at_min=candidate_min)
                if picked is None:
                    blocking_reason = (
                        f"AGING: ingredient {ing!r} — no producer is in-window"
                        f" for consumer earliest_start={candidate_min}"
                    )
                    break

                producer_picks[ing] = committed[picked.lot_id]
                transfer = _transfer_min_for(ing, norm.routing_df,
                                              settings.default_transfer_min)
                this_min_gap = max(picked.min_aging_min, transfer)
                earliest_start = max(
                    earliest_start, picked.end_min + this_min_gap
                )

            # AND-join check for Building (GT) lots: every in-scope component
            # must have a producer.
            if _is_building_lot(lot, settings):
                if blocking_reason is None:
                    missing = [
                        c for c in settings.green_tyre_components
                        if c not in producer_picks
                    ]
                    if missing:
                        blocking_reason = (
                            f"AND_JOIN: Building lot missing producers for "
                            f"{missing}"
                        )

            if blocking_reason is not None:
                infeasibilities.append(InfeasibilityRecord(
                    lot_id=lot.lot_id,
                    item_code=lot.item_code,
                    op_seq=lot.op_seq,
                    binding_constraint=blocking_reason.split(":", 1)[0],
                    message=blocking_reason,
                ))
                continue

            # 2. Pick machine
            machines = eligibility_idx.get((item, lot.op_seq), [])
            if not machines:
                infeasibilities.append(InfeasibilityRecord(
                    lot_id=lot.lot_id, item_code=item, op_seq=lot.op_seq,
                    binding_constraint="MACHINE",
                    message=f"No eligible machines for ({item}, op_seq={lot.op_seq})"
                ))
                continue

            # For Building lots (L18), prefer the configured primary `6001`.
            if _is_building_lot(lot, settings):
                preferred = settings.building_primary
                if preferred in machines:
                    ordered_machines = [preferred] + [m for m in sorted(machines)
                                                       if m != preferred]
                else:
                    ordered_machines = sorted(machines)
            else:
                ordered_machines = sorted(machines)

            # Placement window: [floor, ceiling] from the CPM backward pass.
            # We delay each lot until its FLOOR (earliest aging-MAX-safe start)
            # so it doesn't run too early and age out before its consumers.
            # The ceiling is the on-time deadline (aging-MIN); breaches set
            # on_time_flag=False per L11 but still commit.
            feas = feasibility_by_lot.get(lot.lot_id)
            ceiling = target_ceilings.get(lot.lot_id)
            if ceiling is None and feas is not None:
                ceiling = feas.latest_acceptable_end_min
            floor = target_floors.get(lot.lot_id, 0)
            best: tuple[str, int, int, int] | None = None
            duration_map = durations.for_lot(lot.lot_id)
            for m in ordered_machines:
                if m not in duration_map:
                    continue
                duration = duration_map[m]
                if duration == 0:
                    actual_start = max(earliest_start, floor)
                else:
                    lower_bound = earliest_start
                    if floor > 0:
                        lower_bound = max(lower_bound, floor - duration)
                    actual_start = _find_earliest_slot(
                        machine_intervals[m], duration, lower_bound
                    )
                actual_end = actual_start + duration
                if best is None or (actual_end, m) < (best[3], best[0]):
                    best = (m, actual_start, duration, actual_end)
            if best is None:
                infeasibilities.append(InfeasibilityRecord(
                    lot_id=lot.lot_id, item_code=item, op_seq=lot.op_seq,
                    binding_constraint="DURATION",
                    message=f"No durations computed for {lot.lot_id} on eligible machines"
                ))
                continue
            machine_id, actual_start, duration, actual_end = best

            # 3. On-time check vs ceiling (aging-MIN deadline). Per L11 —
            # flag and continue: commit the lot but set on_time_flag=False
            # so the planner sees the breach in schedule.csv + diagnostics.
            on_time = True
            if ceiling is not None and actual_end > ceiling:
                on_time = False

            # 4. Commit.
            sched = ScheduledLot(
                lot_id=lot.lot_id, item_code=item, item_type=lot.item_type,
                op_seq=lot.op_seq, machine_id=machine_id,
                start_min=actual_start, end_min=actual_end,
                duration_min=duration, qty=lot.qty, uom=lot.uom,
                serves_blocks=list(lot.serves_blocks),
                on_time_flag=on_time,
                producer_lot_ids={ing: p.lot_id for ing, p in producer_picks.items()},
            )
            scheduled.append(sched)
            committed[lot.lot_id] = sched
            if duration > 0:
                _insert_interval(machine_intervals[machine_id],
                                 actual_start, actual_end)

            # 5. Reservation log (created + consumed at commit instant for V1).
            for ing, prod in producer_picks.items():
                latest_acc = feas.latest_acceptable_end_min - duration if feas else actual_start
                reservation_log.append(ReservationLogEntry(
                    event_minute=actual_start, event_type="created",
                    consumer_lot_id=lot.lot_id, producer_lot_id=prod.lot_id,
                    item_code=ing, qty=prod.qty,
                    producer_end_min=prod.end_min,
                    latest_acceptable_start_min=latest_acc,
                ))
                reservation_log.append(ReservationLogEntry(
                    event_minute=actual_start, event_type="consumed",
                    consumer_lot_id=lot.lot_id, producer_lot_id=prod.lot_id,
                    item_code=ing, qty=prod.qty,
                    producer_end_min=prod.end_min,
                    latest_acceptable_start_min=latest_acc,
                ))

            # Add this committed lot as a FEFO candidate for future consumers.
            fefo_candidates.setdefault(item, []).append(FefoCandidate(
                lot_id=lot.lot_id,
                end_min=actual_end,
                min_aging_min=_aging_min_for(item, norm.aging_df),
                max_aging_min=_aging_max_for(item, norm.aging_df),
            ))

    # Stable output ordering for deterministic CSVs.
    scheduled.sort(key=lambda s: (s.start_min, s.machine_id, s.lot_id))
    infeasibilities.sort(key=lambda i: i.lot_id)
    reservation_log.sort(key=lambda r: (r.event_minute, r.event_type,
                                         r.consumer_lot_id, r.producer_lot_id))
    return ScheduleResult(
        scheduled=scheduled,
        infeasibilities=infeasibilities,
        reservation_log=reservation_log,
    )
