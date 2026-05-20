"""Tests for V1.utilities.machine_parser.eligible_machines + index (Module 7)."""
from __future__ import annotations

from pathlib import Path

import pytest

from V1.config.settings import Settings
from V1.routes import audit
from V1.utilities.machine_parser import (
    build_eligibility_index,
    eligible_machines,
)
from V1.utilities.unit_conversion import normalise


@pytest.fixture(scope="module")
def routing(input_dir: Path, settings: Settings):
    norm = normalise(audit.run(input_dir, settings), settings)
    return norm.routing_df


class TestEligibleMachines:
    def test_returns_list_of_strings(self, routing) -> None:
        ms = eligible_machines(routing, "MB349", 10)
        assert isinstance(ms, list)
        for m in ms:
            assert isinstance(m, str)

    def test_mb349_mixer_pool(self, routing) -> None:
        # MB349 is mastered on the 5-machine mixer pool.
        ms = eligible_machines(routing, "MB349", 10)
        assert "0201" in ms
        assert "0202" in ms
        # L23 — leading zeros preserved
        assert all(m.startswith("0") for m in ms if m.startswith(tuple("01234")))

    def test_frc_calendering(self, routing) -> None:
        # EHT1000 calandering goes on the single FRC machine.
        assert eligible_machines(routing, "EHT1000", 40) == ["FRC"]

    def test_no_routing_raises(self, routing) -> None:
        with pytest.raises(KeyError):
            eligible_machines(routing, "NONEXISTENT_ITEM_XYZ", 99)

    def test_curing_pool_includes_pilot_press(
        self, routing, settings: Settings
    ) -> None:
        sku_ms = eligible_machines(routing, settings.sku_code, 80)
        # The pilot's curing press (14811) is one of dozens in this pool.
        assert settings.curing_press in sku_ms


class TestEligibilityIndex:
    def test_index_covers_every_routing_row(self, routing) -> None:
        idx = build_eligibility_index(routing)
        # One entry per (item, op_seq) in cleaned routing.
        assert len(idx) == len(routing)

    def test_index_keys_match_direct_lookup(self, routing) -> None:
        idx = build_eligibility_index(routing)
        for (item, op_seq), ms in idx.items():
            assert eligible_machines(routing, item, op_seq) == ms

    def test_index_machine_ids_are_strings(self, routing) -> None:
        idx = build_eligibility_index(routing)
        for ms in idx.values():
            for m in ms:
                assert isinstance(m, str)
