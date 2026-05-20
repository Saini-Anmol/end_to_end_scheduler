"""Tests for V1.routes.demand_explosion (Module 4)."""
from __future__ import annotations

from pathlib import Path

import pytest

from V1.config.settings import Settings
from V1.models.demand import DemandResult
from V1.routes import audit, demand_explosion
from V1.utilities.bom_walker import build_graph
from V1.utilities.unit_conversion import normalise


@pytest.fixture(scope="module")
def norm(input_dir: Path, settings: Settings):
    return normalise(audit.run(input_dir, settings), settings)


@pytest.fixture(scope="module")
def bom(norm, settings: Settings):
    return build_graph(norm.audit.bom_df, norm.aging_df,
                       norm.audit.itemtype_df, settings)


@pytest.fixture(scope="module")
def demand(norm, bom, settings: Settings) -> DemandResult:
    return demand_explosion.run(norm, bom, settings)


# --- shape & coverage ------------------------------------------------------

class TestShape:
    def test_41_demand_blocks_one_is_zero_qty_skipped(
        self, demand: DemandResult
    ) -> None:
        """42 pilot curing rows; b00 is a 0-tyre placeholder — skipped."""
        block_ids = {d.block_id for d in demand.block_demands}
        assert len(block_ids) == 41
        assert "b00" not in block_ids
        assert block_ids == {f"b{i:02d}" for i in range(1, 42)}

    def test_each_block_has_sku_demand_and_is_positive(
        self, demand: DemandResult, settings: Settings
    ) -> None:
        sku_rows = [d for d in demand.block_demands
                    if d.item_code == settings.sku_code]
        assert len(sku_rows) == 41
        for r in sku_rows:
            assert r.qty > 0
            assert r.uom == "NOS"

    def test_sku_demand_sums_to_2620_tyres(
        self, demand: DemandResult, settings: Settings
    ) -> None:
        """Total pilot demand per CLAUDE.md = 2620 tyres."""
        total = sum(d.qty for d in demand.block_demands
                    if d.item_code == settings.sku_code)
        assert int(total) == 2620

    def test_each_block_has_all_8_components(self, demand: DemandResult,
                                             settings: Settings) -> None:
        for bid in {d.block_id for d in demand.block_demands}:
            items_in_block = {d.item_code for d in demand.block_demands
                              if d.block_id == bid}
            for comp in settings.green_tyre_components:
                assert comp in items_in_block, (
                    f"block {bid} missing component {comp}"
                )

    def test_capstrip_excluded_l12(self, demand: DemandResult,
                                   settings: Settings) -> None:
        for d in demand.block_demands:
            assert d.item_code not in settings.capstrip_items, (
                f"capstrip item leaked into demand: {d.item_code}"
            )


# --- per-tyre arithmetic ---------------------------------------------------

class TestArithmetic:
    def test_sku_demand_matches_curing_qty(self, demand: DemandResult,
                                           settings: Settings, norm) -> None:
        for d in demand.block_demands:
            if d.item_code != settings.sku_code:
                continue
            assert d.qty == d.curing_qty_tyres

    def test_gt_equals_sku_count(self, demand: DemandResult,
                                 settings: Settings) -> None:
        for d in demand.block_demands:
            if d.item_code != settings.green_tyre_code:
                continue
            sku_d = next(x for x in demand.block_demands
                         if x.block_id == d.block_id
                         and x.item_code == settings.sku_code)
            assert d.qty == sku_d.qty

    def test_cpj1218_162_per_tyre_1860mm(self, demand: DemandResult) -> None:
        """BOM row 1 says GT→CPJ1218-162MM/29° = 1860 MM per 1 NOS GT."""
        rows = [d for d in demand.block_demands
                if d.item_code == "CPJ1218-162MM/29°"]
        assert len(rows) == 41  # excludes b00 zero-qty
        for r in rows:
            assert r.uom == "MM"
            expected = r.curing_qty_tyres * 1860.0
            assert abs(r.qty - expected) < 1e-6

    def test_b460_per_tyre_kg(self, demand: DemandResult) -> None:
        """B460 accumulates via BOTH CPJ1218 branches (162MM and 154MM-1)."""
        rows = [d for d in demand.block_demands if d.item_code == "B460"]
        assert len(rows) == 41
        for r in rows:
            assert r.uom == "KG"
            assert r.qty > 0


# --- aggregation -----------------------------------------------------------

class TestAggregation:
    def test_per_item_total_matches_block_sum(self, demand: DemandResult) -> None:
        for item, agg in demand.item_demands.items():
            block_sum = sum(
                d.qty for d in demand.block_demands if d.item_code == item
            )
            assert abs(agg.total_qty - block_sum) < 1e-6

    def test_serves_blocks_sorted_chronologically(
        self, demand: DemandResult
    ) -> None:
        for agg in demand.item_demands.values():
            assert agg.serves_blocks == sorted(
                agg.serves_blocks, key=lambda b: int(b[1:])
            )

    def test_qty_by_block_keys_match_serves_blocks(
        self, demand: DemandResult
    ) -> None:
        for agg in demand.item_demands.values():
            assert set(agg.qty_by_block.keys()) == set(agg.serves_blocks)

    def test_item_type_populated_for_in_scope(
        self, demand: DemandResult, settings: Settings
    ) -> None:
        for item in settings.green_tyre_components:
            assert item in demand.item_demands
            assert demand.item_demands[item].item_type is not None

    def test_bom_output_qty_and_uom_attached(
        self, demand: DemandResult
    ) -> None:
        # CPJ1218-162MM/29° has output_qty=1860 MM per BOM.
        d = demand.item_demands["CPJ1218-162MM/29°"]
        assert d.bom_output_qty == 1860.0
        assert d.bom_output_uom == "MM"


# --- determinism -----------------------------------------------------------

class TestDeterminism:
    def test_block_demands_sorted(self, demand: DemandResult) -> None:
        keys = [(d.block_id, d.item_code) for d in demand.block_demands]
        assert keys == sorted(keys)

    def test_repeated_runs_byte_identical(self, norm, bom,
                                          settings: Settings) -> None:
        a = demand_explosion.run(norm, bom, settings)
        b = demand_explosion.run(norm, bom, settings)
        keys_a = [(d.block_id, d.item_code, round(d.qty, 6)) for d in a.block_demands]
        keys_b = [(d.block_id, d.item_code, round(d.qty, 6)) for d in b.block_demands]
        assert keys_a == keys_b
        assert set(a.item_demands.keys()) == set(b.item_demands.keys())
