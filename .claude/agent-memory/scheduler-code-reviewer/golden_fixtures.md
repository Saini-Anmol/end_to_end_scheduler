---
name: golden-fixtures
description: Section 17 golden test fixture coverage status
metadata:
  type: project
---

## Coverage as of 2026-05-21

| # | Description | Status | Test location |
|---|---|---|---|
| 1 | EHT1000 24h-MAX squeeze on curing block #1 | **MISSING** | Not found anywhere |
| 2 | BD-12843443-4 Fillering HALT | PRESENT, PASSING | `tests/unit/test_audit.py::TestFindings::test_fixture_2_bd_fillering_halt` |
| 3 | EHT1000 duplicate routing row | PRESENT, PASSING | `tests/unit/test_audit.py::TestFindings::test_fixture_3_eht1000_duplicate_row` |
| 4 | B460 mixed-unit aging | PRESENT, PASSING | `tests/unit/test_unit_conversion.py::TestAgingToMinutes::test_fixture_4_b460` + `TestNormalise::test_fixture_4_b460_in_aging_df` |
| 5 | MPQ + tight-aging HALT | PRESENT, PASSING | `tests/unit/test_lot_sizing.py::TestFixture5MPQTightAgingHALT` |

## Fixture 1 details
Section 17 spec: "First pilot curing row 2026-05-17 07:00. EHT1000 has aging-MAX 24h.
Passes iff: scheduled lot's gap to Building-lot start is ≤ 1440 min and ≥ MIN_aging_min."
This requires a test that runs the full pipeline with the patched BD proc_time and
verifies EHT1000 lot's end_min and the Building lot start_min differ by ≤ 1440.
This test does NOT exist. Critical gap in the Section 17 acceptance bar.

## Note on Fixture 3
CLAUDE.md Section 17 says "Excel row 51 in the routing sheet" for EHT1000 -480MM/90°.
But the actual duplicate is for routed_product="EHT1000" at operation_seq=40, not for
"EHT1000 -480MM/90°". The test correctly uses routed_product=="EHT1000" and op_seq=40.
The CLAUDE.md description was slightly imprecise about which item has the duplicate.
