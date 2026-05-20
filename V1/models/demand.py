"""Demand explosion records.

`block_id` is a stable, chronological identifier (`b00 .. b41` for the pilot's
42 curing rows). All qty values are in the item's BOM-natural UOM (= the
unit the item carries in its BOM Output row).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BlockDemand:
    """Demand for one item arising from one curing block."""
    block_id: str               # chronological, e.g. 'b00'
    item_code: str
    qty: float                  # in `uom`
    uom: str                    # BOM-natural UOM (output_uom of the item)
    # Pass-through info from the curing block — convenient for downstream.
    curing_start_min: int       # block start in integer minutes since t0
    curing_qty_tyres: int       # tyres in this block (Qty column)


@dataclass
class ItemDemand:
    """Aggregated demand across all blocks for one item."""
    item_code: str
    item_type: str | None       # from ItemType Master (may be None for the SKU)
    uom: str                    # BOM-natural UOM (constant across blocks)
    bom_output_qty: float | None    # rate per produced unit (per-tyre amount)
    bom_output_uom: str | None
    total_qty: float            # sum of qty across blocks
    serves_blocks: list[str] = field(default_factory=list)        # sorted chronologically
    qty_by_block: dict[str, float] = field(default_factory=dict)  # block_id → qty


@dataclass
class DemandResult:
    """Output of Module 4 — demand_explosion."""
    block_demands: list[BlockDemand]
    item_demands: dict[str, ItemDemand]  # keyed by item_code

    def items(self) -> list[str]:
        return sorted(self.item_demands.keys())
