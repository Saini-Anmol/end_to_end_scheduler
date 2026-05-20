# Golden test fixtures

Five hand-computed cases from `CLAUDE.md` Section 17. **These must pass before
any module past `lot_sizing` is wired up.** Each fixture folder has:

- `inputs/` — the minimal slice of curing + routing + aging + ItemType + MPQ
  needed to exercise the case.
- `expected/` — the hand-computed expected outputs (audit report lines,
  cleaned tables, schedule rows, violation rows, exit code).

| # | Fixture | What it pins down |
|---|---|---|
| 1 | `f1_eht1000_24h_squeeze` | Tightest aging window in the pilot — EHT1000 24 h MAX on curing block #1. Inclusive boundary at exactly 1440 min (L22). |
| 2 | `f2_bd_fillering_halt` | Null `proc_time` on `BD-12843443-4` Fillering. HALT before any `schedule.csv` is written (Section 9 #4, Section 8.D). |
| 3 | `f3_eht1000_duplicate_row` | Two routing rows for `EHT1000 -480MM/90°` calendering — `is_primary == 1.0` kept, NaN dropped, logged to Warn (L7). |
| 4 | `f4_b460_mixed_unit` | `B460` aging has `MinAging = 4 Hours` and `MaxAging = 4 Days`. Normaliser must output `(240, 5760)` minutes (Section 9 #1). |
| 5 | `f5_mpq_tight_aging_halt` | Synthetic single-block demand `< MPQ_Min` with next block beyond aging-MAX. HALT in `lot_sizing` (Section 8.C). |

## Filling `expected/`

Hand-compute every value with the locked rules:
- `effective_min = ceil(nominal_min / 0.95)` (L10, L20).
- `effective_gap = MAX(transfer_time, MIN_aging)` (L14).
- Aging boundaries inclusive both ends (L22).
- `lot_id = {safe_item_code}__{op_seq}__{lot_seq:04d}` (L23).
- `machine_id` is always a string — preserve leading zeros.

Show the working in a `notes.md` inside each fixture folder so the expected
values can be re-derived if the spec ever moves.
