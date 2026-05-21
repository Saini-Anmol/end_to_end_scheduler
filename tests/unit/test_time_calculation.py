"""Tests for V1.routes.time_calculation (Module 8)."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from V1.config.settings import Settings
from V1.models.lot import LotsResult
from V1.routes import audit, demand_explosion, lot_sizing, time_calculation
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
def lots(norm, bom, settings: Settings) -> LotsResult:
    demand = demand_explosion.run(norm, bom, settings)
    return lot_sizing.run(norm, demand, settings)


@pytest.fixture(scope="module")
def durations(lots, norm, settings):
    return time_calculation.run(lots, norm, settings)


class TestShape:
    def test_durations_for_every_routable_lot_with_proc_time(
        self, lots: LotsResult, durations, norm
    ) -> None:
        """Lots for items with null proc_time (BD-12843443-4 Fillering, a known
        HALT in audit) are intentionally skipped — see Section 8.D."""
        null_proc_items = set(
            norm.routing_df[
                norm.routing_df["proc_time"].isna()
            ]["routed_product"].astype(str)
        )
        for lot in lots.lots:
            if lot.item_code in null_proc_items:
                assert lot.lot_id not in durations.durations
                continue
            assert lot.lot_id in durations.durations
            d = durations.for_lot(lot.lot_id)
            assert len(d) > 0

    def test_durations_are_non_negative_ints(self, durations) -> None:
        """Durations are integer minutes ≥ 0. Zero-tyre placeholder GT lots
        (b00 11-min pre-shift slot) carry duration 0."""
        for per_machine in durations.durations.values():
            for dur in per_machine.values():
                assert isinstance(dur, int)
                assert dur >= 0


class TestSecPerBatch:
    def test_mb349_master_mixing(
        self, lots: LotsResult, durations, settings: Settings
    ) -> None:
        """MB349 op 10: proc_time=171 SEC/BATCH, batch_size=205 KG.
        Per batch = ceil(171/60) = 3 min nominal.
        For a 500 KG lot: n_batches = ceil(500/205) = 3 → nominal = 9 min.
        effective = ceil(9/0.95) = 10 min."""
        mb349_lots = lots.by_item("MB349")
        # Pick a lot with qty between 500 and 600 to verify the math
        candidate = next((l for l in mb349_lots if 500 <= l.qty <= 600), None)
        if candidate is None:
            # Real data may not have this size — fall back to recomputing for
            # whatever the first MB349 lot turned out to be.
            candidate = mb349_lots[0]
        d = next(iter(durations.for_lot(candidate.lot_id).values()))
        n_batches = max(1, math.ceil(candidate.qty / 205.0))
        nominal = n_batches * math.ceil(171 / 60)
        effective = math.ceil(nominal / 0.95)
        assert d == effective


class TestMperMin:
    def test_eht1000_calandering(self, lots: LotsResult, durations) -> None:
        """EHT1000 op 40: proc_time=600 SEC/BATCH, batch_size=400 M.
        Each lot's qty is in MM; converts to MTR by /1000, divides by batch_size.
        n_batches = ceil(qty_mtr / 400). per_batch = ceil(600/60) = 10 min.
        """
        eht_lots = lots.by_item("EHT1000")
        if not eht_lots:
            pytest.skip("No EHT1000 lots in this run")
        lot = eht_lots[0]
        d = next(iter(durations.for_lot(lot.lot_id).values()))
        qty_mtr = lot.qty / 1000.0
        n_batches = max(1, math.ceil(qty_mtr / 400.0))
        nominal = n_batches * math.ceil(600 / 60)
        effective = math.ceil(nominal / 0.95)
        assert d == effective

    def test_ply_cutter_continuous_mm(self, lots: LotsResult, durations) -> None:
        """EHT1000 -480MM/90° op 50: proc_time=20 M/MIN. Continuous.
        nominal = ceil(qty_mtr / 20). effective = ceil(nominal/0.95)."""
        cut_lots = lots.by_item("EHT1000 -480MM/90°")
        if not cut_lots:
            pytest.skip("No EHT1000 -480 lots")
        lot = cut_lots[0]
        d = next(iter(durations.for_lot(lot.lot_id).values()))
        qty_mtr = lot.qty / 1000.0
        nominal = math.ceil(qty_mtr / 20.0)
        effective = math.ceil(nominal / 0.95)
        assert d == effective


class TestEfficiency:
    def test_all_positive_qty_durations_at_least_one(self, durations, lots) -> None:
        """Effective is always ≥ nominal (efficiency < 1 lengthens duration).
        Zero-qty placeholder lots get duration 0 and are excluded."""
        nonzero_lots = {l.lot_id for l in lots.lots if l.qty > 0}
        for lot_id, per_machine in durations.durations.items():
            if lot_id not in nonzero_lots:
                continue
            for dur in per_machine.values():
                assert dur >= 1


class TestDeterminism:
    def test_repeated_runs_identical(self, lots, norm, settings) -> None:
        a = time_calculation.run(lots, norm, settings)
        b = time_calculation.run(lots, norm, settings)
        assert a.durations == b.durations
