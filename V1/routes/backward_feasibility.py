"""Route 5 — backward_feasibility (Section 10 #5, approach-flow step 15).

For each lot, compute `latest_acceptable_end_min`: the latest minute the lot
can finish without breaching MIN aging downstream all the way to the
earliest served curing block.

V1 V1 simplification (documented in models/feasibility.py): aggregate ONLY
the min-aging chain, ignoring intermediate processing time. The forward
scheduler will refine this using actual lot durations.

Does NOT commit any time — pure forward pass owns scheduling (Section 10 #5).
"""
from __future__ import annotations

import pandas as pd

from V1.models.demand import DemandResult
from V1.models.feasibility import FeasibilityResult, LotFeasibility
from V1.models.lot import LotsResult
from V1.utilities.bom_walker import BomGraph
from V1.utilities.unit_conversion import NormalisedResult


def run(
    lots: LotsResult,
    demand: DemandResult,
    bom: BomGraph,
    norm: NormalisedResult,
) -> FeasibilityResult:
    """Compute latest_acceptable_end_min per lot."""
    curing_starts: dict[str, int] = {
        d.block_id: d.curing_start_min for d in demand.block_demands
    }
    # Also include zero-qty placeholder rows from curing_df (b00 doesn't
    # appear in demand because of the zero-tyre filter, but GT lots cover
    # every curing row per L1).
    for idx, row in norm.curing_df.reset_index(drop=True).iterrows():
        bid = f"b{int(idx):02d}"
        curing_starts.setdefault(bid, int(row["start_min"]))

    # Cache per-item chain min-aging (reused across all lots of the same item).
    chain_cache: dict[str, int] = {}

    feasibilities: list[LotFeasibility] = []
    for lot in lots.lots:
        item = lot.item_code
        if item not in chain_cache:
            chain_cache[item] = bom.longest_min_aging_path_from(item)
        chain = chain_cache[item]

        # The earliest served block dominates the deadline.
        earliest_curing = min(curing_starts[b] for b in lot.serves_blocks)
        latest_end = int(earliest_curing - chain)

        feasibilities.append(LotFeasibility(
            lot_id=lot.lot_id,
            item_code=item,
            latest_acceptable_end_min=latest_end,
            chain_min_aging_min=int(chain),
        ))

    feasibilities.sort(key=lambda f: f.lot_id)
    return FeasibilityResult(feasibilities=feasibilities)
