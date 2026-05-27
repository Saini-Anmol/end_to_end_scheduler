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

L16 (soft reservation) — V1 implements the **sequential qty-shared** model:
  one producer lot may feed multiple consumers across time, but at any
  given commit instant the reservation is exclusive on a per-(producer,
  remaining_qty) basis. The reservation log records one `created`+`consumed`
  pair per (consumer, producer) match, carrying the per-consumer share of
  the producer's qty (NOT the producer's full qty). End-of-run invariant:
  for every producer, `sum(consumed_share) ≤ producer.qty` (raws excluded).

Not yet implemented (deferred from V1):
  - Strict event-heap dispatch (L21) — we use topo+greedy instead.
  - Full LSF tiebreak chain (L15) — sequential dispatch avoids the tie.
  - Soft-reservation EXPIRY (L16 (a) + `released` events) — sequential
    dispatch with no contention never lets a reservation outlive its
    consumer's commit.
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


# Floating-point slack for qty bookkeeping (KG / MM / NOS are all well below
# 1e-3 precision of interest in this pilot).
_QTY_EPS = 1e-6


def _bom_edge_ratio(
    consumer_item: str,
    ingredient_item: str,
    bom: BomGraph,
) -> float:
    """Per-unit-of-consumer ingredient consumption from the BOM edge.

    BOM edge (consumer → ingredient) carries `output_qty` (consumer's
    per-unit batch in its UOM) and `qty` (ingredient consumed per batch in
    its UOM). Ratio = qty / output_qty.

    Returns 0.0 if the edge is missing or the BOM doesn't permit the
    conversion (e.g., raw / work-away items the consumer doesn't actually
    consume through this edge).
    """
    edge = bom.graph.get_edge_data(consumer_item, ingredient_item)
    if edge is None:
        return 0.0
    out_q = edge.get("output_qty")
    in_q = edge.get("qty")
    if out_q is None or in_q is None or out_q <= 0:
        return 0.0
    return float(in_q) / float(out_q)


def _consumer_ingredient_demand(
    consumer_lot,
    ingredient_item: str,
    bom: BomGraph,
) -> float:
    """Total ingredient need for `consumer_lot` across all its served blocks.

    Computed via the BOM edge between the consumer's item and the ingredient,
    multiplied by the consumer's lot qty. This is the CONSUMER-SPECIFIC share
    (not the producer-side total demand across all consumers), which is what
    matters for FEFO reservation — a producer feeding multiple distinct
    consumer items (e.g. CPJ1218 → both 162mm and 154mm cuts) must apportion
    its qty across them by edge ratio, not by total per-block demand.
    """
    ratio = _bom_edge_ratio(consumer_lot.item_code, ingredient_item, bom)
    if ratio == 0.0:
        return 0.0
    return float(consumer_lot.qty * ratio)


def _consumer_ingredient_demand_for_blocks(
    consumer_lot,
    ingredient_item: str,
    bom: BomGraph,
    blocks: Iterable[str],
) -> float:
    """Per-block-subset ingredient need for `consumer_lot`.

    Used to compute the take from a producer that overlaps the consumer on
    only some of the consumer's blocks. Uses `Lot.qty_by_block` to prorate
    accurately (handles pre-shift zero-tyre blocks correctly).
    """
    ratio = _bom_edge_ratio(consumer_lot.item_code, ingredient_item, bom)
    if ratio == 0.0:
        return 0.0
    consumer_qty_in_blocks = sum(
        consumer_lot.qty_by_block.get(b, 0.0) for b in blocks
    )
    return float(consumer_qty_in_blocks * ratio)


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
      - floor:   the EARLIEST consumer's target_start − max_aging.
                 Using MIN (not MAX) handles the common case where a single
                 producer lot serves both early- and late-block consumers:
                 we MUST end early enough to feed the earliest consumer.
                 Late-consumer aging-MAX violations (if any) are reported
                 by diagnostics per L11 (flag-and-continue). MAX would push
                 the producer past its early consumer's window entirely,
                 effectively losing those Building lots.

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
                # Floor uses MIN, not MAX — see docstring. The producer must
                # end early enough to feed the EARLIEST consumer; if the
                # latest consumer would push aging-MAX, that's a flagged
                # violation per L11 — but we prioritise feeding the early
                # consumers over avoiding late-consumer warnings.
                floors[lot.lot_id] = min(floor_candidates)
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

    # L16 soft-reservation bookkeeping. Tracks qty already consumed off each
    # producer lot. A producer is selectable by a new consumer iff
    # `producer.qty - reserved_consumed[producer.lot_id] ≥ consumer_share`.
    reserved_consumed: dict[str, float] = {}

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

            # 1. Find producer(s) for each BOM-child ingredient.
            #    Producer match honours L16 sequential qty-shared reservation:
            #    iterate FEFO picks for each ingredient until the consumer's
            #    full per-block share is reserved. Multiple producer lots may
            #    be needed if MPQ-split has fragmented the producer side
            #    below the consumer's per-block demand.
            ingredients = bom.children(item, exclude_capstrip=True)
            producer_picks: dict[str, list[tuple[ScheduledLot, float]]] = {}
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

                consumer_blocks = set(lot.serves_blocks)
                share_needed = _consumer_ingredient_demand(lot, ing, bom)
                if share_needed <= _QTY_EPS:
                    # Consumer doesn't actually need this ingredient (zero
                    # per-block demand) — skip.
                    continue

                share_reserved = 0.0
                picks_for_ing: list[tuple[ScheduledLot, float]] = []
                picked_ids: set[str] = set()
                transfer_min = _transfer_min_for(
                    ing, norm.routing_df, settings.default_transfer_min,
                )
                # Iterate FEFO picks until either share is satisfied or no
                # more eligible producers remain. From each picked producer,
                # take EXACTLY the per-block-intersection share (not a
                # greedy max-fill) — this lets a single producer feed several
                # consumers across distinct blocks without over- or
                # under-commitment.
                while share_reserved + _QTY_EPS < share_needed:
                    overlapping: list[FefoCandidate] = []
                    for c in fefo_candidates[ing]:
                        if c.lot_id in picked_ids:
                            continue
                        p_lot = committed[c.lot_id]
                        if set(p_lot.serves_blocks).isdisjoint(consumer_blocks):
                            continue
                        remaining = p_lot.qty - reserved_consumed.get(c.lot_id, 0.0)
                        if remaining <= _QTY_EPS:
                            continue
                        overlapping.append(c)
                    if not overlapping:
                        break
                    candidate_min = max(
                        earliest_start,
                        min(c.end_min + max(c.min_aging_min, transfer_min)
                            for c in overlapping)
                    )
                    picked = fefo_pick(overlapping, at_min=candidate_min)
                    if picked is None:
                        # No producer is in-window AT THE CANDIDATE MINUTE.
                        # Per L11 (flag-and-continue): commit anyway with the
                        # LEAST-EXPIRED overlapping producer (highest
                        # expiry_min). The producer's actual end_min may be
                        # shifted later by the JIT post-pass — either way,
                        # diagnostics will re-check the consumer-producer
                        # gap and flag any aging-MAX breach in
                        # aging_violations.csv (CLAUDE.md §11 + §15.25).
                        # This stops the multi-producer cascade from
                        # snowballing 1 expired ingredient into 20+ Building
                        # infeasibilities downstream.
                        overlapping.sort(
                            key=lambda c: (-(c.end_min + c.max_aging_min), c.lot_id)
                        )
                        picked = overlapping[0]
                    p_lot = committed[picked.lot_id]
                    # Per-block-intersection share = the qty of this producer
                    # that this consumer actually needs (covers only the
                    # blocks they share). Bound by remaining qty so we never
                    # overdraw a producer whose blocks intersect more than
                    # one consumer.
                    shared_blocks = consumer_blocks & set(p_lot.serves_blocks)
                    intersect_share = _consumer_ingredient_demand_for_blocks(
                        lot, ing, bom, shared_blocks,
                    )
                    available = p_lot.qty - reserved_consumed.get(picked.lot_id, 0.0)
                    take = min(intersect_share, available)
                    if take <= _QTY_EPS:
                        # Producer technically overlapped on blocks but has
                        # no remaining intersect-share — skip and try next.
                        picked_ids.add(picked.lot_id)
                        continue
                    picks_for_ing.append((p_lot, take))
                    picked_ids.add(picked.lot_id)
                    share_reserved += take
                    earliest_start = max(
                        earliest_start,
                        picked.end_min + max(picked.min_aging_min, transfer_min),
                    )

                if share_reserved + _QTY_EPS < share_needed:
                    blocking_reason = (
                        f"BLOCK_OVERLAP: ingredient {ing!r} — only "
                        f"{share_reserved:.4f} of {share_needed:.4f} share "
                        f"reservable from overlapping/in-window producers"
                    )
                    break
                producer_picks[ing] = picks_for_ing

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

            # Machine ordering. Non-Building lots: best (actual_end, machine_id)
            # across the eligible pool. Building lots (L18): pin to the
            # configured primary (6001) and wait for it; spill to another
            # building machine ONLY if waiting on the primary would push the
            # lot past its aging-MIN ceiling.
            feas = feasibility_by_lot.get(lot.lot_id)
            ceiling = target_ceilings.get(lot.lot_id)
            if ceiling is None and feas is not None:
                ceiling = feas.latest_acceptable_end_min
            floor = target_floors.get(lot.lot_id, 0)
            duration_map = durations.for_lot(lot.lot_id)

            def _slot_on(m: str) -> tuple[int, int, int] | None:
                if m not in duration_map:
                    return None
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
                return (actual_start, duration, actual_start + duration)

            best: tuple[str, int, int, int] | None = None
            if _is_building_lot(lot, settings):
                preferred = settings.building_primary
                spill_pool = [m for m in sorted(machines) if m != preferred]
                primary_slot = _slot_on(preferred) if preferred in machines else None
                if primary_slot is not None and (
                    ceiling is None or primary_slot[2] <= ceiling
                ):
                    # Primary fits within aging-MIN ceiling — stay on primary.
                    best = (preferred, *primary_slot)
                else:
                    # Primary would breach (or unavailable). Try spill — pick
                    # the candidate with the earliest actual_end that fits
                    # within the ceiling. If none fit, fall back to primary
                    # (preserving floor discipline per planner's L3 intent)
                    # and let L11 flag-and-continue mark on_time_flag=False.
                    spill_best: tuple[str, int, int, int] | None = None
                    for m in spill_pool:
                        slot = _slot_on(m)
                        if slot is None:
                            continue
                        if ceiling is not None and slot[2] > ceiling:
                            continue
                        cand = (m, *slot)
                        if spill_best is None or (slot[2], m) < (spill_best[3], spill_best[0]):
                            spill_best = cand
                    if spill_best is not None:
                        best = spill_best
                    elif primary_slot is not None:
                        best = (preferred, *primary_slot)
                    else:
                        # No primary slot AND no in-window spill — pick the
                        # earliest-finishing spill anyway so we commit something.
                        for m in spill_pool:
                            slot = _slot_on(m)
                            if slot is None:
                                continue
                            cand = (m, *slot)
                            if best is None or (slot[2], m) < (best[3], best[0]):
                                best = cand
            else:
                for m in sorted(machines):
                    slot = _slot_on(m)
                    if slot is None:
                        continue
                    cand = (m, *slot)
                    if best is None or (slot[2], m) < (best[3], best[0]):
                        best = cand

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
                producer_lot_ids={
                    ing: [p.lot_id for p, _share in picks]
                    for ing, picks in producer_picks.items()
                },
            )
            scheduled.append(sched)
            committed[lot.lot_id] = sched
            if duration > 0:
                _insert_interval(machine_intervals[machine_id],
                                 actual_start, actual_end)

            # 5. Reservation log + qty bookkeeping (L16 sequential qty-shared).
            #    Each (consumer, producer) match emits one created+consumed
            #    pair with qty = per-consumer share. The producer's remaining
            #    qty is decremented so a later consumer cannot double-book it.
            for ing, picks in producer_picks.items():
                latest_acc = feas.latest_acceptable_end_min - duration if feas else actual_start
                for prod, share in picks:
                    reserved_consumed[prod.lot_id] = (
                        reserved_consumed.get(prod.lot_id, 0.0) + share
                    )
                    reservation_log.append(ReservationLogEntry(
                        event_minute=actual_start, event_type="created",
                        consumer_lot_id=lot.lot_id, producer_lot_id=prod.lot_id,
                        item_code=ing, qty=share,
                        producer_end_min=prod.end_min,
                        latest_acceptable_start_min=latest_acc,
                    ))
                    reservation_log.append(ReservationLogEntry(
                        event_minute=actual_start, event_type="consumed",
                        consumer_lot_id=lot.lot_id, producer_lot_id=prod.lot_id,
                        item_code=ing, qty=share,
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

    # ---- Just-in-time delay post-pass --------------------------------------
    # The forward pass schedules each lot as early as its floor (aging-MAX-safe
    # earliest end) allows. When a downstream consumer ends up running later
    # than the CPM estimate (because of contention or sequential pinning),
    # the producer's actual end can fall outside its aging-MAX window relative
    # to the consumer's actual start — the MB231 → MB1232 master-to-master
    # case is the canonical example.
    #
    # This post-pass walks committed lots from consumers down to producers and
    # delays each producer so its end lands at, or just inside, the consumer's
    # min_aging window. Constraints respected:
    #   - Producer only moves FORWARD in time (never earlier than current start).
    #   - Producer's machine intervals stay legal (no overlap with other lots).
    #   - GT lots are NOT moved (curing is fixed input; GT must hit aging-MIN
    #     ceiling vs curing_start, which the forward pass already targets).
    consumers_by_producer: dict[str, list[str]] = {}
    for sched_lot in scheduled:
        for ing, prod_ids in sched_lot.producer_lot_ids.items():
            for prod_id in prod_ids:
                consumers_by_producer.setdefault(prod_id, []).append(sched_lot.lot_id)

    aging_min_by_item = _aging_min_lookup(norm.aging_df)

    # Process producers in reverse topological order so consumers are already
    # in their final positions before we delay any producer.
    delay_order: list[str] = []
    for item in reversed(item_order):
        for lot in lots_by_item.get(item, []):
            if lot.lot_id in committed and lot.item_code != settings.green_tyre_code:
                delay_order.append(lot.lot_id)

    by_id: dict[str, ScheduledLot] = {s.lot_id: s for s in scheduled}
    for prod_id in delay_order:
        prod = by_id.get(prod_id)
        if prod is None or prod.duration_min == 0:
            continue
        consumer_ids = consumers_by_producer.get(prod_id, [])
        if not consumer_ids:
            continue
        # Latest end the producer can finish at = MIN over consumers of
        # (consumer.start - this_min_aging).
        this_min_aging = aging_min_by_item.get(prod.item_code, 0)
        consumer_starts = [by_id[c].start_min for c in consumer_ids if c in by_id]
        if not consumer_starts:
            continue
        latest_end_jit = min(consumer_starts) - this_min_aging
        if latest_end_jit <= prod.end_min:
            continue  # already at or past JIT — nothing to do
        # Find machine-interval gap that fits (start, end) where
        # prod.start_min ≤ new_start ≤ latest_end_jit - duration.
        m = prod.machine_id
        if m == "—":
            continue
        intervals = machine_intervals.get(m, [])
        # Remove this producer's current interval; we will re-insert.
        try:
            intervals.remove((prod.start_min, prod.end_min))
        except ValueError:
            continue
        target_start = latest_end_jit - prod.duration_min
        # Find the LATEST start ≤ target_start with prod.start_min as floor
        # that doesn't overlap with remaining intervals on the machine.
        chosen_start = prod.start_min
        for s, e in intervals:
            if s > prod.start_min and s + 0 <= target_start + prod.duration_min:
                # Could we fit BEFORE this interval at its (e_of_prev, s)?
                pass
        # Greedy: walk intervals; the gap ending at the next interval's start
        # bounds the producer. Track the latest legal start.
        cursor_lo = prod.start_min
        cursor_hi = target_start
        # Walk left-to-right, finding the latest gap that contains a slot of
        # `duration_min` minutes with end ≤ latest_end_jit.
        best_start = prod.start_min  # fallback: original
        prev_end = 0
        for s, e in intervals + [(10 ** 12, 10 ** 12)]:  # sentinel
            gap_start = max(prev_end, prod.start_min)
            gap_end = s  # exclusive upper bound
            if gap_end - gap_start >= prod.duration_min:
                # Latest valid start in this gap.
                latest_in_gap = min(gap_end - prod.duration_min, target_start)
                if latest_in_gap >= gap_start and latest_in_gap >= best_start:
                    best_start = latest_in_gap
            if s > target_start:
                break
            prev_end = e
        new_start = best_start
        new_end = new_start + prod.duration_min
        _insert_interval(intervals, new_start, new_end)
        if new_start == prod.start_min:
            continue  # nothing to do
        # Update the ScheduledLot (dataclass is frozen → replace).
        from dataclasses import replace
        updated = replace(prod, start_min=new_start, end_min=new_end)
        by_id[prod_id] = updated
        # Update reservation log entries that reference this producer's end.
        for rl in reservation_log:
            if rl.producer_lot_id == prod_id:
                # Rewrite producer_end_min only (it's a frozen dataclass).
                from dataclasses import replace as _rep
                idx = reservation_log.index(rl)
                reservation_log[idx] = _rep(rl, producer_end_min=new_end)

    # Rebuild scheduled list from by_id (preserve original insertion order
    # via the original `scheduled` list, swapping each entry with its
    # possibly-updated counterpart).
    scheduled = [by_id[s.lot_id] for s in scheduled]

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
