# Fixture 1 — EHT1000 24h-MAX squeeze on curing block #1

**Setup.** First pilot curing row, `2026-05-17 07:00`. EHT1000 has aging-MAX
24 h on its consumer edge.

**Expected.** Scheduler places the EHT1000 calendering lot such that
`calender_end_min` falls within `[curing_start_min − 24h, curing_start_min −
MIN_aging]` (inclusive both ends per L22). At least one such lot exists with
no aging violation.

**Passes iff.** The scheduled lot's gap to the Building-lot start is
≤ 1440 min and ≥ MIN_aging_min.

_Hand-compute the exact minute values and fill `expected/` once the audit
module is wired and t0 is set._
