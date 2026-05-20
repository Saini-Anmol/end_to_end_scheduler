"""lot_id construction per L23.

    lot_id = {safe_item_code}__{op_seq}__{lot_seq:04d}

`safe_item_code` is the item code with whitespace, '-', '/' and '°' replaced
to make the id filesystem-safe and the underscore separator unambiguous.

Locked example from CLAUDE.md L23:
    'EHT1000 -480MM/90°' → 'EHT1000_480MM_90deg'
"""
from __future__ import annotations


_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (" ", ""),
    ("-", "_"),
    ("/", "_"),
    ("°", "deg"),
)


def safe_item_code(item: str) -> str:
    """Transliterate a raw item code into a lot-id-safe form."""
    out = item
    for bad, good in _REPLACEMENTS:
        out = out.replace(bad, good)
    return out


def make_lot_id(item: str, op_seq: int, lot_seq: int) -> str:
    """Build a fully-formed lot_id (L23)."""
    return f"{safe_item_code(item)}__{int(op_seq)}__{int(lot_seq):04d}"
