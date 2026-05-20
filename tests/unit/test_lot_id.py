"""Tests for V1.utilities.lot_id (L23)."""
from __future__ import annotations

from V1.utilities.lot_id import make_lot_id, safe_item_code


class TestSafeItemCode:
    def test_locked_example_from_l23(self) -> None:
        """L23 — 'EHT1000 -480MM/90°' → 'EHT1000_480MM_90deg'."""
        assert safe_item_code("EHT1000 -480MM/90°") == "EHT1000_480MM_90deg"

    def test_simple_alphanumeric_unchanged(self) -> None:
        assert safe_item_code("B460") == "B460"
        assert safe_item_code("MB230") == "MB230"

    def test_dashes_become_underscores(self) -> None:
        assert safe_item_code("BD-12843443-4") == "BD_12843443_4"

    def test_pilot_sku_unchanged(self) -> None:
        # Pilot SKU has no special chars.
        assert safe_item_code("1325220516095HTMX0") == "1325220516095HTMX0"

    def test_cpj1218_162_degree(self) -> None:
        assert safe_item_code("CPJ1218-162MM/29°") == "CPJ1218_162MM_29deg"

    def test_idempotent(self) -> None:
        once = safe_item_code("EHT1000 -480MM/90°")
        assert safe_item_code(once) == once


class TestMakeLotId:
    def test_format(self) -> None:
        assert make_lot_id("B460", 40, 1) == "B460__40__0001"

    def test_lot_seq_zero_padded_4_digits(self) -> None:
        assert make_lot_id("B460", 40, 12).endswith("__0012")
        assert make_lot_id("B460", 40, 1234).endswith("__1234")

    def test_combined_with_safe_item_code(self) -> None:
        assert (make_lot_id("EHT1000 -480MM/90°", 50, 7)
                == "EHT1000_480MM_90deg__50__0007")
