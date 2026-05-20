"""Diagnostics records — output of Module 11."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgingViolation:
    """One row per breached consumer-producer pair per Section 11."""
    consumer_lot_id: str
    producer_lot_id: str
    item_code: str               # producer item (the one being aged)
    edge_min: int                # producer's min_aging_min
    edge_max: int                # producer's max_aging_min
    actual_gap_min: int          # consumer.start - producer.end
    violation_type: str          # 'MIN' | 'MAX'


@dataclass(frozen=True)
class BuildingToCuringRecord:
    """One row per Building (GT) lot — classification OK / LATE / EARLY."""
    lot_id: str
    machine_id: str
    block_id: str                # the single curing block this GT lot serves
    gt_end_min: int
    curing_start_min: int
    gap_min: int                 # curing_start - gt_end
    min_aging_min: int           # GT aging window
    max_aging_min: int
    classification: str          # 'OK' | 'LATE' | 'EARLY'


@dataclass
class DiagnosticsResult:
    aging_violations: list[AgingViolation]
    building_to_curing: list[BuildingToCuringRecord]
