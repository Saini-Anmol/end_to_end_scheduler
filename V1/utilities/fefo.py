"""FEFO eligibility + selection (L19).

A producer lot P is FEFO-eligible for consumer C at sim_time t iff:
  P.end + MIN_aging ≤ t  ≤  P.end + MAX_aging

Among eligible producers, pick the one with smallest (P.end + MAX_aging)
("first to expire"). Tiebreak by `lot_id` ascending.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class FefoCandidate:
    """Minimal info needed for a FEFO scan."""
    lot_id: str
    end_min: int
    min_aging_min: int
    max_aging_min: int

    def is_aged_in(self, at_min: int) -> bool:
        return self.end_min + self.min_aging_min <= at_min

    def is_expired(self, at_min: int) -> bool:
        return self.end_min + self.max_aging_min < at_min

    def expiry_min(self) -> int:
        return self.end_min + self.max_aging_min


def fefo_pick(
    candidates: Iterable[FefoCandidate],
    at_min: int,
    reserved: set[str] | None = None,
) -> Optional[FefoCandidate]:
    """Return the FEFO winner among candidates at `at_min`, or None.

    A candidate is eligible iff aged in and not expired. Reserved candidates
    (lot_ids in `reserved`) are filtered out — L16 soft reservation invisibility.

    Deterministic: tiebreak (expiry_min, lot_id) ascending.
    """
    reserved_set = reserved or set()
    eligible = [
        c for c in candidates
        if c.lot_id not in reserved_set
        and c.is_aged_in(at_min)
        and not c.is_expired(at_min)
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda c: (c.expiry_min(), c.lot_id))
    return eligible[0]
