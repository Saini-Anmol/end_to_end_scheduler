"""Lot dataclass.

`lot_id` format (L23): {safe_item_code}__{op_seq}__{lot_seq:04d}.
`machine_id` is always a string (assigned by the forward scheduler — not by
this module). `qty` is in the lot's UOM, which equals the BOM-natural UOM
for the item; MPQ thresholds are converted to this UOM at sizing time.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Lot:
    """A single production lot, sized and assigned a stable lot_id.

    Forward scheduler will later attach machine_id, start_min, end_min.

    `bom_output_qty` / `bom_output_uom` carry the item's BOM Output rate
    (per-tyre production unit, e.g. 1350 MM per 1 NOS bead). Time calculation
    needs this for routing rows where batch_UNIT differs from lot.uom — e.g.
    bead Fillering, lot in MM, batch in NOS.
    """
    lot_id: str
    item_code: str          # readable original (preserves spaces/°)
    op_seq: int
    item_type: str
    qty: float              # in `uom`
    uom: str                # lot's natural UOM (BOM Output unit for the item)
    serves_blocks: list[str]    # chronologically sorted block_ids
    earliest_block_id: str
    latest_block_id: str
    bom_output_qty: float | None = None
    bom_output_uom: str | None = None
    # Per-block qty share — used by diagnostics for traceability.
    qty_by_block: dict[str, float] = field(default_factory=dict)


@dataclass
class LotsResult:
    """Output of Module 5 — lot_sizing.

    `lots` are sorted by lot_id (stable across re-runs).

    `warnings` carries soft messages (e.g. multi-block lot under MPQ_Min after
    aging-forced split — which CLAUDE.md §8.C does not classify as HALT).
    """
    lots: list[Lot]
    warnings: list[str] = field(default_factory=list)

    def by_item(self, item_code: str) -> list[Lot]:
        return [lot for lot in self.lots if lot.item_code == item_code]

    def lot_ids(self) -> list[str]:
        return [lot.lot_id for lot in self.lots]
