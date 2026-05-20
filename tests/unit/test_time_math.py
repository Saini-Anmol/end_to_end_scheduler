"""Tests for V1.utilities.time_math (L20 minute domain)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from V1.utilities.time_math import (
    apply_efficiency,
    ceil_div,
    from_minute,
    to_minute,
)


T0 = datetime(2026, 5, 1, 7, 0)


class TestToMinute:
    def test_t0_is_minute_zero(self) -> None:
        assert to_minute(T0, T0) == 0

    def test_one_minute_later(self) -> None:
        assert to_minute(T0 + timedelta(minutes=1), T0) == 1

    def test_one_hour_later(self) -> None:
        assert to_minute(T0 + timedelta(hours=1), T0) == 60

    def test_one_day_later(self) -> None:
        assert to_minute(T0 + timedelta(days=1), T0) == 1440

    def test_sub_minute_drops(self) -> None:
        # 30s past t0 → still minute 0
        assert to_minute(T0 + timedelta(seconds=30), T0) == 0

    def test_negative_before_t0(self) -> None:
        assert to_minute(T0 - timedelta(minutes=5), T0) == -5

    def test_first_pilot_curing(self) -> None:
        """t0=2026-05-01 07:00; first pilot curing = 2026-05-17 07:00.
        Delta = 16 days = 23040 min."""
        first = datetime(2026, 5, 17, 7, 0)
        assert to_minute(first, T0) == 16 * 1440


class TestFromMinute:
    def test_zero_is_t0(self) -> None:
        assert from_minute(0, T0) == T0

    def test_roundtrip(self) -> None:
        t = datetime(2026, 5, 17, 7, 0)
        assert from_minute(to_minute(t, T0), T0) == t


class TestApplyEfficiency:
    def test_750_at_95_percent(self) -> None:
        """750 nominal / 0.95 = 789.47 → ceil = 790."""
        assert apply_efficiency(750, 0.95) == 790

    def test_60_at_95_percent(self) -> None:
        """60 / 0.95 = 63.15 → 64."""
        assert apply_efficiency(60, 0.95) == 64

    def test_exact_division_no_round(self) -> None:
        """100 / 1.0 = 100."""
        assert apply_efficiency(100, 1.0) == 100

    def test_ceil_not_round(self) -> None:
        """1 / 2 = 0.5 → ceil(0.5) = 1, not 0."""
        assert apply_efficiency(1, 2.0) == 1

    def test_invalid_factor(self) -> None:
        with pytest.raises(ValueError):
            apply_efficiency(100, 0)
        with pytest.raises(ValueError):
            apply_efficiency(100, -0.5)


class TestCeilDiv:
    def test_basic(self) -> None:
        assert ceil_div(60, 60) == 1
        assert ceil_div(61, 60) == 2
        assert ceil_div(750, 60) == 13  # 12.5 → 13
        assert ceil_div(0, 60) == 0

    def test_zero_denom(self) -> None:
        with pytest.raises(ZeroDivisionError):
            ceil_div(1, 0)
