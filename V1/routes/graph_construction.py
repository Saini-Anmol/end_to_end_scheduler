"""Route 4 — graph_construction (Section 10 #4, approach-flow step 14).

Builds the lot-level DAG: one node per lot, one directed edge per
*potential* consumer → producer pairing across each BOM edge. An edge
exists from consumer-lot C of item X to producer-lot P of item Y iff:
  - X consumes Y in the BOM (in-scope, not capstrip).
  - C.serves_blocks ∩ P.serves_blocks ≠ ∅ (block overlap).

Edges carry (min_aging_min, max_aging_min, effective_gap_min) — the aging
window of the producer item, with effective_gap = max(transfer_time, MIN_aging)
per L14.

The forward scheduler later chooses ONE producer per consumer ingredient via
FEFO (L19). Until then, the DAG enumerates every potential producer for
diagnostics + dag.json export.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import networkx as nx
import pandas as pd

from V1.config.settings import Settings
from V1.models.lot import LotsResult
from V1.utilities.bom_walker import BomGraph
from V1.utilities.unit_conversion import NormalisedResult


@dataclass
class LotDagResult:
    """Output of Module 9."""
    graph: nx.DiGraph

    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    def edge_count(self) -> int:
        return self.graph.number_of_edges()


def _aging_lookup(aging_df: pd.DataFrame) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for _, row in aging_df.iterrows():
        if pd.notna(row.get("min_aging_min")) and pd.notna(row.get("max_aging_min")):
            out[str(row["ItemCode"])] = (
                int(row["min_aging_min"]), int(row["max_aging_min"])
            )
    return out


def _transfer_time_lookup(routing_df: pd.DataFrame, default_min: int) -> dict[str, int]:
    out: dict[str, int] = {}
    for _, row in routing_df.iterrows():
        item = str(row["routed_product"])
        t = row.get("transfer_time_min")
        out[item] = int(t) if pd.notna(t) else default_min
    return out


def run(
    lots: LotsResult,
    bom: BomGraph,
    norm: NormalisedResult,
    settings: Settings,
) -> LotDagResult:
    aging = _aging_lookup(norm.aging_df)
    transfer = _transfer_time_lookup(norm.routing_df, settings.default_transfer_min)

    # Index lots by item
    lots_by_item: dict[str, list] = {}
    for lot in lots.lots:
        lots_by_item.setdefault(lot.item_code, []).append(lot)
    for item in lots_by_item:
        lots_by_item[item].sort(key=lambda l: l.lot_id)

    g = nx.DiGraph()
    for lot in lots.lots:
        g.add_node(lot.lot_id,
                   item_code=lot.item_code,
                   op_seq=lot.op_seq,
                   item_type=lot.item_type,
                   qty=lot.qty,
                   uom=lot.uom,
                   serves_blocks=list(lot.serves_blocks))

    # For each consumer lot, walk its BOM children to find producers.
    for consumer in lots.lots:
        consumer_blocks = set(consumer.serves_blocks)
        for child_item in bom.children(consumer.item_code, exclude_capstrip=True):
            if child_item not in lots_by_item:
                continue  # raw / work-away — no producer lots
            min_a, max_a = aging.get(child_item, (0, 0))
            transfer_min = transfer.get(child_item, settings.default_transfer_min)
            effective_gap = max(transfer_min, min_a)
            for producer in lots_by_item[child_item]:
                if consumer_blocks.isdisjoint(producer.serves_blocks):
                    continue
                g.add_edge(consumer.lot_id, producer.lot_id,
                           item_code=child_item,
                           min_aging_min=min_a,
                           max_aging_min=max_a,
                           effective_gap_min=effective_gap,
                           transfer_time_min=transfer_min)

    return LotDagResult(graph=g)
