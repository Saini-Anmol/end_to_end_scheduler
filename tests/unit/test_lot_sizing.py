"""Tests for V1.routes.lot_sizing (Module 5).

Includes Section 17 Fixture 5 — the MPQ + tight-aging HALT — using a
synthetic minimal demand+routing+aging+MPQ slice. The other tests run on
the real pilot inputs.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

from V1.config.halt_codes import HaltCode, HaltError
from V1.config.settings import Settings
from V1.models.demand import BlockDemand, DemandResult, ItemDemand
from V1.models.lot import LotsResult
from V1.routes import audit, demand_explosion, lot_sizing
from V1.utilities.bom_walker import build_graph
from V1.utilities.unit_conversion import NormalisedResult, normalise


# --- shared real-data fixtures ---------------------------------------------

@pytest.fixture(scope="module")
def norm(input_dir: Path, settings: Settings) -> NormalisedResult:
    return normalise(audit.run(input_dir, settings), settings)


@pytest.fixture(scope="module")
def bom(norm, settings: Settings):
    return build_graph(norm.audit.bom_df, norm.aging_df,
                       norm.audit.itemtype_df, settings)


@pytest.fixture(scope="module")
def demand(norm, bom, settings: Settings) -> DemandResult:
    return demand_explosion.run(norm, bom, settings)


@pytest.fixture(scope="module")
def lots(norm, demand, settings: Settings) -> LotsResult:
    return lot_sizing.run(norm, demand, settings)


# --- shape -----------------------------------------------------------------

class TestShape:
    def test_some_lots_produced(self, lots: LotsResult) -> None:
        assert len(lots.lots) > 0

    def test_each_pilot_component_has_lots(
        self, lots: LotsResult, settings: Settings
    ) -> None:
        for comp in settings.green_tyre_components:
            assert lots.by_item(comp), f"No lots for component {comp!r}"

    def test_lot_id_format_l23(self, lots: LotsResult) -> None:
        for lot in lots.lots:
            parts = lot.lot_id.split("__")
            assert len(parts) == 3
            assert parts[1] == str(lot.op_seq)
            assert len(parts[2]) == 4 and parts[2].isdigit()

    def test_lot_qty_positive(self, lots: LotsResult) -> None:
        for lot in lots.lots:
            assert lot.qty > 0

    def test_serves_blocks_chronological_within_lot(
        self, lots: LotsResult
    ) -> None:
        for lot in lots.lots:
            assert lot.serves_blocks == sorted(
                lot.serves_blocks, key=lambda b: int(b[1:])
            )

    def test_lot_seq_starts_at_1_per_item(self, lots: LotsResult) -> None:
        from collections import defaultdict
        seen: defaultdict[str, list[int]] = defaultdict(list)
        for lot in lots.lots:
            seq = int(lot.lot_id.rsplit("__", 1)[-1])
            seen[lot.item_code].append(seq)
        for item, seqs in seen.items():
            assert sorted(seqs) == list(range(1, len(seqs) + 1)), (
                f"{item!r} seqs not contiguous: {sorted(seqs)}"
            )

    def test_total_qty_matches_demand(
        self, lots: LotsResult, demand: DemandResult
    ) -> None:
        from collections import defaultdict
        per_item_lot_total: dict[str, float] = defaultdict(float)
        for lot in lots.lots:
            per_item_lot_total[lot.item_code] += lot.qty
        for item, lot_total in per_item_lot_total.items():
            demand_total = demand.item_demands[item].total_qty
            assert abs(lot_total - demand_total) < 1e-3, (
                f"{item!r}: lot_total={lot_total}, demand_total={demand_total}"
            )


# --- MPQ enforcement -------------------------------------------------------

class TestMPQ:
    def test_b460_lots_within_mpq(
        self, lots: LotsResult, norm: NormalisedResult
    ) -> None:
        """B460 is MASTER COMPOUND (210–840 KG)."""
        b460_lots = lots.by_item("B460")
        for lot in b460_lots:
            assert 210.0 <= lot.qty <= 840.0, (
                f"B460 lot {lot.lot_id} qty={lot.qty} outside [210, 840]"
            )

    def test_cpj1218_162_mm_within_mpq_in_mm(
        self, lots: LotsResult
    ) -> None:
        """Rubberized Steel Belt MPQ 20–250 NOS; 1 NOS = 1860 MM here.
        So lot qty in MM should be in [20×1860, 250×1860] = [37,200, 465,000].
        """
        for lot in lots.by_item("CPJ1218-162MM/29°"):
            assert 37_200.0 <= lot.qty <= 465_000.0


# --- aging-span constraint -------------------------------------------------

class TestAgingSpan:
    def test_lot_curing_span_within_aging_window(
        self, lots: LotsResult, demand: DemandResult, norm: NormalisedResult
    ) -> None:
        """For every lot, latest_curing - earliest_curing ≤ aging_max - aging_min."""
        starts = {d.block_id: d.curing_start_min for d in demand.block_demands}
        aging_by_item: dict[str, tuple[float, float]] = {}
        for _, row in norm.aging_df.iterrows():
            if pd.notna(row["min_aging_min"]) and pd.notna(row["max_aging_min"]):
                aging_by_item[str(row["ItemCode"])] = (
                    float(row["min_aging_min"]), float(row["max_aging_min"])
                )
        for lot in lots.lots:
            if lot.item_code not in aging_by_item:
                continue
            mn, mx = aging_by_item[lot.item_code]
            span = mx - mn
            actual_span = (starts[lot.latest_block_id]
                           - starts[lot.earliest_block_id])
            assert actual_span <= span, (
                f"{lot.lot_id} span={actual_span} > aging_span={span}"
            )


# --- determinism -----------------------------------------------------------

class TestDeterminism:
    def test_two_runs_byte_identical_lot_ids(
        self, norm, demand, settings: Settings
    ) -> None:
        a = lot_sizing.run(norm, demand, settings)
        b = lot_sizing.run(norm, demand, settings)
        assert [l.lot_id for l in a.lots] == [l.lot_id for l in b.lots]
        for la, lb in zip(a.lots, b.lots):
            assert la.qty == lb.qty
            assert la.serves_blocks == lb.serves_blocks


# --- Section 17 Fixture 5 — MPQ + tight aging HALT -------------------------

def _make_synthetic_demand(
    item: str,
    uom: str,
    block_specs: list[tuple[str, float, int]],  # (bid, qty, curing_start_min)
    bom_output_qty: float | None = None,
    bom_output_uom: str | None = None,
    item_type: str = "TestType",
) -> DemandResult:
    block_demands: list[BlockDemand] = []
    qty_by_block: dict[str, float] = {}
    for bid, q, start in block_specs:
        block_demands.append(BlockDemand(
            block_id=bid, item_code=item, qty=q, uom=uom,
            curing_start_min=start, curing_qty_tyres=1,
        ))
        qty_by_block[bid] = q
    item_demand = ItemDemand(
        item_code=item, item_type=item_type, uom=uom,
        bom_output_qty=bom_output_qty, bom_output_uom=bom_output_uom,
        total_qty=sum(qty_by_block.values()),
        serves_blocks=[s[0] for s in block_specs],
        qty_by_block=qty_by_block,
    )
    return DemandResult(block_demands=block_demands,
                        item_demands={item: item_demand})


def _make_synthetic_norm(
    item: str, op_seq: int, item_type: str,
    min_aging_min: int, max_aging_min: int,
    mpq_min: float, mpq_max: float | None, mpq_uom: str,
    norm_real: NormalisedResult,
) -> NormalisedResult:
    """Build a NormalisedResult with synthetic routing/aging/MPQ for one item."""
    routing = pd.DataFrame([{
        "routed_product": item, "operation_seq": op_seq,
        "operation_name": "TEST", "department": "TEST",
        "machines": "MX1", "proc_time": 60, "proc_time_UOM": "SEC/BATCH",
        "batch_size": 100, "batch_UNIT": "KG", "transfer_time_min": None,
        "is_primary": 1.0, "efficiency": 0.95,
        "machines_list": ["MX1"], "eligible_machine_count": 1,
        "machines_normalised": "MX1", "proc_time_min": 1,
    }])
    aging = pd.DataFrame([{
        "ItemCode": item, "MinAging": min_aging_min, "MaxAging": max_aging_min,
        "MinAgingUnit": "Minutes", "MaxAgingUnit": "Minutes",
        "min_aging_min": min_aging_min, "max_aging_min": max_aging_min,
    }])
    itemtype = pd.DataFrame([{"ItemCode": item, "ItemType": item_type}])
    mpq = pd.DataFrame([{
        "Item Type": item_type, "Minimum Run Qty": mpq_min,
        "Maximum Run Qty": mpq_max, "UOM": mpq_uom,
    }])
    # Reuse real audit shell; replace the four frames.
    real_audit = norm_real.audit
    # Synthesize curing — we don't actually consult it from lot_sizing; pass empty.
    curing = norm_real.curing_df.iloc[:0].copy()
    new_audit = replace(real_audit, curing_df=curing, routing_cleaned_df=routing,
                        aging_df=aging, itemtype_df=itemtype, mpq_df=mpq)
    return NormalisedResult(audit=new_audit, t0=norm_real.t0,
                            aging_df=aging, routing_df=routing,
                            curing_df=curing)


class TestFixture5MPQTightAgingHALT:
    """Section 17 Fixture 5 — HALT on single-block < MPQ_Min + aging-blocked agg."""

    def test_halts_on_tight_aging_and_undersize_block(
        self, settings: Settings, norm: NormalisedResult
    ) -> None:
        # Single demand block, qty below MPQ_Min, with second block beyond
        # aging-MAX so aggregation is impossible.
        # aging window: min=60, max=120 → span = 60 min.
        # Blocks: b00 @ minute 0, b01 @ minute 5000 (span 5000 >> 60).
        # Demand: 10 KG on b00 (< MPQ_Min=200), 10 KG on b01 (< MPQ_Min=200).
        demand = _make_synthetic_demand(
            item="X1", uom="KG",
            block_specs=[("b00", 10.0, 0), ("b01", 10.0, 5000)],
        )
        synth = _make_synthetic_norm(
            item="X1", op_seq=10, item_type="TestType",
            min_aging_min=60, max_aging_min=120,
            mpq_min=200, mpq_max=500, mpq_uom="KG",
            norm_real=norm,
        )
        with pytest.raises(HaltError) as exc:
            lot_sizing.run(synth, demand, settings)
        assert exc.value.code == HaltCode.LOT_SIZING_TIGHT_AGING
        # Must name BOTH the block and the compound:
        msg = str(exc.value)
        assert "X1" in msg
        assert ("b00" in msg or "b01" in msg)

    def test_no_halt_when_aging_allows_aggregation(
        self, settings: Settings, norm: NormalisedResult
    ) -> None:
        """Same low qty, but blocks close enough that aging-span allows merge."""
        demand = _make_synthetic_demand(
            item="X1", uom="KG",
            block_specs=[
                ("b00", 110.0, 0),
                ("b01", 110.0, 30),    # within span (max−min = 60)
            ],
        )
        synth = _make_synthetic_norm(
            item="X1", op_seq=10, item_type="TestType",
            min_aging_min=60, max_aging_min=120,
            mpq_min=200, mpq_max=500, mpq_uom="KG",
            norm_real=norm,
        )
        result = lot_sizing.run(synth, demand, settings)
        assert len(result.lots) == 1
        assert result.lots[0].qty == pytest.approx(220.0)
        assert result.lots[0].serves_blocks == ["b00", "b01"]

    def test_equal_split_when_block_exceeds_mpq_max(
        self, settings: Settings, norm: NormalisedResult
    ) -> None:
        """Single block 1200 KG with MPQ_Max=500 → 3 sub-lots of 400 KG each."""
        demand = _make_synthetic_demand(
            item="X1", uom="KG",
            block_specs=[("b00", 1200.0, 0)],
        )
        synth = _make_synthetic_norm(
            item="X1", op_seq=10, item_type="TestType",
            min_aging_min=60, max_aging_min=120,
            mpq_min=100, mpq_max=500, mpq_uom="KG",
            norm_real=norm,
        )
        result = lot_sizing.run(synth, demand, settings)
        assert len(result.lots) == 3
        for lot in result.lots:
            assert lot.qty == pytest.approx(400.0)
            assert lot.serves_blocks == ["b00"]
