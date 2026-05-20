"""Schedule model — output of Module 10 (forward_scheduler).

A `ScheduledLot` is a committed lot with machine + start/end minutes. An
`InfeasibilityRecord` captures a lot that could not be committed, with the
binding constraint named (L11 — flag and continue).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ScheduledLot:
    lot_id: str
    item_code: str
    item_type: str
    op_seq: int
    machine_id: str
    start_min: int
    end_min: int
    duration_min: int
    qty: float
    uom: str
    serves_blocks: list[str]
    # Picked producer for each ingredient (item_code → producer lot_id).
    # Empty for items whose ingredients are all raws / work-away.
    producer_lot_ids: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class InfeasibilityRecord:
    lot_id: str
    item_code: str
    op_seq: int
    binding_constraint: str    # short code (AGING_MIN, AGING_MAX, AND_JOIN, MACHINE, DEADLINE)
    message: str


@dataclass(frozen=True)
class ReservationLogEntry:
    """Section 16 reservation log schema."""
    event_minute: int
    event_type: str            # 'created' | 'consumed' | 'expired' | 'released'
    consumer_lot_id: str
    producer_lot_id: str
    item_code: str
    qty: float
    producer_end_min: int
    latest_acceptable_start_min: int


@dataclass
class ScheduleResult:
    """Output of Module 10."""
    scheduled: list[ScheduledLot]
    infeasibilities: list[InfeasibilityRecord]
    reservation_log: list[ReservationLogEntry]

    def by_lot_id(self) -> dict[str, ScheduledLot]:
        return {s.lot_id: s for s in self.scheduled}
