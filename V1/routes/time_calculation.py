"""Route 6 — time_calculation (Section 10 #6, approach-flow step 16).

Per L10/L20: `duration_min = ceil(nominal_min / 0.95)` with a single ceil
rounding direction throughout.

Three nominal-minute regimes, selected per routing row:

  A. **Continuous** (`proc_time_UOM == "M/MIN"`) — length-based:
        nominal = ceil(lot_qty_in_MTR / proc_time)

  B. **Per-batch** (`batch_size` is set, any UOM):
        n_batches    = ceil(lot_qty_in_batch_unit / batch_size)
        per_batch    = ceil(proc_time / 60)            (SEC/BATCH, SEC)
                       or ceil(proc_time)              (MIN)
        nominal      = n_batches × per_batch

  C. **Per-cycle / per-unit** (`batch_size` is NaN, UOM in {SEC, SEC/BATCH, MIN}):
        cycle_size   = 2 for Tyre Building (VMIMaxx GROUP per L8 / settings)
                       = 1 for everything else (one bead per cycle, one cut per
                         cycle, …)
        n_units      = lot_qty / bom_output_qty   (converts to NOS-equivalent
                       output units when lot.uom is e.g. MM and one NOS = N MM)
        n_cycles     = ceil(n_units / cycle_size)
        per_cycle    = ceil(proc_time / 60)            (SEC/BATCH, SEC)
                       or ceil(proc_time)              (MIN)
        nominal      = n_cycles × per_cycle

Special case: lots with `qty == 0` (zero-tyre placeholder GT lots) get
duration = 0 — they're traceability rows, no actual production.

Curing rows are SKIPPED — curing is fixed input (L4.5).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from V1.config.settings import Settings
from V1.models.lot import Lot, LotsResult
from V1.utilities.machine_parser import build_eligibility_index
from V1.utilities.time_math import apply_efficiency, ceil_div
from V1.utilities.unit_conversion import NormalisedResult, _norm_uom, convert_qty


# Building operation identifiers (lower-cased for case-insensitive match).
_BUILDING_OPERATION_NAMES: frozenset[str] = frozenset({"vmimaxx group"})
_BUILDING_DEPARTMENTS: frozenset[str] = frozenset({"building"})


@dataclass
class DurationResult:
    """`durations[lot_id][machine_id] = duration_min`."""
    durations: dict[str, dict[str, int]]

    def for_lot(self, lot_id: str) -> dict[str, int]:
        return self.durations.get(lot_id, {})

    def fastest(self, lot_id: str) -> tuple[str | None, int | None]:
        d = self.for_lot(lot_id)
        if not d:
            return None, None
        m, dur = min(d.items(), key=lambda kv: (kv[1], kv[0]))
        return m, dur


def _is_building_row(routing_row: pd.Series) -> bool:
    op = str(routing_row.get("operation_name", "")).strip().lower()
    dept = str(routing_row.get("department", "")).strip().lower()
    return op in _BUILDING_OPERATION_NAMES or dept in _BUILDING_DEPARTMENTS


def _qty_in_natural_units(
    lot_qty: float, lot_uom: str,
    bom_output_qty: float | None, bom_output_uom: str | None,
) -> float:
    """Convert lot.qty (in lot.uom) to natural output units (1 unit = 1 NOS).

    Examples:
      lot.qty=119040 MM, bom_output_qty=1860 MM/NOS → 64 NOS
      lot.qty=64 NOS, bom_output_qty=1 NOS         → 64 NOS
      lot.qty=22.56 KG, bom_output_qty=0.352 KG/NOS → 64 NOS (mass-per-unit)
    """
    if bom_output_qty is None or bom_output_qty <= 0:
        return float(lot_qty)
    if _norm_uom(lot_uom) == _norm_uom(bom_output_uom or lot_uom):
        return float(lot_qty) / float(bom_output_qty)
    # Different UOM — convert lot.qty to bom_output_uom first.
    converted = convert_qty(
        lot_qty, lot_uom, bom_output_uom or lot_uom,
        bom_output_qty=bom_output_qty, bom_output_uom=bom_output_uom,
    )
    return converted / float(bom_output_qty)


def _nominal_min(
    routing_row: pd.Series,
    lot_qty: float, lot_uom: str,
    bom_output_qty: float | None, bom_output_uom: str | None,
    building_cycle_size: int,
) -> int:
    """Compute nominal minutes for one lot on one operation (L20)."""
    if lot_qty == 0:
        # Zero-qty placeholder lot (e.g. b00 zero-tyre Building lot).
        return 0

    proc_time = float(routing_row["proc_time"])
    proc_uom = str(routing_row["proc_time_UOM"]).strip()
    batch_size_raw = routing_row.get("batch_size")
    batch_size = float(batch_size_raw) if pd.notna(batch_size_raw) else None
    batch_unit = (str(routing_row["batch_UNIT"])
                  if pd.notna(routing_row.get("batch_UNIT")) else None)

    # A. Continuous (M/MIN) — length-based on running material.
    if proc_uom == "M/MIN":
        qty_mtr = convert_qty(lot_qty, lot_uom, "MTR",
                              bom_output_qty=bom_output_qty,
                              bom_output_uom=bom_output_uom)
        if proc_time <= 0:
            raise ValueError(f"proc_time must be > 0 for M/MIN, got {proc_time}")
        return int(math.ceil(qty_mtr / float(proc_time)))

    # B. Per-batch — when batch_size + batch_UNIT are set.
    if batch_size is not None and batch_size > 0 and batch_unit:
        qty_in_batch_uom = convert_qty(
            lot_qty, lot_uom, batch_unit,
            bom_output_qty=bom_output_qty, bom_output_uom=bom_output_uom,
        )
        n_batches = max(1, math.ceil(qty_in_batch_uom / batch_size))
        if proc_uom in ("SEC/BATCH", "SEC"):
            per_batch = ceil_div(proc_time, 60)
        elif proc_uom == "MIN":
            per_batch = int(math.ceil(proc_time))
        else:
            raise ValueError(f"Unsupported proc_time_UOM with batch: {proc_uom!r}")
        return n_batches * per_batch

    # C. Per-cycle / per-unit — no batch_size, time is per output unit.
    cycle_size = building_cycle_size if _is_building_row(routing_row) else 1
    n_units = _qty_in_natural_units(lot_qty, lot_uom, bom_output_qty,
                                    bom_output_uom)
    n_cycles = max(1, math.ceil(n_units / cycle_size))
    if proc_uom in ("SEC/BATCH", "SEC"):
        per_cycle = ceil_div(proc_time, 60)
    elif proc_uom == "MIN":
        per_cycle = int(math.ceil(proc_time))
    else:
        raise ValueError(f"Unsupported proc_time_UOM (no batch): {proc_uom!r}")
    return n_cycles * per_cycle


def run(
    lots: LotsResult,
    norm: NormalisedResult,
    settings: Settings,
) -> DurationResult:
    """Compute per-(lot, machine) duration for every lot."""
    routing = norm.routing_df
    eligibility = build_eligibility_index(routing)

    routing_idx: dict[tuple[str, int], pd.Series] = {}
    for _, row in routing.iterrows():
        key = (str(row["routed_product"]), int(row["operation_seq"]))
        routing_idx[key] = row

    out: dict[str, dict[str, int]] = {}
    for lot in lots.lots:
        key = (lot.item_code, lot.op_seq)
        if key not in routing_idx:
            continue
        row = routing_idx[key]
        proc_time = row.get("proc_time")
        if proc_time is None or pd.isna(proc_time) or float(proc_time) <= 0:
            continue
        nominal = _nominal_min(
            routing_row=row,
            lot_qty=lot.qty, lot_uom=lot.uom,
            bom_output_qty=lot.bom_output_qty,
            bom_output_uom=lot.bom_output_uom,
            building_cycle_size=settings.building_tyres_per_cycle,
        )
        if nominal == 0:
            # Zero-qty placeholder lot — still record 0 duration on each
            # eligible machine so downstream lookups don't KeyError.
            effective = 0
        else:
            effective = apply_efficiency(nominal, settings.efficiency_factor)

        machines = eligibility.get(key, [])
        out[lot.lot_id] = {m: effective for m in machines}

    return DurationResult(durations=out)
