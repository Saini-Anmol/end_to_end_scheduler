"""Route 3 — lot_sizing (Section 10 #3, approach-flow steps 10-13, Section 8.C).

For each demanded item with a routing row, forward-aggregates consecutive
block demands into the largest lot that satisfies BOTH:
  - lot_qty ≤ MPQ_Max
  - lot_curing_span ≤ (aging_MAX − aging_MIN)   [using curing_start as proxy
                                                  for consumer_start; the span
                                                  is preserved under any
                                                  constant downstream lead time]

When a single block's demand exceeds MPQ_Max, splits into equal-sized
sub-lots (no remainder < MPQ_Min). The split sub-lots all serve the same
single block.

**HALT** (Section 8.C, locked) — a single block's demand < MPQ_Min AND
aggregation across blocks is blocked by aging-MAX. Reports the offending
(block, compound).

UOM handling: demand is in BOM-natural UOM; MPQ is in MPQ-table UOM. We
convert MPQ to the lot's UOM (= demand UOM) once, then compare. Supported
conversions: same, MM↔MTR, NOS↔MM (via item.bom_output_qty).

Items without a routing row (raws, Work-Away) are skipped — they're not
produced by us per L2/L13.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from V1.config.halt_codes import HaltCode, HaltError
from V1.config.settings import Settings
from V1.models.demand import DemandResult, ItemDemand
from V1.models.finding import AuditFinding
from V1.config.enums import FindingSeverity
from V1.models.lot import Lot, LotsResult
from V1.utilities.lot_id import make_lot_id, safe_item_code
from V1.utilities.unit_conversion import NormalisedResult, convert_qty, _norm_uom


# --- helpers ---------------------------------------------------------------

def _block_chrono_index(bid: str) -> int:
    """Numeric position of a 'bNN' id (for sort + span math)."""
    return int(bid[1:])


def _routing_row(routing_df: pd.DataFrame, item: str) -> Optional[pd.Series]:
    rows = routing_df[routing_df["routed_product"] == item]
    if len(rows) == 0:
        return None
    return rows.iloc[0]


def _aging_row(aging_df: pd.DataFrame, item: str) -> Optional[pd.Series]:
    rows = aging_df[aging_df["ItemCode"].astype(str) == item]
    if len(rows) == 0:
        return None
    return rows.iloc[0]


def _mpq_row(mpq_df: pd.DataFrame, item_type: str) -> Optional[pd.Series]:
    norm = str(item_type).strip().lower()
    rows = mpq_df[mpq_df["Item Type"].astype(str).str.strip().str.lower() == norm]
    if len(rows) == 0:
        return None
    return rows.iloc[0]


def _mpq_thresholds(
    mpq_row: pd.Series, demand_uom: str, demand_bom_output_qty: float | None,
    demand_bom_output_uom: str | None,
) -> tuple[Optional[float], Optional[float], str]:
    """Returns (mpq_min_in_demand_uom, mpq_max_in_demand_uom, mpq_uom)."""
    mpq_uom = str(mpq_row["UOM"])
    mpq_min_raw = mpq_row.get("Minimum Run Qty")
    mpq_max_raw = mpq_row.get("Maximum Run Qty")
    mpq_min = (float(mpq_min_raw) if pd.notna(mpq_min_raw) else None)
    mpq_max = (float(mpq_max_raw) if pd.notna(mpq_max_raw) else None)

    def conv(v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        return convert_qty(v, mpq_uom, demand_uom,
                           bom_output_qty=demand_bom_output_qty,
                           bom_output_uom=demand_bom_output_uom)

    return conv(mpq_min), conv(mpq_max), mpq_uom


# --- core algorithm --------------------------------------------------------

@dataclass
class _LotGroup:
    """Internal scratch type — accumulates entries before becoming a Lot."""
    entries: list[tuple[str, float]]   # list of (block_id, qty)

    @property
    def total_qty(self) -> float:
        return sum(q for _, q in self.entries)

    @property
    def block_ids(self) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for bid, _ in self.entries:
            if bid not in seen:
                out.append(bid)
                seen.add(bid)
        return out

    def earliest_curing_min(self, curing_starts: dict[str, int]) -> int:
        return min(curing_starts[bid] for bid in self.block_ids)

    def latest_curing_min(self, curing_starts: dict[str, int]) -> int:
        return max(curing_starts[bid] for bid in self.block_ids)


def _equal_split_block(
    block_id: str, qty: float, mpq_min: Optional[float], mpq_max: float,
) -> list[float]:
    """Split a single block's qty into equal sub-lots of size ≤ MPQ_Max and
    (when set) ≥ MPQ_Min.
    """
    n = max(1, math.ceil(qty / mpq_max))
    if mpq_min is not None:
        max_n_for_min = int(qty // mpq_min) if mpq_min > 0 else n
        if max_n_for_min < n:
            # Cannot honour both bounds → caller should HALT.
            raise _SplitImpossible(block_id, qty, mpq_min, mpq_max)
    split_qty = qty / n
    return [split_qty] * n


class _SplitImpossible(Exception):
    def __init__(self, block_id: str, qty: float, mpq_min: float, mpq_max: float):
        self.block_id = block_id
        self.qty = qty
        self.mpq_min = mpq_min
        self.mpq_max = mpq_max


def _try_merge(
    a: _LotGroup, b: _LotGroup, mpq_max: Optional[float], aging_span_min: float,
    curing_starts: dict[str, int],
) -> Optional[_LotGroup]:
    merged_entries = a.entries + b.entries
    merged = _LotGroup(entries=merged_entries)
    if mpq_max is not None and merged.total_qty > mpq_max:
        return None
    span = merged.latest_curing_min(curing_starts) - merged.earliest_curing_min(curing_starts)
    if span > aging_span_min:
        return None
    return merged


def _aging_allows_merge(
    a: _LotGroup, b: _LotGroup, aging_span_min: float,
    curing_starts: dict[str, int],
) -> bool:
    """True iff aging-span alone (ignoring MPQ_Max) permits merging a and b."""
    merged = _LotGroup(entries=a.entries + b.entries)
    span = merged.latest_curing_min(curing_starts) - merged.earliest_curing_min(curing_starts)
    return span <= aging_span_min


def _aggregate(
    item_demand: ItemDemand,
    curing_starts: dict[str, int],
    mpq_min: Optional[float],
    mpq_max: Optional[float],
    aging_span_min: float,
) -> list[_LotGroup]:
    """Forward-aggregate + equal-split (Section 8.C)."""
    blocks_sorted = sorted(item_demand.serves_blocks, key=_block_chrono_index)

    groups: list[_LotGroup] = []
    current: _LotGroup | None = None

    for bid in blocks_sorted:
        bqty = item_demand.qty_by_block[bid]

        # Equal-split when a single block exceeds MPQ_Max.
        if mpq_max is not None and bqty > mpq_max:
            if current is not None:
                groups.append(current)
                current = None
            try:
                splits = _equal_split_block(bid, bqty, mpq_min, mpq_max)
            except _SplitImpossible as exc:
                raise HaltError(
                    HaltCode.LOT_SIZING_TIGHT_AGING,
                    f"Cannot equal-split block {exc.block_id} for item "
                    f"{item_demand.item_code!r}: qty={exc.qty:.3f}, "
                    f"MPQ=({exc.mpq_min:.3f}, {exc.mpq_max:.3f})."
                )
            for sq in splits:
                groups.append(_LotGroup(entries=[(bid, sq)]))
            continue

        if current is None:
            current = _LotGroup(entries=[(bid, bqty)])
            continue

        candidate = _LotGroup(entries=current.entries + [(bid, bqty)])
        candidate_span = (curing_starts[bid] -
                          current.earliest_curing_min(curing_starts))
        if (mpq_max is not None and candidate.total_qty > mpq_max) \
                or candidate_span > aging_span_min:
            groups.append(current)
            current = _LotGroup(entries=[(bid, bqty)])
        else:
            current = candidate

    if current is not None:
        groups.append(current)

    return groups


def _enforce_min_qty_or_halt(
    groups: list[_LotGroup],
    item_demand: ItemDemand,
    curing_starts: dict[str, int],
    mpq_min: Optional[float],
    mpq_max: Optional[float],
    aging_span_min: float,
) -> tuple[list[_LotGroup], list[str]]:
    """For each lot under MPQ_Min: try merge with prev/next.

    Dichotomy (CLAUDE.md §8.C is precise about which case HALTs):

      - **Single-block** lot under MPQ_Min that cannot merge (aging blocks
        aggregation) → **HALT** with the offending (block, compound).
      - **Multi-block** lot under MPQ_Min after aging-forced split → **WARN**
        and keep the lot (the total demand for the item is too small relative
        to MPQ_Min and the per-block split is forced by aging — this is
        structural, not a single-block tight-aging case).
    """
    warnings: list[str] = []
    if mpq_min is None:
        return groups, warnings

    i = 0
    while i < len(groups):
        g = groups[i]
        if g.total_qty >= mpq_min:
            i += 1
            continue
        if i > 0:
            merged = _try_merge(groups[i - 1], g, mpq_max, aging_span_min, curing_starts)
            if merged is not None:
                groups[i - 1] = merged
                groups.pop(i)
                continue
        if i + 1 < len(groups):
            merged = _try_merge(g, groups[i + 1], mpq_max, aging_span_min, curing_starts)
            if merged is not None:
                groups[i] = merged
                groups.pop(i + 1)
                continue
        # No merge possible. Decide HALT vs WARN per CLAUDE.md §8.C precisely.
        # The HALT case fires only when the under-min block is *aging-isolated
        # from every other block of the same item* — i.e., even ignoring lot
        # boundaries, no other block sits within the aging window of this one.
        # If a near-in-time neighbour exists (just MPQ_Max-blocked from merging),
        # this is structural under-production, not aging-induced — emit a WARN.
        is_single_block = len(g.block_ids) == 1
        if is_single_block:
            this_start = curing_starts[g.block_ids[0]]
            others = [b for b in item_demand.serves_blocks
                      if b != g.block_ids[0]]
            truly_aging_isolated = bool(others) and all(
                abs(curing_starts[b] - this_start) > aging_span_min
                for b in others
            )
            if truly_aging_isolated:
                raise HaltError(
                    HaltCode.LOT_SIZING_TIGHT_AGING,
                    f"Lot for item {item_demand.item_code!r} on block "
                    f"[{g.block_ids[0]}] has qty={g.total_qty:.3f} "
                    f"{item_demand.uom} < MPQ_Min ({mpq_min:.3f}); "
                    f"aging-MAX isolates this block from all other demand."
                )
        warnings.append(
            f"[LOT_SIZING_UNDER_MIN] {item_demand.item_code!r}: lot on blocks "
            f"[{', '.join(g.block_ids)}] qty={g.total_qty:.3f} {item_demand.uom} "
            f"< MPQ_Min ({mpq_min:.3f})."
        )
        i += 1
    return groups, warnings


# --- public entry ----------------------------------------------------------

def run(
    norm: NormalisedResult,
    demand: DemandResult,
    settings: Settings,
) -> LotsResult:
    """Forward-aggregate per-item demand into deterministic lots."""
    # block_id → curing_start_min lookup (built once)
    curing_starts: dict[str, int] = {}
    for d in demand.block_demands:
        curing_starts[d.block_id] = d.curing_start_min

    lots: list[Lot] = []
    all_warnings: list[str] = []

    for item in sorted(demand.item_demands.keys()):
        item_demand = demand.item_demands[item]
        if item == settings.sku_code:
            # L4.5 — curing is the demand event and a fixed input. We don't
            # lot-size the SKU; the published curing schedule defines it.
            continue
        routing_row = _routing_row(norm.routing_df, item)
        if routing_row is None:
            continue  # raws / work-away
        op_seq = int(routing_row["operation_seq"])
        item_type = item_demand.item_type
        if item_type is None:
            # Surface as a Warn in audit — here we just skip with a HALT-safe
            # message. (audit's pilot-master check already HALTs for the 9
            # mandatory items.)
            raise HaltError(
                HaltCode.AUDIT_MISSING_ITEMTYPE,
                f"Item {item!r} has no ItemType — cannot size lots."
            )

        mpq_row = _mpq_row(norm.audit.mpq_df, item_type)
        if mpq_row is None:
            # No MPQ — one lot per block, no bounds.
            mpq_min_in_uom: Optional[float] = None
            mpq_max_in_uom: Optional[float] = None
        else:
            mpq_min_in_uom, mpq_max_in_uom, _ = _mpq_thresholds(
                mpq_row, item_demand.uom,
                item_demand.bom_output_qty, item_demand.bom_output_uom,
            )

        aging_row = _aging_row(norm.aging_df, item)
        if aging_row is None or pd.isna(aging_row["min_aging_min"]) \
                or pd.isna(aging_row["max_aging_min"]):
            # No aging — assume infinite slack (single aggregated lot per item).
            aging_span_min = float("inf")
        else:
            aging_span_min = float(aging_row["max_aging_min"]) - float(
                aging_row["min_aging_min"])

        groups = _aggregate(item_demand, curing_starts,
                            mpq_min_in_uom, mpq_max_in_uom, aging_span_min)
        groups, item_warns = _enforce_min_qty_or_halt(
            groups, item_demand, curing_starts,
            mpq_min_in_uom, mpq_max_in_uom, aging_span_min)
        all_warnings.extend(item_warns)

        # Build Lot objects.
        for lot_seq, g in enumerate(groups, start=1):
            block_ids = sorted(g.block_ids, key=_block_chrono_index)
            qty_by_block: dict[str, float] = {}
            for bid, q in g.entries:
                qty_by_block[bid] = qty_by_block.get(bid, 0.0) + q
            lots.append(Lot(
                lot_id=make_lot_id(item, op_seq, lot_seq),
                item_code=item,
                op_seq=op_seq,
                item_type=item_type,
                qty=g.total_qty,
                uom=item_demand.uom,
                serves_blocks=block_ids,
                earliest_block_id=block_ids[0],
                latest_block_id=block_ids[-1],
                bom_output_qty=item_demand.bom_output_qty,
                bom_output_uom=item_demand.bom_output_uom,
                qty_by_block=qty_by_block,
            ))

    # Stable order: by safe_item_code, then op_seq, then lot_seq (== lot_id sort).
    lots.sort(key=lambda lot: lot.lot_id)
    return LotsResult(lots=lots, warnings=all_warnings)
