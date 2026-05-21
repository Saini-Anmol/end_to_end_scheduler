"""Tests for V1.routes.backward_feasibility (Module 6)."""
from __future__ import annotations

from pathlib import Path

import pytest

from V1.config.settings import Settings
from V1.models.feasibility import FeasibilityResult, LotFeasibility
from V1.models.lot import LotsResult
from V1.routes import audit, backward_feasibility, demand_explosion, lot_sizing
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
def demand(norm, bom, settings: Settings):
    return demand_explosion.run(norm, bom, settings)


@pytest.fixture(scope="module")
def lots(norm, demand, settings: Settings) -> LotsResult:
    return lot_sizing.run(norm, demand, settings)


@pytest.fixture(scope="module")
def feas(lots, demand, bom, norm) -> FeasibilityResult:
    return backward_feasibility.run(lots, demand, bom, norm)


class TestShape:
    def test_one_record_per_lot(self, feas: FeasibilityResult,
                                lots: LotsResult) -> None:
        assert len(feas.feasibilities) == len(lots.lots)
        ids = {f.lot_id for f in feas.feasibilities}
        assert ids == {l.lot_id for l in lots.lots}

    def test_chain_min_aging_non_negative(self, feas: FeasibilityResult) -> None:
        for f in feas.feasibilities:
            assert f.chain_min_aging_min >= 0


class TestDeadlines:
    def test_deadline_at_or_before_earliest_curing(
        self, feas: FeasibilityResult, lots: LotsResult, demand,
        norm,
    ) -> None:
        """latest_end_min == earliest_curing_start − chain_min_aging.
        For GT lots (one per curing row, including zero-qty b00) where
        chain_min_aging = 0, the deadline equals curing_start."""
        starts = {d.block_id: d.curing_start_min for d in demand.block_demands}
        for idx, row in norm.curing_df.reset_index(drop=True).iterrows():
            starts.setdefault(f"b{int(idx):02d}", int(row["start_min"]))
        lots_by_id = {l.lot_id: l for l in lots.lots}
        for f in feas.feasibilities:
            lot = lots_by_id[f.lot_id]
            earliest = min(starts[b] for b in lot.serves_blocks)
            assert f.latest_acceptable_end_min == earliest - f.chain_min_aging_min
            assert f.latest_acceptable_end_min <= earliest

    def test_gt_chain_equals_gt_aging_alone(
        self, feas: FeasibilityResult, norm, settings: Settings,
    ) -> None:
        """The Green Tyre is one step from Curing → chain equals GT's own min_aging."""
        gt_feas = [f for f in feas.feasibilities
                   if f.item_code == settings.green_tyre_code]
        assert gt_feas
        # All GT lots have the same chain value.
        chain_values = {f.chain_min_aging_min for f in gt_feas}
        assert len(chain_values) == 1
        # That value should equal GT's own min_aging_min.
        gt_aging = norm.aging_df[
            norm.aging_df["ItemCode"].astype(str) == settings.green_tyre_code
        ].iloc[0]["min_aging_min"]
        assert chain_values == {int(gt_aging)}

    def test_master_compound_chain_exceeds_component_chain(
        self, feas: FeasibilityResult, settings: Settings,
    ) -> None:
        """A deeper item (master compound) has a longer downstream chain than
        its parent component."""
        comp_feas = next(
            f for f in feas.feasibilities
            if f.item_code == "CPJ1218-162MM/29°"
        )
        # B460 is a master compound consumed deep in the CPJ1218 chain.
        b460_feas = next(f for f in feas.feasibilities if f.item_code == "B460")
        assert b460_feas.chain_min_aging_min >= comp_feas.chain_min_aging_min


class TestDeterminism:
    def test_repeated_runs_identical(self, lots, demand, bom, norm) -> None:
        a = backward_feasibility.run(lots, demand, bom, norm)
        b = backward_feasibility.run(lots, demand, bom, norm)
        assert [(f.lot_id, f.latest_acceptable_end_min,
                 f.chain_min_aging_min) for f in a.feasibilities] \
            == [(f.lot_id, f.latest_acceptable_end_min,
                 f.chain_min_aging_min) for f in b.feasibilities]
