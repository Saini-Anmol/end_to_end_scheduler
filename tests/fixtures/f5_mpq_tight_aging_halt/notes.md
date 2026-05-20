# Fixture 5 — MPQ + tight-aging HALT

**Setup.** Synthetic single-block demand for a compound where:
- (a) `demand_qty < MPQ_Min`, AND
- (b) the next block is more than `aging_MAX` minutes away (aggregation is
  blocked).

**Expected.** Lot-sizing module HALTs per Section 8.C with the offending
`(block, compound)` printed. No `schedule.csv` written.

**Passes iff.**
- Exit code ≠ 0.
- Lot-sizing HALT line names both the block and the compound.
- No schedule file is produced.
