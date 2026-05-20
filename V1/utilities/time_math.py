"""Integer-minute domain math (L20).

All scheduling math runs in integer minutes anchored at t0. Conversion
happens ONCE in unit_normalisation (datetime → minute) and ONCE in the
output writer (minute → datetime). Single ceil rounding direction throughout
(L20). No other module touches pandas.Timestamp arithmetic (L23).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta


def to_minute(t: datetime, t0: datetime) -> int:
    """Convert a wall-clock datetime to integer minutes since `t0`.

    Sub-minute precision is dropped via integer floor division (// 60). Both
    sides of every aging-window comparison use this same definition so the
    inclusive boundary (L22) holds at the minute granularity.
    """
    delta_s = (t - t0).total_seconds()
    return int(delta_s // 60)


def from_minute(m: int, t0: datetime) -> datetime:
    """Convert an integer-minute offset back to a wall-clock datetime.

    Inverse of `to_minute` up to the original sub-minute drop.
    """
    return t0 + timedelta(minutes=int(m))


def apply_efficiency(nominal_min: int, factor: float) -> int:
    """Apply L10/L20 efficiency: effective_min = ceil(nominal_min / factor).

    Single ceil rounding direction. `factor` must be > 0.
    """
    if factor <= 0:
        raise ValueError(f"efficiency factor must be > 0, got {factor!r}")
    return int(math.ceil(nominal_min / factor))


def ceil_div(numerator: float, denominator: float) -> int:
    """The one canonical ceil-division used across the codebase (L20, L23).

    Duplicating `ceil(x/60)` logic anywhere else is a defect — call this.
    """
    if denominator == 0:
        raise ZeroDivisionError(f"ceil_div by zero (numerator={numerator})")
    return int(math.ceil(numerator / denominator))
