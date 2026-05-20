"""Enumerations: FindingSeverity, AgingUnit, EventClass, ReservationState."""
from __future__ import annotations

from enum import Enum, IntEnum


class FindingSeverity(str, Enum):
    HALT = "HALT"
    WARN = "WARN"


class AgingUnit(str, Enum):
    DAYS = "Days"
    HOURS = "Hours"
    MINUTES = "Minutes"

    @classmethod
    def to_minutes(cls, value: float, unit: str) -> int:
        """Convert (value, unit_string) to integer minutes. ceil rounding (L20)."""
        import math
        u = (unit or "").strip()
        if u == cls.DAYS.value:
            return math.ceil(value * 24 * 60)
        if u == cls.HOURS.value:
            return math.ceil(value * 60)
        if u == cls.MINUTES.value:
            return math.ceil(value)
        raise ValueError(f"Unknown aging unit: {unit!r}")


class EventClass(IntEnum):
    """L21 — event-class priority at tied integer minute."""
    LOT_COMPLETION = 0
    MACHINE_FREE = 1
    LOT_AGED_IN = 2


class ReservationState(str, Enum):
    """L16 / Section 16."""
    CREATED = "created"
    CONSUMED = "consumed"
    EXPIRED = "expired"
    RELEASED = "released"
