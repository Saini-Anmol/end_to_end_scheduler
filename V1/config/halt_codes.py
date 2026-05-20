"""HALT reason codes (Section 9) mapped to non-zero exit codes.

HALT discipline: engine refuses to write schedule.csv and exits non-zero with
the binding finding named. audit_report.md is still written so the user can see
what went wrong.
"""
from __future__ import annotations

from enum import IntEnum


class HaltCode(IntEnum):
    OK = 0
    # Audit-stage halts (10-19)
    AUDIT_NULL_PROC_TIME = 10           # Section 9 #4 — BD-12843443-4 Fillering
    AUDIT_MISSING_AGING = 11            # Section 9 #8 — pilot item missing from Aging Master
    AUDIT_MISSING_ITEMTYPE = 12         # Section 9 #8 — pilot item missing from ItemType Master
    # Lot-sizing halts (20-29)
    LOT_SIZING_TIGHT_AGING = 20         # Section 8.C — block < MPQ_Min AND aging-MAX blocked aggregation
    # Pre-run guardrails (30-39)
    T0_GUARDRAIL_VIOLATION = 30         # L17 — t0 + longest_path_min_aging > first_curing_start


class HaltError(Exception):
    """Raised when a HALT-class audit finding is detected.

    Carries the binding finding for the bootstrap to surface in the report
    and the exit code.
    """

    def __init__(self, code: HaltCode, finding):
        self.code = code
        self.finding = finding
        super().__init__(f"HALT [{code.name}]: {finding}")
