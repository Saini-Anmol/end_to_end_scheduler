"""Tests for V1.setups.t0_compute — auto-anchor t0 from BOM critical path."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from V1.config.settings import Settings
from V1.routes import audit
from V1.setups.t0_compute import compute_auto_t0


class TestAutoT0:
    @pytest.fixture(scope="class")
    def auto(self, input_dir: Path, settings: Settings):
        au = audit.run(input_dir, settings)
        return compute_auto_t0(au, settings)

    def test_returns_tuple(self, auto) -> None:
        t0, cp, path = auto
        assert cp > 0
        assert isinstance(path, list) and path

    def test_t0_strictly_before_first_curing(
        self, auto, input_dir: Path, settings: Settings
    ) -> None:
        au = audit.run(input_dir, settings)
        first_curing = au.curing_df.iloc[0]["StartTime"]
        t0, _, _ = auto
        assert t0 < first_curing.to_pydatetime()

    def test_gap_equals_critical_path_plus_buffer(
        self, auto, input_dir: Path, settings: Settings
    ) -> None:
        au = audit.run(input_dir, settings)
        first_curing = au.curing_df.iloc[0]["StartTime"].to_pydatetime()
        t0, cp, _ = auto
        gap = first_curing - t0
        # gap == cp + 60 min buffer (default), modulo the second/microsecond drop.
        expected = timedelta(minutes=cp + settings.t0_safety_buffer_min)
        assert abs(gap - expected) < timedelta(seconds=60)

    def test_critical_path_runs_from_leaf_to_sku(
        self, auto, settings: Settings
    ) -> None:
        """`path` is the predecessor chain — leaf at index 0, SKU at the end."""
        _, _, path = auto
        assert path[-1] == settings.sku_code
        # Penultimate is the Green Tyre (always directly consumed by curing).
        assert path[-2] == settings.green_tyre_code

    def test_t0_makes_sense_for_pilot(self, auto, input_dir, settings) -> None:
        """For the pilot's chain (≈ 1000 min) + 60 min buffer, t0 should
        land in mid-May, not in early May (the old hard-coded default)."""
        t0, _, _ = auto
        assert t0.month == 5
        # The old default was May 1; auto-t0 should be much closer to first
        # curing (May 17). At least 3 days later than the dummy default.
        assert t0 > settings.t0_default + timedelta(days=3)


class TestSettings:
    def test_t0_auto_enabled_by_default(self, settings: Settings) -> None:
        assert settings.t0_auto is True

    def test_t0_safety_buffer_positive(self, settings: Settings) -> None:
        assert settings.t0_safety_buffer_min > 0
