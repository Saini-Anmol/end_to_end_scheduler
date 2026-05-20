"""Route 6 — time_calculation (Section 10 #6, approach-flow step 16).

For each (lot, eligible_machine) pair: duration_min = ceil(nominal_min / 0.95)
per L10/L20. Single ceil rounding direction throughout (L20).

Nominal-minute rules by routing proc_time_UOM (L20):
  - SEC/BATCH  → n_batches × ceil(proc_time / 60)
  - SEC        → n_batches × ceil(proc_time / 60)        (if batch_size set)
                 else ceil(proc_time / 60)               (per-lot)
  - MIN        → n_batches × ceil(proc_time)             (if batch_size set)
                 else ceil(proc_time)                    (per-lot)
  - M/MIN      → ceil(lot_qty_mtr / proc_time)           (continuous; needs lot_qty in MTR)

Curing rows are SKIPPED — curing is fixed input (L4.5); its times come from
the published schedule, not from this module.

Output: DurationResult mapping `lot_id → {machine_id → duration_min}`. V1
typically yields identical durations across a lot's eligible machines (same
proc_time per row), but we keep the per-machine shape for future-proofing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from V1.config.settings import Settings
from V1.models.lot import LotsResult
from V1.utilities.machine_parser import build_eligibility_index
from V1.utilities.time_math import apply_efficiency, ceil_div
from V1.utilities.unit_conversion import NormalisedResult, convert_qty


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


def _nominal_min(
    proc_time: float, proc_uom: str,
    lot_qty: float, lot_uom: str,
    batch_size: float | None, batch_unit: str | None,
    bom_output_qty: float | None, bom_output_uom: str | None,
) -> int:
    """Compute nominal minutes for one lot on one operation (L20)."""
    uom = proc_uom.strip()
    if uom == "M/MIN":
        qty_mtr = convert_qty(lot_qty, lot_uom, "MTR",
                              bom_output_qty=bom_output_qty,
                              bom_output_uom=bom_output_uom)
        if proc_time <= 0:
            raise ValueError(f"proc_time must be > 0 for M/MIN, got {proc_time}")
        return int(math.ceil(qty_mtr / float(proc_time)))

    # Batch-based UOMs need batch_size + batch_unit; without them the op
    # treats the whole lot as one batch.
    if batch_size is None or pd.isna(batch_size) or batch_size <= 0:
        n_batches = 1
    else:
        qty_in_batch_uom = convert_qty(
            lot_qty, lot_uom, str(batch_unit or lot_uom),
            bom_output_qty=bom_output_qty,
            bom_output_uom=bom_output_uom,
        )
        n_batches = max(1, math.ceil(qty_in_batch_uom / float(batch_size)))

    if uom in ("SEC/BATCH", "SEC"):
        per_batch = ceil_div(float(proc_time), 60)
    elif uom == "MIN":
        per_batch = int(math.ceil(float(proc_time)))
    else:
        raise ValueError(f"Unsupported proc_time_UOM: {uom!r}")
    return int(n_batches * per_batch)


def run(
    lots: LotsResult,
    norm: NormalisedResult,
    settings: Settings,
) -> DurationResult:
    """Compute per-(lot, machine) duration for every lot."""
    routing = norm.routing_df
    eligibility = build_eligibility_index(routing)

    # Index routing by (item, op_seq) for O(1) lookup.
    routing_idx: dict[tuple[str, int], pd.Series] = {}
    for _, row in routing.iterrows():
        key = (str(row["routed_product"]), int(row["operation_seq"]))
        routing_idx[key] = row

    out: dict[str, dict[str, int]] = {}
    for lot in lots.lots:
        key = (lot.item_code, lot.op_seq)
        if key not in routing_idx:
            # Curing op (op_seq=80 on SKU) doesn't have a routing-driven
            # duration; lot_sizing already skips the SKU.
            continue
        row = routing_idx[key]
        proc_time = float(row["proc_time"])
        proc_uom = str(row["proc_time_UOM"])
        batch_size_raw = row.get("batch_size")
        batch_size = float(batch_size_raw) if pd.notna(batch_size_raw) else None
        batch_unit = row.get("batch_UNIT") if pd.notna(row.get("batch_UNIT")) else None

        # Skip rows whose proc_time is null — audit HALTs on these, but tests
        # that bypass the HALT shouldn't crash here.
        if not (proc_time == proc_time and proc_time > 0):  # NaN-safe
            continue
        nominal = _nominal_min(
            proc_time=proc_time, proc_uom=proc_uom,
            lot_qty=lot.qty, lot_uom=lot.uom,
            batch_size=batch_size, batch_unit=batch_unit,
            bom_output_qty=lot.bom_output_qty,
            bom_output_uom=lot.bom_output_uom,
        )
        effective = apply_efficiency(nominal, settings.efficiency_factor)

        machines = eligibility.get(key, [])
        out[lot.lot_id] = {m: effective for m in machines}

    return DurationResult(durations=out)
