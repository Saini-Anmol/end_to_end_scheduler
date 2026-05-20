"""Route 2 — demand_explosion (Section 10 #2, approach-flow steps 8-9).

For each of the 42 pilot curing rows, walks the BOM downward from the SKU
and computes per-edge demand quantities in each consumer's natural UOM.
Then aggregates per item across blocks, preserving the chronologically-sorted
`serves_blocks` list and the per-block qty mapping.

Capstrip subtree is skipped per L12 (the BOM graph's `exclude_capstrip=True`
default handles this). Work-Away items per L13 still appear in the demand
tree (downstream lot_sizing will skip them — no routing row means no lot).

Propagation rule per BOM edge (parent → child):
    child_qty = parent_qty * (edge.qty / edge.output_qty)

This holds because each BOM row is a recipe: "to produce `output_qty` of
Output, consume `qty` of input code". The output unit and the child's
natural unit always agree (verified by audit).

Determinism: every traversal sorts by item code; topological order is
lexicographical.
"""
from __future__ import annotations

import networkx as nx
import pandas as pd

from V1.config.settings import Settings
from V1.models.demand import BlockDemand, DemandResult, ItemDemand
from V1.utilities.bom_walker import BomGraph
from V1.utilities.unit_conversion import NormalisedResult


def _block_id(idx: int) -> str:
    """Chronological block ID — pilot has 42 blocks, so 2 digits is enough."""
    return f"b{idx:02d}"


def _itemtype_lookup(itemtype_df: pd.DataFrame) -> dict[str, str]:
    return {
        str(r["ItemCode"]): str(r["ItemType"])
        for _, r in itemtype_df.iterrows()
        if pd.notna(r.get("ItemType"))
    }


def explode_block(
    block_id: str,
    sku_qty: int,
    curing_start_min: int,
    bom: BomGraph,
    settings: Settings,
) -> dict[str, tuple[float, str]]:
    """Propagate `sku_qty` SKU demand down the BOM to every reachable item.

    Returns a dict `item_code → (qty, uom)` where qty is in the item's
    natural UOM. Capstrip subtree skipped per L12.
    """
    g = bom._scoped_subgraph()  # in-scope (no capstrip)
    sku = settings.sku_code
    if sku not in g:
        raise KeyError(f"SKU {sku!r} not in BOM graph")

    # Topological order (lexicographical), parents-first.
    topo = list(nx.lexicographical_topological_sort(g))
    if topo[0] != sku:
        # Defensive: SKU should be the unique source node.
        if g.in_degree(sku) != 0:
            raise ValueError(f"SKU {sku!r} is not a source node")

    qty_by_item: dict[str, tuple[float, str]] = {
        sku: (float(sku_qty), str(g.nodes[sku].get("bom_output_uom") or "NOS"))
    }

    for parent in topo:
        if parent not in qty_by_item:
            continue
        parent_qty, _ = qty_by_item[parent]
        for child in sorted(g.successors(parent)):
            edge = g[parent][child]
            edge_in_qty = edge["qty"]
            edge_out_qty = edge["output_qty"]
            child_uom = edge["uom"]
            if edge_in_qty is None or edge_out_qty is None or child_uom is None:
                raise ValueError(
                    f"BOM edge {parent!r} → {child!r} missing qty/output_qty/uom"
                )
            child_qty = parent_qty * (edge_in_qty / edge_out_qty)
            if child in qty_by_item:
                existing_qty, existing_uom = qty_by_item[child]
                if existing_uom != child_uom:
                    raise ValueError(
                        f"UOM mismatch for {child!r}: {existing_uom!r} vs {child_uom!r}"
                    )
                qty_by_item[child] = (existing_qty + child_qty, child_uom)
            else:
                qty_by_item[child] = (child_qty, child_uom)
    return qty_by_item


def run(
    norm: NormalisedResult, bom: BomGraph, settings: Settings
) -> DemandResult:
    """Build the per-block + per-item demand tables for the pilot."""
    curing = norm.curing_df.reset_index(drop=True)
    itype_by_item = _itemtype_lookup(norm.audit.itemtype_df)

    block_demands: list[BlockDemand] = []
    # Aggregator: item_code → (total_qty, uom, serves_blocks_list, qty_by_block_dict)
    agg: dict[str, dict] = {}

    for idx, row in curing.iterrows():
        bid = _block_id(int(idx))
        sku_qty = int(row["Qty"])
        cur_start = int(row["start_min"])
        # Zero-tyre placeholder blocks (e.g. the pre-shift prep slot at b00)
        # generate no demand — skip outright. They remain visible in
        # norm.curing_df for downstream diagnostics.
        if sku_qty == 0:
            continue

        per_item = explode_block(bid, sku_qty, cur_start, bom, settings)
        for item, (qty, uom) in per_item.items():
            block_demands.append(BlockDemand(
                block_id=bid,
                item_code=item,
                qty=qty,
                uom=uom,
                curing_start_min=cur_start,
                curing_qty_tyres=sku_qty,
            ))
            entry = agg.setdefault(item, {
                "uom": uom,
                "total": 0.0,
                "blocks": [],
                "by_block": {},
            })
            if entry["uom"] != uom:
                raise ValueError(
                    f"UOM mismatch aggregating {item!r}: {entry['uom']!r} vs {uom!r}"
                )
            entry["total"] += qty
            entry["blocks"].append(bid)
            entry["by_block"][bid] = qty

    item_demands: dict[str, ItemDemand] = {}
    for item, e in agg.items():
        node = bom.graph.nodes.get(item, {})
        item_demands[item] = ItemDemand(
            item_code=item,
            item_type=itype_by_item.get(item),
            uom=e["uom"],
            bom_output_qty=node.get("bom_output_qty"),
            bom_output_uom=node.get("bom_output_uom"),
            total_qty=e["total"],
            serves_blocks=list(e["blocks"]),  # already chronological by iteration
            qty_by_block=dict(e["by_block"]),
        )

    # Stable ordering of block_demands: by (block_id, item_code).
    block_demands.sort(key=lambda d: (d.block_id, d.item_code))
    return DemandResult(block_demands=block_demands, item_demands=item_demands)
