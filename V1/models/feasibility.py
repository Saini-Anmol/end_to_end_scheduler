"""Backward feasibility limits per lot (Module 6 output).

V1 simplification: `latest_acceptable_end_min` is computed using ONLY the
min-aging chain from the lot's item up to the SKU (treated as zero-aging
finished good). Per-lot intermediate processing times are deferred to the
forward scheduler (which knows the chosen machine + lot duration).

This makes the deadline *conservative* — i.e., gives the lot LESS slack than
strictly necessary, so any schedule honouring it is feasible. The forward
scheduler may refine using actual durations.

Module 8 (time_calculation) will compute per-lot duration and the forward
scheduler will derive `latest_acceptable_start_min = latest_acceptable_end_min
- duration_min`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LotFeasibility:
    lot_id: str
    item_code: str
    # Latest minute the lot must FINISH by to satisfy min-aging downstream
    # to the earliest curing block it serves. Taken as min over served blocks.
    latest_acceptable_end_min: int
    # Cumulative min-aging from the lot's item (inclusive) up to the SKU
    # (inclusive). Independent of which block is served — a property of the
    # BOM topology and the item.
    chain_min_aging_min: int


@dataclass
class FeasibilityResult:
    feasibilities: list[LotFeasibility]

    def by_lot_id(self) -> dict[str, LotFeasibility]:
        return {f.lot_id: f for f in self.feasibilities}
